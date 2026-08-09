"""FastAPI application entry point."""

from fastapi import FastAPI

from backend.api.health import router as health_router
from backend.core.config import get_settings
from backend.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="DIU Admission AI API",
    description="Research backend for the DIU Admission AI project.",
    version="0.1.0",
)
app.include_router(health_router)

