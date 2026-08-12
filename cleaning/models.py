"""Serializable models used by the Phase 5 cleaning pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CleanTable:
    """A table retained only after conservative rectangularity checks."""

    headers: List[str]
    rows: List[List[str]]
    extraction_method: str
    page_number: Optional[int] = None
    source_locator: Optional[str] = None
    extraction_quality: str = "reliable"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PageText:
    """Embedded text extracted from one PDF page without OCR."""

    page_number: int
    text: str
    character_count: int
    table_candidates: int = 0
    reliable_tables: int = 0
    quality_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CleanedRecord:
    """One traceable cleaned view of one immutable raw record."""

    document_id: str
    source_id: str
    source_url: str
    canonical_url: str
    final_url: str
    title: str
    observed_title: Optional[str]
    category: str
    program: Optional[str]
    faculty: Optional[str]
    priority: str
    source_last_checked: Optional[str]
    source_notes: Optional[str]
    raw_dataset_version: str
    raw_run_id: str
    raw_record_path: str
    raw_path: str
    raw_content_hash: str
    raw_extracted_content_hash: Optional[str]
    hash_algorithm: str
    raw_response_bytes: int
    source_text_length: int
    cleaned_content: str
    cleaned_content_hash: str
    cleaned_text_length: int
    text_removed_percent: float
    content_type: str
    mime_type: str
    attempted_at: str
    retrieved_at: str
    cleaned_at: str
    currency_status: str
    date_sensitive: bool
    manual_review: bool
    scrape_status: str
    dynamic_page: bool
    capture_representation: str
    capture_redactions: List[str]
    fetch_method: str
    http_status: int
    browser_version: Optional[str]
    approved_dependency_urls: List[str]
    observed_dependency_urls: List[str]
    materialized_shadow_roots: int
    collector_version: str
    cleaning_pipeline_version: str
    extraction_status: str
    extraction_method: str
    extraction_quality: str
    quality_flags: List[str] = field(default_factory=list)
    tables: List[CleanTable] = field(default_factory=list)
    pages: List[PageText] = field(default_factory=list)
    related_documents: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["quality_flags"] = sorted(set(self.quality_flags))
        value["related_documents"] = sorted(
            self.related_documents,
            key=lambda item: (str(item.get("relationship")), str(item.get("document_id"))),
        )
        return value
