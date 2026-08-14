"""Sources endpoint (GET /api/sources)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.models.sources import SourcesResponse
from backend.services.sources_service import SourcesService

router = APIRouter(tags=["sources"])


@lru_cache
def get_sources_service() -> SourcesService:
    """Build the production sources service from the cleaned dataset."""
    return SourcesService()


@router.get("/api/sources", response_model=SourcesResponse)
async def sources(
    service: SourcesService = Depends(get_sources_service),
) -> SourcesResponse:
    return service.list_sources()