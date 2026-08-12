"""Environment-driven configuration for DIU knowledge retrieval."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
DEFAULT_EMBEDDING_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
DEFAULT_EMBEDDING_DIMENSION = 768


class RagSettings(BaseSettings):
    """RAG settings loaded from environment variables or the root ``.env``."""

    database_url: Optional[str] = None
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL
    embedding_model_revision: Optional[str] = None
    embedding_dimension: int = Field(DEFAULT_EMBEDDING_DIMENSION, ge=1)
    embedding_batch_size: int = Field(16, ge=1)
    embedding_device: Optional[str] = None

    rag_vector_backend: Literal["pgvector", "local"] = "pgvector"
    rag_table_name: str = "diu_knowledge_chunks"
    rag_local_store_path: Path = PROJECT_ROOT / "data/chunks/local_knowledge_base.json"
    rag_cleaned_data_path: Path = PROJECT_ROOT / "data/cleaned/v1"

    rag_chunk_size: int = Field(1200, ge=300)
    rag_chunk_overlap: int = Field(150, ge=0)
    rag_min_chunk_size: int = Field(100, ge=1)
    rag_min_similarity_score: float = Field(0.75, ge=-1.0, le=1.0)
    rag_min_relevance_score: float = Field(0.72, ge=-1.0, le=1.0)
    rag_candidate_multiplier: int = Field(5, ge=1, le=20)
    rag_max_results_per_source: int = Field(5, ge=1, le=20)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", "embedding_model_revision", "embedding_device", mode="before")
    @classmethod
    def blank_optional_values_are_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("embedding_model_name", mode="before")
    @classmethod
    def blank_model_uses_default(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return DEFAULT_EMBEDDING_MODEL
        return value

    @field_validator("rag_local_store_path", "rag_cleaned_data_path")
    @classmethod
    def resolve_rag_paths_from_project_root(cls, value: Path) -> Path:
        """Make environment-relative RAG paths independent of the caller's cwd."""

        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @field_validator("rag_table_name")
    @classmethod
    def validate_table_name(cls, value: str) -> str:
        if not value or len(value) > 48:
            raise ValueError("RAG_TABLE_NAME must contain 1-48 characters")
        if (
            not value.isascii()
            or not value.replace("_", "").isalnum()
            or not value[0].isalpha()
            or value != value.lower()
        ):
            raise ValueError(
                "RAG_TABLE_NAME must start with a lowercase letter and contain "
                "only lowercase letters, digits, and underscores"
            )
        return value

    @model_validator(mode="after")
    def validate_chunking(self) -> "RagSettings":
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        if self.rag_min_chunk_size > self.rag_chunk_size:
            raise ValueError("RAG_MIN_CHUNK_SIZE cannot exceed RAG_CHUNK_SIZE")
        if (
            self.embedding_model_name == DEFAULT_EMBEDDING_MODEL
            and not self.embedding_model_revision
        ):
            self.embedding_model_revision = DEFAULT_EMBEDDING_REVISION
        if (
            self.embedding_model_name != DEFAULT_EMBEDDING_MODEL
            and self.embedding_model_revision == DEFAULT_EMBEDDING_REVISION
        ):
            raise ValueError(
                "EMBEDDING_MODEL_REVISION is the default E5 commit but "
                "EMBEDDING_MODEL_NAME selects another model; configure that "
                "model's immutable revision and embedding dimension"
            )
        return self


@lru_cache
def get_rag_settings() -> RagSettings:
    """Return cached RAG settings."""

    return RagSettings()
