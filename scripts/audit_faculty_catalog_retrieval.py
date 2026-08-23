#!/usr/bin/env python3
"""Audit faculty-scoped retrieval against every cleaned DIU program row."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.faculty_resolution import FACULTY_NAMES, faculty_names_match  # noqa: E402
from rag.models import KnowledgeChunk  # noqa: E402
from rag.retriever import Retriever, create_retriever  # noqa: E402
from rag.vector_store import InMemoryVectorStore  # noqa: E402


DEFAULT_RECORD = ROOT / "data/cleaned/v2/records/diu-prog-001.json"


class _AuditEmbedder:
    """Make semantics uninformative so faculty metadata must decide."""

    model_name = "faculty-catalog-audit"
    model_revision = None
    dimension = 2

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


def _load_chunks(record_path: Path) -> list[KnowledgeChunk]:
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    tables = payload.get("tables") or []
    if not tables:
        raise ValueError(f"{record_path}: no cleaned program table")
    table = tables[0]
    headers = [str(value) for value in table["headers"]]
    required = {"Full Program Name", "Faculty"}
    if not required <= set(headers):
        raise ValueError(f"{record_path}: missing {sorted(required - set(headers))}")
    program_index = headers.index("Full Program Name")
    faculty_index = headers.index("Faculty")
    chunks: list[KnowledgeChunk] = []
    for index, values in enumerate(table["rows"]):
        row = [str(value) for value in values]
        program = row[program_index].strip()
        faculty = row[faculty_index].strip()
        content = " | ".join(
            f"{header}: {value}" for header, value in zip(headers, row)
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"faculty-catalog-audit-{index:03d}",
                document_id=str(payload["document_id"]),
                source_id=str(payload["source_id"]),
                source_url=str(payload["source_url"]),
                title=str(payload["title"]),
                category=str(payload["category"]),
                program=program,
                faculty=faculty,
                content=content,
                content_type="table",
                source_content_type=str(payload.get("content_type") or "html"),
                currency_status=str(payload["currency_status"]),
                date_sensitive=bool(payload["date_sensitive"]),
                manual_review=bool(payload["manual_review"]),
                retrieved_at=str(payload["retrieved_at"]),
                document_hash=str(payload["cleaned_content_hash"]),
                source_hash=str(payload["raw_content_hash"]),
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                source_locator=f"table:0:row:{index}",
                page_number=None,
                chunk_index=index,
                extraction_status=str(payload["extraction_status"]),
                quality_flags=tuple(payload.get("quality_flags") or ()),
            )
        )
    return chunks


def _local_retriever(chunks: Sequence[KnowledgeChunk]) -> Retriever:
    embedder = _AuditEmbedder()
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(
        list(chunks), embedder.embed_documents([chunk.content for chunk in chunks])
    )
    return Retriever(
        embedder,
        store,
        candidate_multiplier=max(1, len(chunks)),
        max_results_per_source=max(1, len(chunks)),
    )


def _query_variants(faculty: str) -> tuple[str, ...]:
    conjunction_variant = (
        faculty.replace("&", "and")
        if "&" in faculty
        else faculty.replace(" and ", " & ")
    )
    return tuple(
        dict.fromkeys(
            (
                faculty,
                conjunction_variant,
                f"Which programs are in {faculty}?",
                f"Show programs from the Faculty of {faculty}",
            )
        )
    )


def run_audit(
    record_path: Path = DEFAULT_RECORD, *, retrieval: bool = False
) -> dict[str, object]:
    chunks = _load_chunks(record_path)
    retriever = create_retriever() if retrieval else _local_retriever(chunks)
    cleaned_faculties = sorted({str(chunk.faculty) for chunk in chunks}, key=str.casefold)
    canonical_faculties = [faculty.canonical for faculty in FACULTY_NAMES]
    unmapped = [
        faculty
        for faculty in cleaned_faculties
        if not any(faculty_names_match(faculty, name) for name in canonical_faculties)
    ]
    failures: list[dict[str, object]] = []
    if unmapped:
        failures.append({"unmapped_cleaned_faculties": unmapped})

    total_queries = 0
    passed_faculties = 0
    for faculty in cleaned_faculties:
        expected = {
            str(chunk.program)
            for chunk in chunks
            if faculty_names_match(str(chunk.faculty), faculty)
        }
        faculty_failed = False
        for query in _query_variants(faculty):
            total_queries += 1
            results = retriever.retrieve(query, top_k=max(1, len(expected)))
            returned = {
                str(result.chunk.program)
                for result in results
                if result.chunk.program
                and result.chunk.faculty
                and faculty_names_match(str(result.chunk.faculty), faculty)
            }
            incompatible = sorted(
                {
                    str(result.chunk.faculty)
                    for result in results
                    if result.chunk.faculty
                    and not faculty_names_match(str(result.chunk.faculty), faculty)
                }
            )
            if returned != expected or incompatible:
                faculty_failed = True
                failures.append(
                    {
                        "faculty": faculty,
                        "query": query,
                        "expected_programs": sorted(expected),
                        "returned_programs": sorted(returned),
                        "incompatible_faculties": incompatible,
                    }
                )
        if not faculty_failed:
            passed_faculties += 1

    return {
        "record": str(record_path),
        "mode": "configured_retrieval" if retrieval else "deterministic_local",
        "total_faculties": len(cleaned_faculties),
        "faculties_passed": passed_faculties,
        "total_programs": len(chunks),
        "total_queries": total_queries,
        "passed": total_queries - sum("query" in failure for failure in failures),
        "failed": len(failures),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument(
        "--retrieval",
        action="store_true",
        help="Use the configured embedding provider and vector store.",
    )
    args = parser.parse_args()
    report = run_audit(args.record, retrieval=args.retrieval)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
