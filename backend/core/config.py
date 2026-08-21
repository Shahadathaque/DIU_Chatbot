"""Environment-based application configuration."""

import logging
from functools import lru_cache
from typing import Any, Literal, Optional
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOGGER = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: Optional[str] = None
    runtime_catalog_backend: Literal["local", "database"] = "local"
    rag_vector_backend: Literal["local", "pgvector"] = "pgvector"
    openai_api_base: Optional[str] = None
    openai_api_key: Optional[str] = None
    # GENERATOR_* is the canonical runtime configuration used by rag.generator.
    # The OPENAI_* fields remain as backwards-compatible aliases for existing
    # deployments and are never logged.
    generator_backend: Optional[str] = None
    generator_api_base: Optional[str] = None
    generator_api_key: Optional[str] = None
    generator_api_model: Optional[str] = None
    model_name: Optional[str] = None
    embedding_model_name: Optional[str] = None
    embedding_backend: Literal["local", "openai"] = "local"
    embedding_api_base: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_api_model: Optional[str] = None
    hf_token: Optional[str] = None
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = Field(30, ge=0, le=10_000)
    sentry_dsn: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "database_url",
        "openai_api_base",
        "openai_api_key",
        "generator_backend",
        "generator_api_base",
        "generator_api_key",
        "generator_api_model",
        "model_name",
        "embedding_model_name",
        "embedding_api_base",
        "embedding_api_key",
        "embedding_api_model",
        "hf_token",
        "sentry_dsn",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_none(cls, value: Any) -> Any:
        """Treat empty deployment variables as unset optional values."""

        return None if isinstance(value, str) and not value.strip() else value

    def validate_production_settings(self) -> None:
        """Ensure deployment-critical settings exist in production mode."""

        if self.app_env.strip().lower() != "production":
            return
        if not self.database_url:
            message = "DATABASE_URL required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if not self.cors_origins.strip():
            message = "CORS_ORIGINS required in production"
            LOGGER.error(message)
            raise ValueError(message)
        self.production_cors_origins()
        model_endpoint = self.generator_api_base or self.openai_api_base
        if not model_endpoint:
            message = (
                "OPENAI_API_BASE required in production; "
                "GENERATOR_API_BASE required in production"
            )
            LOGGER.error(message)
            raise ValueError(message)
        backend = (self.generator_backend or "openai").strip().lower()
        if backend != "openai":
            message = "GENERATOR_BACKEND=openai required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if not (self.generator_api_key or self.openai_api_key):
            message = "GENERATOR_API_KEY required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if not (self.generator_api_model or self.model_name):
            message = "GENERATOR_API_MODEL required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if self.runtime_catalog_backend != "database":
            message = "RUNTIME_CATALOG_BACKEND=database required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if self.rag_vector_backend != "pgvector":
            message = "RAG_VECTOR_BACKEND=pgvector required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if self.embedding_backend != "openai":
            message = "EMBEDDING_BACKEND=openai required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if not self.embedding_api_base:
            message = "EMBEDDING_API_BASE required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if not self.embedding_api_key:
            message = "EMBEDDING_API_KEY required in production"
            LOGGER.error(message)
            raise ValueError(message)
        if not self.embedding_api_model:
            message = "EMBEDDING_API_MODEL required in production"
            LOGGER.error(message)
            raise ValueError(message)

    def production_cors_origins(self) -> list[str]:
        """Return exact browser origins and reject unsafe production values."""

        origins = [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]
        if not origins:
            raise ValueError("CORS_ORIGINS required in production")
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "CORS_ORIGINS cannot contain '*' in production"
                )
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS entries must be exact http(s) origins"
                )
        return list(dict.fromkeys(origin.rstrip("/") for origin in origins))


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
