"""Source list service derived from the cleaned DIU knowledge base."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.core.errors import ArtifactUnavailableError
from backend.core.cache import TTLCache
from backend.core.config import get_settings
from backend.models.sources import SourceInfo, SourcesResponse
from backend.repositories.runtime_catalog import (
    RuntimeCatalogError,
    RuntimeCatalogRepository,
)
from rag.chunker import load_cleaned_records
from rag.config import get_rag_settings


_SOURCES_CACHE: TTLCache[SourcesResponse] = TTLCache()


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
        repository: Optional[RuntimeCatalogRepository] = None,
        catalog_backend: Optional[str] = None,
    ) -> None:
        self._records = records
        self._cleaned_root = cleaned_root
        self._repository = repository
        self._catalog_backend = catalog_backend
        self._cache_default = (
            records is None
            and cleaned_root is None
            and repository is None
            and catalog_backend is None
        )

    def list_sources(self) -> SourcesResponse:
        if self._cache_default:
            cached = _SOURCES_CACHE.get()
            if cached is not None:
                return cached
        if self._records is None and self._use_database():
            response = self._list_database_sources()
            if self._cache_default:
                _SOURCES_CACHE.set(response)
            return response
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
        response = SourcesResponse(sources=sources)
        if self._cache_default:
            _SOURCES_CACHE.set(response)
        return response

    def _use_database(self) -> bool:
        if self._repository is not None:
            return True
        if self._cleaned_root is not None:
            return False
        backend = self._catalog_backend or get_settings().runtime_catalog_backend
        return backend == "database"

    def _list_database_sources(self) -> SourcesResponse:
        repository = self._repository
        if repository is None:
            database_url = get_settings().database_url
            if not database_url:
                raise ArtifactUnavailableError(
                    artifact="Neon runtime source catalog",
                    path="diu_runtime_sources",
                    recovery="Configure DATABASE_URL and synchronize the runtime catalog.",
                )
            repository = RuntimeCatalogRepository(database_url)
        try:
            rows = repository.list_sources()
        except RuntimeCatalogError as error:
            raise ArtifactUnavailableError(
                artifact="Neon runtime source catalog",
                path="diu_runtime_sources",
                recovery="Run scripts/sync_runtime_catalog.py and verify Neon connectivity.",
            ) from error
        return SourcesResponse(sources=[SourceInfo.model_validate(row) for row in rows])

    def _load_records(self) -> Sequence[Dict[str, Any]]:
        root = self._cleaned_root or str(get_rag_settings().rag_cleaned_data_path)
        try:
            return load_cleaned_records(root)
        except (OSError, ValueError) as error:
            raise ArtifactUnavailableError(
                artifact="cleaned DIU dataset",
                path=root,
                recovery="Restore the cleaned snapshot or run scripts/clean_dataset.py.",
            ) from error
