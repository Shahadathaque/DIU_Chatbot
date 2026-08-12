"""Typed values shared by the DIU RAG pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class KnowledgeChunk:
    """One independently retrievable, fully traceable piece of a DIU source."""

    chunk_id: str
    document_id: str
    source_id: str
    source_url: str
    title: str
    category: str
    program: Optional[str]
    faculty: Optional[str]
    content: str
    content_type: str
    source_content_type: str
    currency_status: str
    date_sensitive: bool
    manual_review: bool
    retrieved_at: str
    document_hash: str
    source_hash: str
    content_hash: str
    source_locator: str
    page_number: Optional[int]
    chunk_index: int
    extraction_status: str
    quality_flags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["quality_flags"] = list(self.quality_flags)
        return value

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "KnowledgeChunk":
        data = dict(value)
        data["quality_flags"] = tuple(data.get("quality_flags") or ())
        return cls(**data)


@dataclass(frozen=True)
class SearchResult:
    """A ranked chunk with raw semantic and post-ranking relevance scores."""

    chunk: KnowledgeChunk
    similarity_score: float
    relevance_score: float

    def to_dict(self) -> Dict[str, Any]:
        value = self.chunk.to_dict()
        value["similarity_score"] = float(self.similarity_score)
        value["relevance_score"] = float(self.relevance_score)
        return value


@dataclass(frozen=True)
class IndexReport:
    """Outcome of one idempotent vector-store update."""

    received_chunks: int
    inserted_chunks: int
    updated_chunks: int
    deleted_stale_chunks: int
    total_chunks: int
    processed_documents: int

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class VectorMatch:
    """Raw similarity match returned by a vector-store implementation."""

    chunk: KnowledgeChunk
    similarity_score: float


@dataclass(frozen=True)
class SearchFilters:
    """Authority and metadata restrictions applied before vector ranking."""

    category: Optional[str] = None
    program: Optional[str] = None
    include_historical: bool = False
    include_uncertain: bool = False
    include_manual_review: bool = False
    include_partial: bool = False


REQUIRED_RECORD_FIELDS = frozenset(
    {
        "document_id",
        "source_id",
        "source_url",
        "title",
        "category",
        "program",
        "faculty",
        "cleaned_content",
        "cleaned_content_hash",
        "raw_content_hash",
        "content_type",
        "currency_status",
        "date_sensitive",
        "manual_review",
        "retrieved_at",
        "extraction_status",
        "quality_flags",
        "tables",
        "pages",
    }
)

DEFAULT_CURRENCY_STATUSES = frozenset(
    {"current_date_sensitive", "stable_reference"}
)
