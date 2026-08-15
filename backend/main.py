"""FastAPI application entry point."""

import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.eligibility import router as eligibility_router
from backend.api.health import router as health_router
from backend.api.programs import router as programs_router
from backend.api.sources import router as sources_router
from backend.core.config import get_settings
from backend.core.errors import register_exception_handlers
from backend.core.logging import configure_logging
from rag.config import get_rag_settings
from rag.config import get_generator_settings

logger = logging.getLogger(__name__)
settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="DIU Admission AI API",
    description="Research backend for the DIU Admission AI project.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(eligibility_router)
app.include_router(programs_router)
app.include_router(sources_router)


def _configure_optional_sentry() -> None:
    """Enable Sentry only when explicitly configured and installed."""

    if settings.app_env.strip().lower() != "production" or not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            environment="production",
        )
        logger.info("[startup] Error monitoring: Sentry configured")
    except ImportError:
        logger.warning(
            "[startup] Sentry DSN is set but sentry-sdk is not installed; monitoring disabled"
        )


_configure_optional_sentry()


@app.on_event("startup")
async def startup_validation() -> None:
    """Log runtime configuration and validate production settings."""

    runtime_settings = get_settings()
    try:
        rag_backend = get_rag_settings().rag_vector_backend
    except Exception:  # pragma: no cover - defensive startup logging fallback
        rag_backend = "unavailable"

    environment = runtime_settings.app_env.strip().lower() or "development"
    cors_origins = ",".join(
        origin.strip()
        for origin in runtime_settings.cors_origins.split(",")
        if origin.strip()
    ) or "not configured"
    database_status = (
        "PostgreSQL configured" if runtime_settings.database_url else "not configured"
    )
    try:
        generator_settings = get_generator_settings()
        generator_base = (
            generator_settings.generator_api_base
            or runtime_settings.generator_api_base
            or runtime_settings.openai_api_base
        )
        generator_backend = generator_settings.generator_backend
    except Exception:  # pragma: no cover - defensive startup logging fallback
        generator_base = runtime_settings.generator_api_base or runtime_settings.openai_api_base
        generator_backend = runtime_settings.generator_backend or "unknown"
    model_status = (
        "Configured ({})".format(generator_backend)
        if generator_base
        else "not configured"
    )
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    logger.info("[startup] Timestamp: %s", timestamp)
    logger.info("[startup] Environment: %s", environment)
    logger.info("[startup] CORS origins: %s", cors_origins)
    logger.info("[startup] Database: %s", database_status)
    logger.info("[startup] Model endpoint: %s", model_status)
    logger.info("[startup] RAG backend: %s", rag_backend)
    logger.info(
        "[startup] Runtime catalog: %s",
        runtime_settings.runtime_catalog_backend,
    )
    logger.info(
        "[startup] Embeddings: %s",
        runtime_settings.embedding_backend,
    )

    if environment != "production":
        logger.info("[startup] Development mode: optional production settings are not required")
        return

    logger.info("Production mode: validating required settings...")
    try:
        runtime_settings.validate_production_settings()
    except ValueError as error:
        logger.error("❌ Production configuration error: %s", error)
        raise
    logger.info("✅ All required production settings are configured")
