"""Small synthetic fixtures shared by the offline RAG tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from rag.models import KnowledgeChunk


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cleaned_record(
    *,
    source_id: str = "DIU-TEST-001",
    document_id: Optional[str] = None,
    content: str = "Admission information from a verified DIU source.",
    title: str = "DIU Admission Information",
    category: str = "admission_overview",
    program: Optional[str] = None,
    faculty: Optional[str] = None,
    content_type: str = "html",
    currency_status: str = "current_date_sensitive",
    date_sensitive: bool = True,
    manual_review: bool = False,
    extraction_status: str = "success",
    quality_flags: Optional[List[str]] = None,
    tables: Optional[List[Dict[str, Any]]] = None,
    pages: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    resolved_document_id = document_id or source_id.casefold()
    return {
        "document_id": resolved_document_id,
        "source_id": source_id,
        "source_url": "https://daffodilvarsity.edu.bd/admission/{}".format(
            source_id.casefold()
        ),
        "title": title,
        "category": category,
        "program": program,
        "faculty": faculty,
        "cleaned_content": content,
        "cleaned_content_hash": sha256_text(content),
        "raw_content_hash": sha256_text("raw:" + source_id),
        "content_type": content_type,
        "currency_status": currency_status,
        "date_sensitive": date_sensitive,
        "manual_review": manual_review,
        "retrieved_at": "2026-08-12T00:00:00.000000Z",
        "extraction_status": extraction_status,
        "quality_flags": list(quality_flags or []),
        "tables": list(tables or []),
        "pages": list(pages or []),
    }


def write_cleaned_dataset(
    root: Path, records: Iterable[Dict[str, Any]]
) -> Path:
    records_dir = root / "records"
    records_dir.mkdir(parents=True)
    entries = []
    for index, record in enumerate(records, start=1):
        relative_path = Path("records") / "record-{:02d}.json".format(index)
        serialized = json.dumps(
            record, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        (root / relative_path).write_text(serialized, encoding="utf-8")
        entries.append(
            {
                "record_path": relative_path.as_posix(),
                "record_file_hash": sha256_text(serialized),
                "source_id": record["source_id"],
                "document_id": record["document_id"],
                "raw_content_hash": record["raw_content_hash"],
                "cleaned_content_hash": record["cleaned_content_hash"],
            }
        )
    (root / "manifest.json").write_text(
        json.dumps({"records": entries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return root


def knowledge_chunk(
    chunk_id: str,
    *,
    document_id: Optional[str] = None,
    source_id: Optional[str] = None,
    content: Optional[str] = None,
    category: str = "admission_overview",
    program: Optional[str] = None,
    currency_status: str = "current_date_sensitive",
    manual_review: bool = False,
    extraction_status: str = "success",
) -> KnowledgeChunk:
    resolved_source_id = source_id or "SOURCE-{}".format(chunk_id.upper())
    resolved_content = content or "Verified DIU evidence for {}".format(chunk_id)
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=document_id or "document-{}".format(chunk_id),
        source_id=resolved_source_id,
        source_url="https://daffodilvarsity.edu.bd/source/{}".format(chunk_id),
        title="DIU source {}".format(chunk_id),
        category=category,
        program=program,
        faculty=None,
        content=resolved_content,
        content_type="text",
        source_content_type="html",
        currency_status=currency_status,
        date_sensitive=currency_status != "stable_reference",
        manual_review=manual_review,
        retrieved_at="2026-08-12T00:00:00.000000Z",
        document_hash=sha256_text("document:" + chunk_id),
        source_hash=sha256_text("source:" + chunk_id),
        content_hash=sha256_text(resolved_content),
        source_locator="document-text-1",
        page_number=None,
        chunk_index=0,
        extraction_status=extraction_status,
        quality_flags=(),
    )
