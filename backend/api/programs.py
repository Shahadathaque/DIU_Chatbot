"""Programs endpoint (GET /api/programs)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.models.programs import ProgramsResponse
from backend.services.programs_service import ProgramsService

router = APIRouter(tags=["programs"])


@lru_cache
def get_programs_service() -> ProgramsService:
    """Build the environment-configured runtime program service."""
    return ProgramsService()


@router.get("/api/programs", response_model=ProgramsResponse)
async def programs(
    service: ProgramsService = Depends(get_programs_service),
) -> ProgramsResponse:
    return service.list_programs()
