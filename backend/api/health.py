"""Health-check route."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.config import get_settings
from rag.config import get_rag_settings
from rag.config import get_generator_settings

router = APIRouter(tags=["health"])
HealthCheckStatus = Literal["ok", "not_configured", "error"]


class HealthChecks(BaseModel):
    """Status of optional runtime dependencies."""

    database: HealthCheckStatus
    model_endpoint: HealthCheckStatus
    rag_backend: HealthCheckStatus


class HealthResponse(BaseModel):
    """Service health response."""

    status: Literal["ok"]
    timestamp: str
    environment: str
    checks: HealthChecks


class LiveResponse(BaseModel):
    """Fast process liveness response that never probes external services."""

    status: Literal["ok"]
    timestamp: str
    environment: str


def _check_database(database_url: str | None) -> HealthCheckStatus:
    if not database_url:
        return "not_configured"
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except Exception:
        return "error"
    return "ok"


def _check_model_endpoint(
    api_base: str | None, api_key: str | None
) -> HealthCheckStatus:
    if not api_base:
        return "not_configured"
    endpoint = f"{api_base.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(endpoint, headers=headers)
        return "ok" if 200 <= response.status_code < 400 else "error"
    except httpx.HTTPError:
        return "error"


def _check_rag_backend() -> HealthCheckStatus:
    try:
        rag_settings = get_rag_settings()
        if rag_settings.rag_vector_backend == "local":
            return "ok" if rag_settings.rag_local_store_path.is_file() else "error"
        if rag_settings.rag_vector_backend == "pgvector":
            return "ok" if rag_settings.database_url else "not_configured"
    except Exception:
        return "error"
    return "error"


async def _health_response() -> HealthResponse:
    settings = get_settings()
    try:
        generator = get_generator_settings()
        model_base = generator.generator_api_base or settings.generator_api_base or settings.openai_api_base
        model_key = generator.generator_api_key or settings.generator_api_key or settings.openai_api_key
    except Exception:  # pragma: no cover - defensive health fallback
        model_base = settings.generator_api_base or settings.openai_api_base
        model_key = settings.generator_api_key or settings.openai_api_key
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        environment=settings.app_env.strip().lower() or "development",
        checks=HealthChecks(
            database=_check_database(settings.database_url),
            model_endpoint=_check_model_endpoint(model_base, model_key),
            rag_backend=_check_rag_backend(),
        ),
    )


@router.get("/api/health", response_model=HealthResponse)
@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process availability and dependency status."""

    return await _health_response()


@router.get("/api/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """Fast liveness probe for providers and frontend wake-up checks."""

    settings = get_settings()
    return LiveResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        environment=settings.app_env.strip().lower() or "development",
    )


@router.get("/api/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    """Dependency readiness probe; callers should cache this result briefly."""

    return await _health_response()
