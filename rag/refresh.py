"""Validated, incremental publication for scheduled DIU knowledge refreshes.

Network collection and cleaning produce an isolated candidate snapshot.  This
module handles the safety boundary after that point: sanity checks, deterministic
change summaries, embedding reuse, and one-transaction PostgreSQL publication.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol, Sequence

from backend.repositories.runtime_catalog import (
    RuntimeCatalogMetadata,
    RuntimeCatalogRepository,
)
from rag.embeddings import Embedder
from rag.models import IndexReport, KnowledgeChunk
from rag.vector_store import PgVectorStore, VectorStoreConfigurationError


class RefreshSafetyError(RuntimeError):
    """Raised before publication when a candidate fails a safety invariant."""


@dataclass(frozen=True)
class ChangeSummary:
    unchanged: int
    new: int
    updated: int
    removed: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "unchanged": self.unchanged,
            "new": self.new,
            "updated": self.updated,
            "removed": self.removed,
        }


@dataclass(frozen=True)
class PublishedState:
    """Minimal non-secret state needed to plan an incremental refresh."""

    chunk_embeddings: Mapping[str, tuple[str, Sequence[float]]]
    programs: Mapping[str, str]
    sources: Mapping[str, str]


@dataclass(frozen=True)
class RefreshCandidate:
    records: Sequence[Mapping[str, Any]]
    chunks: Sequence[KnowledgeChunk]
    programs: Sequence[Mapping[str, Any]]
    sources: Sequence[Mapping[str, Any]]
    metadata: RuntimeCatalogMetadata


@dataclass(frozen=True)
class RefreshResult:
    chunks: ChangeSummary
    programs: ChangeSummary
    sources: ChangeSummary
    embedded_chunks: int
    reused_embeddings: int
    index: IndexReport

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks": self.chunks.to_dict(),
            "programs": self.programs.to_dict(),
            "sources": self.sources.to_dict(),
            "embedded_chunks": self.embedded_chunks,
            "reused_embeddings": self.reused_embeddings,
            "index": self.index.to_dict(),
        }


class RefreshPublisher(Protocol):
    def load_state(self) -> PublishedState: ...

    def publish(
        self,
        candidate: RefreshCandidate,
        embeddings: Sequence[Sequence[float]],
    ) -> IndexReport: ...


def execute_refresh(
    candidate: RefreshCandidate,
    *,
    embedder: Embedder,
    publisher: RefreshPublisher,
    minimum_program_ratio: float = 0.5,
) -> RefreshResult:
    """Validate, incrementally embed, then atomically publish one snapshot."""

    state = publisher.load_state()
    validate_candidate(
        candidate,
        previous_program_count=len(state.programs),
        minimum_program_ratio=minimum_program_ratio,
    )
    chunk_hashes = {chunk.chunk_id: chunk.content_hash for chunk in candidate.chunks}
    program_hashes = {
        str(row["id"]): _program_hash(row) for row in candidate.programs
    }
    source_hashes = {
        str(row["id"]): _source_hash(row) for row in candidate.sources
    }
    chunk_changes = _changes(
        chunk_hashes,
        {key: value[0] for key, value in state.chunk_embeddings.items()},
    )
    embeddings, reused = _candidate_embeddings(
        candidate.chunks,
        inventory=state.chunk_embeddings,
        embedder=embedder,
    )
    # Nothing below this line runs until every network embedding has succeeded.
    index_report = publisher.publish(candidate, embeddings)
    if index_report.total_chunks != len(candidate.chunks):
        raise RefreshSafetyError(
            "post-update vector count does not match the validated candidate"
        )
    return RefreshResult(
        chunks=chunk_changes,
        programs=_changes(program_hashes, state.programs),
        sources=_changes(source_hashes, state.sources),
        embedded_chunks=len(candidate.chunks) - reused,
        reused_embeddings=reused,
        index=index_report,
    )


def validate_candidate(
    candidate: RefreshCandidate,
    *,
    previous_program_count: int,
    minimum_program_ratio: float = 0.5,
) -> None:
    """Reject empty, incomplete, or catastrophically reduced snapshots."""

    if not 0 < minimum_program_ratio <= 1:
        raise ValueError("minimum_program_ratio must be within (0, 1]")
    if not candidate.records:
        raise RefreshSafetyError("candidate contains no cleaned records")
    if not candidate.chunks:
        raise RefreshSafetyError("candidate chunking produced no chunks")
    if not candidate.programs:
        raise RefreshSafetyError("candidate contains no programs")
    if not candidate.sources:
        raise RefreshSafetyError("candidate contains no sources")
    if candidate.metadata.program_count != len(candidate.programs):
        raise RefreshSafetyError("candidate program metadata count is inconsistent")
    if candidate.metadata.source_count != len(candidate.sources):
        raise RefreshSafetyError("candidate source metadata count is inconsistent")

    categories = {str(record.get("category") or "") for record in candidate.records}
    missing_categories = {"tuition_and_fees", "undergraduate_programs"} - categories
    if missing_categories:
        raise RefreshSafetyError(
            "candidate is missing required categories: "
            + ", ".join(sorted(missing_categories))
        )
    tuition_records = [
        record
        for record in candidate.records
        if record.get("category") == "tuition_and_fees"
    ]
    if not any(
        table.get("rows")
        for record in tuition_records
        for table in (record.get("tables") or [])
        if isinstance(table, Mapping)
    ):
        raise RefreshSafetyError("candidate tuition catalog has no structured rows")
    if any(record.get("extraction_status") == "failed" for record in candidate.records):
        raise RefreshSafetyError("candidate contains a failed cleaned extraction")

    chunk_ids = [chunk.chunk_id for chunk in candidate.chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise RefreshSafetyError("candidate contains duplicate chunk IDs")
    source_ids = [str(row.get("id") or "") for row in candidate.sources]
    program_ids = [str(row.get("id") or "") for row in candidate.programs]
    if not all(source_ids) or len(source_ids) != len(set(source_ids)):
        raise RefreshSafetyError("candidate source IDs are blank or duplicated")
    if not all(program_ids) or len(program_ids) != len(set(program_ids)):
        raise RefreshSafetyError("candidate program IDs are blank or duplicated")
    for row in candidate.programs:
        for field in ("id", "name", "source_id", "source_url", "document_id"):
            if not str(row.get(field) or "").strip():
                raise RefreshSafetyError(
                    f"candidate program {row.get('id')!r} is missing {field}"
                )

    if previous_program_count:
        minimum = max(1, math.ceil(previous_program_count * minimum_program_ratio))
        if len(candidate.programs) < minimum:
            raise RefreshSafetyError(
                "candidate program count fell below the configured safety ratio "
                f"({len(candidate.programs)} < {minimum})"
            )


class PostgresRefreshPublisher:
    """Publish vectors and runtime catalogs in one PostgreSQL transaction."""

    def __init__(
        self,
        store: PgVectorStore,
        catalog: RuntimeCatalogRepository,
    ) -> None:
        self.store = store
        self.catalog = catalog

    def load_state(self) -> PublishedState:
        self.store.setup()
        inventory = self.catalog.refresh_inventory()
        return PublishedState(
            chunk_embeddings=self.store.embedding_inventory(),
            programs=inventory["programs"],
            sources=inventory["sources"],
        )

    def publish(
        self,
        candidate: RefreshCandidate,
        embeddings: Sequence[Sequence[float]],
    ) -> IndexReport:
        try:
            import psycopg
            from pgvector.psycopg import register_vector
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ImportError as error:  # pragma: no cover - deployment guard
            raise VectorStoreConfigurationError(
                "psycopg and pgvector are required for automatic publication"
            ) from error

        with psycopg.connect(
            self.store.database_url,
            row_factory=dict_row,
        ) as connection:
            register_vector(connection)
            report = self.store.upsert_chunks_on_connection(
                connection,
                chunks=candidate.chunks,
                embeddings=embeddings,
                processed_document_ids={
                    str(record["document_id"]) for record in candidate.records
                },
                replace_all=True,
            )
            if report.total_chunks != len(candidate.chunks):
                # This check must happen before the connection context exits;
                # raising here rolls the vector replacement back instead of
                # detecting a bad count only after it has been committed.
                raise RefreshSafetyError(
                    "post-update vector count does not match the validated candidate"
                )
            self.catalog.synchronize_on_connection(
                connection,
                programs=candidate.programs,
                sources=candidate.sources,
                metadata=candidate.metadata,
                jsonb_factory=Jsonb,
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) AS count FROM diu_runtime_programs")
                program_count = int(cursor.fetchone()["count"])
                cursor.execute("SELECT count(*) AS count FROM diu_runtime_sources")
                source_count = int(cursor.fetchone()["count"])
            if program_count != len(candidate.programs):
                raise RefreshSafetyError("runtime program post-check failed")
            if source_count != len(candidate.sources):
                raise RefreshSafetyError("runtime source post-check failed")
            # The connection context commits only after every post-check passes;
            # any exception rolls vector and catalog changes back together.
            return report


def _candidate_embeddings(
    chunks: Sequence[KnowledgeChunk],
    *,
    inventory: Mapping[str, tuple[str, Sequence[float]]],
    embedder: Embedder,
) -> tuple[list[list[float]], int]:
    missing = [
        chunk
        for chunk in chunks
        if chunk.chunk_id not in inventory
        or inventory[chunk.chunk_id][0] != chunk.content_hash
    ]
    generated = embedder.embed_documents([chunk.content for chunk in missing])
    if len(generated) != len(missing):
        raise RefreshSafetyError("embedding provider returned an incomplete batch")
    generated_by_id = {
        chunk.chunk_id: [float(value) for value in vector]
        for chunk, vector in zip(missing, generated)
    }
    embeddings: list[list[float]] = []
    reused = 0
    for chunk in chunks:
        existing = inventory.get(chunk.chunk_id)
        if existing is not None and existing[0] == chunk.content_hash:
            embeddings.append([float(value) for value in existing[1]])
            reused += 1
        else:
            embeddings.append(generated_by_id[chunk.chunk_id])
    return embeddings, reused


def _changes(
    candidate: Mapping[str, str], previous: Mapping[str, str]
) -> ChangeSummary:
    common = set(candidate) & set(previous)
    return ChangeSummary(
        unchanged=sum(candidate[key] == previous[key] for key in common),
        new=len(set(candidate) - set(previous)),
        updated=sum(candidate[key] != previous[key] for key in common),
        removed=len(set(previous) - set(candidate)),
    )


def _program_hash(row: Mapping[str, Any]) -> str:
    value = {
        key: row.get(key)
        for key in ("id", "name", "degree", "faculty", "admission_url")
    }
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source_hash(row: Mapping[str, Any]) -> str:
    value = {
        key: row.get(key)
        for key in ("id", "title", "url", "category", "content_hash")
    }
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = [
    "ChangeSummary",
    "PostgresRefreshPublisher",
    "PublishedState",
    "RefreshCandidate",
    "RefreshResult",
    "RefreshSafetyError",
    "execute_refresh",
    "validate_candidate",
]
