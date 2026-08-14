"""Eligibility endpoint (POST /api/eligibility)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.models.eligibility import EligibilityRequest, EligibilityResponse
from backend.services.eligibility_service import EligibilityService

router = APIRouter(tags=["eligibility"])


@lru_cache
def get_eligibility_service() -> EligibilityService:
    """Build the production eligibility service from the versioned rules."""
    return EligibilityService()


@router.post("/api/eligibility", response_model=EligibilityResponse)
async def eligibility(
    payload: EligibilityRequest,
    service: EligibilityService = Depends(get_eligibility_service),
) -> EligibilityResponse:
    return service.check(payload)
