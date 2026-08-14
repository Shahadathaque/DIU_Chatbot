"""Source list service derived from the cleaned DIU knowledge base."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.models.sources import SourceInfo, SourcesResponse
from rag.chunker import load_cleaned_records
from rag.config import get_rag_settings


class SourcesService:
    """Expose registered/available DIU sources from cleaned records.

    ``category`` is returned as an additive optional field per TASK-01 and the
    contract's "prefer additive optional fields" change policy.
    """

    def __init__(
        self,
        records: Optional[Iterable[Dict[str, Any]]] = None,
        *,
        cleaned_root: Optional[str] = None,
    ) -> None:
        self._records = records
        self._cleaned_root = cleaned_root

    def list_sources(self) -> SourcesResponse:
        records = list(self._records if self._records is not None else self._load_records())
        sources: List[SourceInfo] = []
        for record in records:
            source = SourceInfo(
                id=str(record["source_id"]),
                title=str(record["title"]),
                url=str(record["source_url"]),
                retrieved_at=record.get("retrieved_at"),
                category=record.get("category"),
            )
            sources.append(source)
        sources.sort(key=lambda item: (item.id.casefold(), item.id))
        return SourcesResponse(sources=sources)

    def _load_records(self) -> Sequence[Dict[str, Any]]:
        root = self._cleaned_root or str(get_rag_settings().rag_cleaned_data_path)
        return load_cleaned_records(root)