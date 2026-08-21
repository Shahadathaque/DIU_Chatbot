"""Environment-driven configuration for DIU knowledge retrieval."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
DEFAULT_EMBEDDING_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
DEFAULT_EMBEDDING_DIMENSION = 768
DEFAULT_GENERATOR_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class RagSettings(BaseSettings):
    """RAG settings loaded from environment variables or the root ``.env``."""

    database_url: Optional[str] = None
    db_pool_min_size: int = Field(1, ge=1, le=10)
    db_pool_max_size: int = Field(4, ge=1, le=20)
    db_pool_timeout: float = Field(10.0, gt=0, le=60.0)
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL
    embedding_model_revision: Optional[str] = None
    embedding_dimension: int = Field(DEFAULT_EMBEDDING_DIMENSION, ge=1)
    embedding_batch_size: int = Field(16, ge=1)
    embedding_device: Optional[str] = None
    embedding_backend: Literal["local", "openai"] = "local"
    embedding_api_base: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_api_model: Optional[str] = None
    embedding_api_timeout: float = Field(30.0, gt=0, le=120.0)
    embedding_api_request_interval: float = Field(0.0, ge=0.0, le=60.0)
    embedding_api_max_retries: int = Field(2, ge=0, le=5)
    embedding_api_retry_backoff: float = Field(0.5, ge=0.0, le=30.0)
    embedding_api_send_dimensions: bool = True

    rag_vector_backend: Literal["pgvector", "local"] = "pgvector"
    rag_table_name: str = "diu_knowledge_chunks"
    rag_local_store_path: Path = PROJECT_ROOT / "data/chunks/local_knowledge_base.json"
    rag_cleaned_data_path: Path = PROJECT_ROOT / "data/cleaned/v2"

    rag_chunk_size: int = Field(1200, ge=300)
    rag_chunk_overlap: int = Field(150, ge=0)
    rag_min_chunk_size: int = Field(100, ge=1)
    rag_min_similarity_score: float = Field(0.75, ge=-1.0, le=1.0)
    rag_min_relevance_score: float = Field(0.72, ge=-1.0, le=1.0)
    rag_candidate_multiplier: int = Field(5, ge=1, le=20)
    rag_max_results_per_source: int = Field(5, ge=1, le=20)
    # Disabled by default for free deployments; enabling it downloads another
    # model and should be followed by a measured held-out evaluation.
    rag_reranker_enabled: bool = False
    rag_reranker_model_name: str = DEFAULT_RERANKER_MODEL

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "database_url",
        "embedding_model_revision",
        "embedding_device",
        "embedding_api_base",
        "embedding_api_key",
        "embedding_api_model",
        mode="before",
    )
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
        if self.db_pool_max_size < self.db_pool_min_size:
            raise ValueError("DB_POOL_MAX_SIZE cannot be smaller than DB_POOL_MIN_SIZE")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        if self.rag_min_chunk_size > self.rag_chunk_size:
            raise ValueError("RAG_MIN_CHUNK_SIZE cannot exceed RAG_CHUNK_SIZE")
        if self.embedding_backend == "openai":
            if not self.embedding_api_base:
                raise ValueError(
                    "EMBEDDING_API_BASE is required when EMBEDDING_BACKEND=openai"
                )
            if not self.embedding_api_model:
                raise ValueError(
                    "EMBEDDING_API_MODEL is required when EMBEDDING_BACKEND=openai"
                )
            self.embedding_model_name = self.embedding_api_model
            # Hosted providers usually expose a versioned model name instead of
            # an immutable Hugging Face commit.
            if self.embedding_model_revision == DEFAULT_EMBEDDING_REVISION:
                self.embedding_model_revision = None
        elif (
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


class GeneratorSettings(BaseSettings):
    """LLM generator configuration loaded from environment or the root ``.env``."""

    generator_backend: Literal["local", "openai"] = "local"
    generator_model_name: str = DEFAULT_GENERATOR_MODEL
    generator_model_revision: Optional[str] = None
    generator_device: Optional[str] = None
    # Keep hosted/local responses bounded so free deployments do not spend
    # unbounded tokens on a single request.
    generator_max_new_tokens: int = Field(384, ge=1, le=512)
    generator_temperature: float = Field(0.0, ge=0.0, le=2.0)
    generator_top_p: float = Field(0.9, ge=0.0, le=1.0)
    generator_api_base: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "generator_api_base", "GENERATOR_API_BASE", "OPENAI_API_BASE"
        ),
    )
    generator_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "generator_api_key", "GENERATOR_API_KEY", "OPENAI_API_KEY"
        ),
    )
    generator_api_model: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "generator_api_model", "GENERATOR_API_MODEL", "MODEL_NAME"
        ),
    )
    generator_api_reasoning_effort: Optional[
        Literal["none", "minimal", "low", "medium", "high"]
    ] = None
    generator_api_max_retries: int = Field(2, ge=0, le=5)
    generator_api_retry_backoff: float = Field(0.5, ge=0.0, le=30.0)
    generator_lora_adapter: Optional[Path] = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "generator_model_revision",
        "generator_device",
        "generator_api_base",
        "generator_api_key",
        "generator_api_model",
        "generator_api_reasoning_effort",
        "generator_lora_adapter",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("generator_model_name", mode="before")
    @classmethod
    def blank_model_uses_default(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return DEFAULT_GENERATOR_MODEL
        return value

    @field_validator("generator_lora_adapter")
    @classmethod
    def resolve_lora_adapter_from_project_root(cls, value: Optional[Path]) -> Optional[Path]:
        if value is None:
            return None
        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @field_validator("generator_max_new_tokens")
    @classmethod
    def reject_blank_max_new_tokens(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("GENERATOR_MAX_NEW_TOKENS cannot be blank")
        return value

    @model_validator(mode="before")
    @classmethod
    def legacy_openai_env_selects_hosted_backend(cls, values: Any) -> Any:
        """Keep older OPENAI_* deployments on the hosted adapter."""

        if isinstance(values, dict):
            legacy_base = (
                values.get("openai_api_base")
                or values.get("OPENAI_API_BASE")
                or values.get("generator_api_base")
            )
            explicit_backend = values.get("generator_backend") or values.get(
                "GENERATOR_BACKEND"
            )
            if legacy_base and not explicit_backend:
                values = dict(values)
                values["generator_backend"] = "openai"
        return values


@lru_cache
def get_rag_settings() -> RagSettings:
    """Return cached RAG settings."""

    return RagSettings()


@lru_cache
def get_generator_settings() -> GeneratorSettings:
    """Return cached generator settings."""

    return GeneratorSettings()
