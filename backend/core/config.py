"""Environment-based application configuration."""

import logging
from functools import lru_cache
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOGGER = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: Optional[str] = None
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
        if not self.cors_origins.strip():
            message = "CORS_ORIGINS required in production"
            LOGGER.error(message)
            raise ValueError(message)


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
