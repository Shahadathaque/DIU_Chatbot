"""Eligibility endpoint (POST /api/eligibility)."""

from functools import lru_cache

from fastapi import APIRouter, Body, Depends

from backend.models.eligibility import EligibilityRequest, EligibilityResponse
from backend.services.eligibility_service import EligibilityService

router = APIRouter(tags=["eligibility"])


@lru_cache
def _build_eligibility_service() -> EligibilityService:
    """Build and cache the production eligibility service."""

    return EligibilityService()


def get_eligibility_service(
    payload: EligibilityRequest = Body(...),
) -> EligibilityService:
    """Build the service only after FastAPI validates the request body."""
    del payload
    return _build_eligibility_service()


@router.post("/api/eligibility", response_model=EligibilityResponse)
async def eligibility(
    payload: EligibilityRequest,
    service: EligibilityService = Depends(get_eligibility_service),
) -> EligibilityResponse:
    return service.check(payload)
