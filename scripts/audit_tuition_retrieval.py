#!/usr/bin/env python3
"""Audit exact tuition-row retrieval for every cleaned DIU catalog program."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.models import KnowledgeChunk
from rag.retriever import Retriever
from rag.vector_store import InMemoryVectorStore


DEFAULT_RECORD = ROOT / "data/cleaned/v2/records/diu-fee-001.json"
DEFAULT_INTERNATIONAL_RECORD = ROOT / "data/cleaned/v2/records/diu-fee-002.json"


class _AuditEmbedder:
    """Make semantics deliberately uninformative to test metadata resolution."""

    model_name = "tuition-catalog-audit"
    model_revision = None
    dimension = 2

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


def _load_rows(record_path: Path) -> tuple[list[str], list[list[str]], dict]:
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    tables = payload.get("tables") or []
    if not tables:
        raise ValueError(f"{record_path}: no cleaned tuition table")
    table = tables[0]
    headers = [str(value) for value in table["headers"]]
    rows = [[str(value) for value in row] for row in table["rows"]]
    if "Full Program Name" not in headers:
        raise ValueError(f"{record_path}: Full Program Name column is missing")
    return headers, rows, payload


def _chunks(headers: list[str], rows: list[list[str]], payload: dict) -> list[KnowledgeChunk]:
    program_index = headers.index("Full Program Name")
    chunks: list[KnowledgeChunk] = []
    for index, row in enumerate(rows):
        program = row[program_index].strip()
        content = " | ".join(f"{header}: {value}" for header, value in zip(headers, row))
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunks.append(
            KnowledgeChunk(
                chunk_id="tuition-audit-{}-{:03d}".format(
                    str(payload["source_id"]).casefold(), index
                ),
                document_id=str(payload["document_id"]),
                source_id=str(payload["source_id"]),
                source_url=str(payload["source_url"]),
                title=str(payload["title"]),
                category=str(payload["category"]),
                program=program,
                faculty=None,
                content=content,
                content_type="table",
                source_content_type=str(payload.get("content_type") or "html"),
                currency_status=str(payload["currency_status"]),
                date_sensitive=bool(payload["date_sensitive"]),
                manual_review=bool(payload["manual_review"]),
                retrieved_at=str(payload["retrieved_at"]),
                document_hash=str(payload["cleaned_content_hash"]),
                source_hash=str(payload["raw_content_hash"]),
                content_hash=content_hash,
                source_locator=f"table:0:row:{index}",
                page_number=None,
                chunk_index=index,
                extraction_status=str(payload["extraction_status"]),
                quality_flags=tuple(payload.get("quality_flags") or ()),
            )
        )
    return chunks


def _query_variants(program: str) -> tuple[str, ...]:
    """Exercise harmless typography without changing the named program."""

    punctuation_free = re.sub(r"[.,()]", " ", program)
    punctuation_free = re.sub(r"\s+", " ", punctuation_free).strip()
    conjunction_variant = (
        program.replace("&", "and") if "&" in program else program.replace(" and ", " & ")
    )
    variants = (
        f"{program} tuition fees",
        f"{program.lower()} TUITION FEES",
        f"  {program}   tuition   fees  ",
        f"{punctuation_free} tuition fees",
        f"{conjunction_variant} tuition fees",
    )
    return tuple(dict.fromkeys(variants))


def run_audit(record_path: Path = DEFAULT_RECORD) -> dict:
    headers, rows, payload = _load_rows(record_path)
    chunks = _chunks(headers, rows, payload)
    embedder = _AuditEmbedder()
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(chunks, embedder.embed_documents([chunk.content for chunk in chunks]))
    retriever = Retriever(
        embedder,
        store,
        candidate_multiplier=max(1, len(chunks)),
        max_results_per_source=max(1, len(chunks)),
    )

    failures: list[dict[str, object]] = []
    total_queries = 0
    passed_programs = 0
    for chunk in chunks:
        program_failed = False
        for query in _query_variants(str(chunk.program)):
            total_queries += 1
            results = retriever.retrieve(query, top_k=1)
            returned = [result.chunk.program for result in results]
            if returned != [chunk.program]:
                program_failed = True
                failures.append(
                    {"query": query, "expected": chunk.program, "returned": returned}
                )
        if not program_failed:
            passed_programs += 1
    return {
        "record": str(record_path),
        "total_programs": len(chunks),
        "programs_passed": passed_programs,
        "total_queries": total_queries,
        "passed": total_queries - len(failures),
        "failed": len(failures),
        "failures": failures,
    }


def run_audience_audit(
    local_record: Path = DEFAULT_RECORD,
    international_record: Path = DEFAULT_INTERNATIONAL_RECORD,
) -> dict:
    """Verify audience isolation and comparison for every USD catalog row."""

    local_headers, local_rows, local_payload = _load_rows(local_record)
    international_headers, international_rows, international_payload = _load_rows(
        international_record
    )
    local_chunks = _chunks(local_headers, local_rows, local_payload)
    international_chunks = _chunks(
        international_headers, international_rows, international_payload
    )
    chunks = [*local_chunks, *international_chunks]
    embedder = _AuditEmbedder()
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(
        chunks, embedder.embed_documents([chunk.content for chunk in chunks])
    )
    retriever = Retriever(
        embedder,
        store,
        candidate_multiplier=max(1, len(chunks)),
        max_results_per_source=max(1, len(chunks)),
    )

    local_by_normalized = {
        re.sub(r"\W+", " ", str(chunk.program).casefold()).strip(): chunk
        for chunk in local_chunks
    }
    failures: list[dict[str, object]] = []
    total_queries = 0
    compared_programs = 0
    for international in international_chunks:
        program = str(international.program)
        international_queries = (
            f"international {program} tuition fees",
            f"foreign student {program} fees in USD",
        )
        for query in international_queries:
            total_queries += 1
            returned = retriever.retrieve(query, top_k=3)
            if [result.chunk.chunk_id for result in returned] != [
                international.chunk_id
            ]:
                failures.append(
                    {
                        "query": query,
                        "expected": [international.chunk_id],
                        "returned": [result.chunk.chunk_id for result in returned],
                    }
                )

        normalized = re.sub(r"\W+", " ", program.casefold()).strip()
        local = local_by_normalized.get(normalized)
        if local is None:
            continue
        compared_programs += 1
        checks = (
            (f"local {program} tuition fees", [local.chunk_id]),
            (f"{program} fees in BDT", [local.chunk_id]),
        )
        for query, expected in checks:
            total_queries += 1
            returned = retriever.retrieve(query, top_k=3)
            returned_ids = [result.chunk.chunk_id for result in returned]
            if returned_ids != expected:
                failures.append(
                    {"query": query, "expected": expected, "returned": returned_ids}
                )
        mixed_query = f"compare local and international {program} tuition fees"
        total_queries += 1
        returned = retriever.retrieve(mixed_query, top_k=3)
        returned_ids = {result.chunk.chunk_id for result in returned}
        expected_ids = {local.chunk_id, international.chunk_id}
        if returned_ids != expected_ids:
            failures.append(
                {
                    "query": mixed_query,
                    "expected": sorted(expected_ids),
                    "returned": sorted(returned_ids),
                }
            )

    return {
        "international_programs": len(international_chunks),
        "programs_with_local_comparison": compared_programs,
        "total_queries": total_queries,
        "passed": total_queries - len(failures),
        "failed": len(failures),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    args = parser.parse_args()
    report = run_audit(args.record)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
