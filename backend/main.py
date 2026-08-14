"""FastAPI application entry point."""

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
)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(eligibility_router)
app.include_router(programs_router)
app.include_router(sources_router)

