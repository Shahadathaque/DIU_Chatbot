"""Regression tests for guarded, incremental knowledge publication."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from backend.repositories.runtime_catalog import RuntimeCatalogMetadata
from rag.models import IndexReport
from rag.retriever import Retriever
from rag.refresh import (
    PostgresRefreshPublisher,
    PublishedState,
    RefreshCandidate,
    RefreshSafetyError,
    execute_refresh,
)
from rag.vector_store import InMemoryVectorStore
from tests.rag_helpers import cleaned_record, knowledge_chunk


class FakeEmbedder:
    model_name = "hosted-test"
    model_revision = None
    dimension = 2

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed_documents(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("simulated embedding failure")
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, query):
        return [1.0, 0.0]


class FakePublisher:
    def __init__(self, candidate: RefreshCandidate, *, fail: str | None = None) -> None:
        self.fail = fail
        self.publish_calls = 0
        self.state = PublishedState(
            chunk_embeddings={
                chunk.chunk_id: (chunk.content_hash, [1.0, 0.0])
                for chunk in candidate.chunks
            },
            programs={str(row["id"]): _program_hash(row) for row in candidate.programs},
            sources={str(row["id"]): _source_hash(row) for row in candidate.sources},
        )
        self.published_chunks = tuple(candidate.chunks)
        self.published_embeddings = [
            list(self.state.chunk_embeddings[chunk.chunk_id][1])
            for chunk in candidate.chunks
        ]

    def load_state(self):
        return deepcopy(self.state)

    def publish(self, candidate, embeddings):
        self.publish_calls += 1
        if self.fail == "database":
            raise RuntimeError("simulated database failure")
        proposed = PublishedState(
            chunk_embeddings={
                chunk.chunk_id: (chunk.content_hash, list(vector))
                for chunk, vector in zip(candidate.chunks, embeddings)
            },
            programs={str(row["id"]): _program_hash(row) for row in candidate.programs},
            sources={str(row["id"]): _source_hash(row) for row in candidate.sources},
        )
        if self.fail == "catalog":
            # A real PostgresRefreshPublisher raises before transaction commit.
            raise RuntimeError("simulated runtime catalog failure")
        old_ids = set(self.state.chunk_embeddings)
        new_ids = set(proposed.chunk_embeddings)
        self.state = proposed
        self.published_chunks = tuple(candidate.chunks)
        self.published_embeddings = [list(vector) for vector in embeddings]
        return IndexReport(
            received_chunks=len(new_ids),
            inserted_chunks=len(new_ids - old_ids),
            updated_chunks=0,
            deleted_stale_chunks=len(old_ids - new_ids),
            total_chunks=len(new_ids),
            processed_documents=len(candidate.records),
        )


def _candidate(
    *,
    program_names=("Program One", "Program Two"),
    tuition_content="Tuition fee row version one",
) -> RefreshCandidate:
    tuition = cleaned_record(
        source_id="DIU-TUI-001",
        category="tuition_and_fees",
        content=tuition_content,
        tables=[{"headers": ["Program", "Fee"], "rows": [["Program One", "verified"]]}],
    )
    catalog = cleaned_record(
        source_id="DIU-PROG-001",
        category="undergraduate_programs",
        content="Official program catalog",
    )
    chunks = (
        knowledge_chunk(
            "tuition-row",
            document_id=tuition["document_id"],
            source_id=tuition["source_id"],
            category="tuition_and_fees",
            content=tuition_content,
        ),
        knowledge_chunk(
            "catalog",
            document_id=catalog["document_id"],
            source_id=catalog["source_id"],
            category="undergraduate_programs",
            content="Official program catalog",
        ),
    )
    programs = tuple(
        {
            "id": f"program-{index}",
            "name": name,
            "degree": "B.Sc.",
            "faculty": "Faculty",
            "admission_url": f"https://daffodilvarsity.edu.bd/program/{index}",
            "source_id": catalog["source_id"],
            "source_url": catalog["source_url"],
            "document_id": catalog["document_id"],
            "document_hash": catalog["cleaned_content_hash"],
            "content_hash": catalog["cleaned_content_hash"],
            "provenance": {},
        }
        for index, name in enumerate(program_names, start=1)
    )
    sources = tuple(
        {
            "id": record["source_id"],
            "title": record["title"],
            "url": record["source_url"],
            "document_id": record["document_id"],
            "document_hash": record["cleaned_content_hash"],
            "content_hash": record["cleaned_content_hash"],
            "provenance": {},
        }
        for record in (tuition, catalog)
    )
    metadata = RuntimeCatalogMetadata(
        dataset_version="refresh-test",
        dataset_fingerprint="f" * 64,
        manifest_hash="a" * 64,
        program_count=len(programs),
        source_count=len(sources),
    )
    return RefreshCandidate(
        records=(tuition, catalog),
        chunks=chunks,
        programs=programs,
        sources=sources,
        metadata=metadata,
    )


def test_unchanged_refresh_reuses_all_embeddings_without_duplicates() -> None:
    candidate = _candidate()
    publisher = FakePublisher(candidate)
    embedder = FakeEmbedder()

    result = execute_refresh(candidate, embedder=embedder, publisher=publisher)

    assert result.chunks.unchanged == 2
    assert result.embedded_chunks == 0
    assert result.reused_embeddings == 2
    assert embedder.calls == [[]]
    assert len(publisher.state.chunk_embeddings) == 2


def test_new_program_is_published_and_available_in_runtime_state() -> None:
    old = _candidate(program_names=("Program One",))
    new = _candidate(program_names=("Program One", "New Program"))
    publisher = FakePublisher(old)

    result = execute_refresh(new, embedder=FakeEmbedder(), publisher=publisher)

    assert result.programs.new == 1
    assert "program-2" in publisher.state.programs


def test_new_program_chunk_is_searchable_after_successful_refresh() -> None:
    old = _candidate(program_names=("Program One",))
    new = _candidate(program_names=("Program One", "New Program"))
    program_chunk = replace(
        knowledge_chunk(
            "new-program-row",
            document_id=new.records[1]["document_id"],
            source_id=new.records[1]["source_id"],
            category="undergraduate_programs",
            content="New Program | Faculty",
            program="New Program",
        ),
        content_type="table",
        faculty="Faculty",
    )
    new = replace(new, chunks=(*new.chunks, program_chunk))
    publisher = FakePublisher(old)
    embedder = FakeEmbedder()

    execute_refresh(new, embedder=embedder, publisher=publisher)

    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(
        publisher.published_chunks,
        publisher.published_embeddings,
    )
    results = Retriever(
        embedder,
        store,
        candidate_multiplier=10,
        max_results_per_source=10,
    ).retrieve("Does DIU offer New Program?", top_k=1)
    assert [result.chunk.program for result in results] == ["New Program"]


def test_changed_tuition_row_reembeds_only_changed_chunk() -> None:
    old = _candidate(tuition_content="Old verified tuition")
    new = _candidate(tuition_content="Updated verified tuition")
    publisher = FakePublisher(old)
    embedder = FakeEmbedder()

    result = execute_refresh(new, embedder=embedder, publisher=publisher)

    assert result.embedded_chunks == 1
    assert result.reused_embeddings == 1
    assert result.chunks.updated == 1
    assert result.chunks.new == 0
    assert result.chunks.removed == 0
    assert result.sources.updated == 1


def test_renamed_program_is_reported_as_update() -> None:
    old = _candidate(program_names=("Old Name", "Program Two"))
    new = _candidate(program_names=("New Name", "Program Two"))
    result = execute_refresh(new, embedder=FakeEmbedder(), publisher=FakePublisher(old))
    assert result.programs.updated == 1


def test_removed_program_disappears_only_after_valid_publication() -> None:
    old = _candidate(program_names=("Program One", "Program Two"))
    new = _candidate(program_names=("Program One",))
    publisher = FakePublisher(old)

    result = execute_refresh(new, embedder=FakeEmbedder(), publisher=publisher)

    assert result.programs.removed == 1
    assert set(publisher.state.programs) == {"program-1"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: replace(value, records=()), "no cleaned records"),
        (
            lambda value: replace(
                value,
                records=tuple(
                    {**record, "tables": []}
                        if record["category"] == "tuition_and_fees"
                    else record
                    for record in value.records
                )
            ),
            "tuition catalog",
        ),
        (
            lambda value: replace(
                value,
                records=tuple(
                    {**record, "extraction_status": "failed"}
                        if record["category"] == "tuition_and_fees"
                    else record
                    for record in value.records
                )
            ),
            "failed cleaned extraction",
        ),
    ],
)
def test_malformed_empty_or_cleaning_failed_candidate_never_publishes(
    mutation, message
) -> None:
    old = _candidate()
    publisher = FakePublisher(old)
    candidate = mutation(old)

    with pytest.raises(RefreshSafetyError, match=message):
        execute_refresh(candidate, embedder=FakeEmbedder(), publisher=publisher)

    assert publisher.publish_calls == 0


def test_catastrophic_program_reduction_is_rejected_before_publication() -> None:
    old = _candidate(program_names=("One", "Two", "Three", "Four"))
    new = _candidate(program_names=("One",))
    publisher = FakePublisher(old)
    with pytest.raises(RefreshSafetyError, match="safety ratio"):
        execute_refresh(new, embedder=FakeEmbedder(), publisher=publisher)
    assert publisher.publish_calls == 0


def test_embedding_failure_preserves_existing_production_state() -> None:
    old = _candidate(tuition_content="Old tuition")
    new = _candidate(tuition_content="New tuition")
    publisher = FakePublisher(old)
    before = deepcopy(publisher.state)
    with pytest.raises(RuntimeError, match="embedding failure"):
        execute_refresh(new, embedder=FakeEmbedder(fail=True), publisher=publisher)
    assert publisher.state == before
    assert publisher.publish_calls == 0


@pytest.mark.parametrize("failure", ["database", "catalog"])
def test_database_or_catalog_failure_rolls_back_complete_snapshot(failure) -> None:
    old = _candidate(tuition_content="Old tuition")
    new = _candidate(tuition_content="New tuition")
    publisher = FakePublisher(old, fail=failure)
    before = deepcopy(publisher.state)
    with pytest.raises(RuntimeError, match="simulated"):
        execute_refresh(new, embedder=FakeEmbedder(), publisher=publisher)
    assert publisher.state == before


def test_successful_idempotent_rerun_reuses_vectors_and_keeps_counts() -> None:
    old = _candidate(tuition_content="Old tuition")
    new = _candidate(tuition_content="New tuition")
    publisher = FakePublisher(old)
    execute_refresh(new, embedder=FakeEmbedder(), publisher=publisher)
    second_embedder = FakeEmbedder()

    result = execute_refresh(new, embedder=second_embedder, publisher=publisher)

    assert result.chunks.unchanged == len(new.chunks)
    assert result.embedded_chunks == 0
    assert second_embedder.calls == [[]]
    assert len(publisher.state.chunk_embeddings) == len(new.chunks)


def test_postgres_vector_postcheck_raises_before_transaction_commit(
    monkeypatch,
) -> None:
    import pgvector.psycopg
    import psycopg

    candidate = _candidate()

    class Connection:
        exit_exception = None

        def __enter__(self):
            return self

        def __exit__(self, exception_type, _exception, _traceback):
            self.exit_exception = exception_type

    class Store:
        database_url = "postgresql://example.invalid/test"

        def upsert_chunks_on_connection(self, *_args, **_kwargs):
            return IndexReport(
                received_chunks=len(candidate.chunks),
                inserted_chunks=1,
                updated_chunks=0,
                deleted_stale_chunks=0,
                total_chunks=len(candidate.chunks) - 1,
                processed_documents=len(candidate.records),
            )

    class Catalog:
        synchronized = False

        def synchronize_on_connection(self, *_args, **_kwargs):
            self.synchronized = True

    connection = Connection()
    catalog = Catalog()
    monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: connection)
    monkeypatch.setattr(
        pgvector.psycopg, "register_vector", lambda _connection: None
    )

    with pytest.raises(RefreshSafetyError, match="vector count"):
        PostgresRefreshPublisher(Store(), catalog).publish(
            candidate,
            [[1.0, 0.0] for _chunk in candidate.chunks],
        )

    assert connection.exit_exception is RefreshSafetyError
    assert catalog.synchronized is False


def _program_hash(row) -> str:
    selected = {
        key: row.get(key)
        for key in ("id", "name", "degree", "faculty", "admission_url")
    }
    return hashlib.sha256(
        json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_hash(row) -> str:
    selected = {
        key: row.get(key)
        for key in ("id", "title", "url", "category", "content_hash")
    }
    return hashlib.sha256(
        json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
