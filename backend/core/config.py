"""Environment-based application configuration."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: Optional[str] = None
    model_name: Optional[str] = None
    embedding_model_name: Optional[str] = None
    hf_token: Optional[str] = None
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
