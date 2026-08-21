#!/usr/bin/env python3
"""Audit exact tuition-row retrieval for every cleaned DIU catalog program."""

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

from rag.models import KnowledgeChunk
from rag.retriever import Retriever
from rag.vector_store import InMemoryVectorStore


DEFAULT_RECORD = ROOT / "data/cleaned/v2/records/diu-fee-001.json"


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
                chunk_id=f"tuition-audit-{index:03d}",
                document_id=str(payload["document_id"]),
                source_id=str(payload["source_id"]),
                source_url=str(payload["source_url"]),
                title=str(payload["title"]),
                category="tuition_and_fees",
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
    for chunk in chunks:
        query = f"{chunk.program} tuition fees"
        results = retriever.retrieve(query, top_k=1)
        returned = [result.chunk.program for result in results]
        if returned != [chunk.program]:
            failures.append(
                {"query": query, "expected": chunk.program, "returned": returned}
            )
    return {
        "record": str(record_path),
        "total_programs": len(chunks),
        "passed": len(chunks) - len(failures),
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
