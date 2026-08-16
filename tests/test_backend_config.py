"""Tests for backend deployment settings and production validation."""

from __future__ import annotations

import asyncio
import logging

import pytest

import backend.main as backend_main
from backend.core.config import Settings


def test_development_settings_allow_optional_production_values_to_be_empty() -> None:
    settings = Settings(_env_file=None, app_env="development")

    settings.validate_production_settings()


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("database_url", "DATABASE_URL required in production"),
        ("openai_api_base", "OPENAI_API_BASE required in production"),
        ("cors_origins", "CORS_ORIGINS required in production"),
    ],
)
def test_production_settings_require_deployment_values(field: str, message: str) -> None:
    values = {
        "app_env": "production",
        "database_url": "postgresql://user:password@db.example/diu",
        "openai_api_base": "https://model.example/v1",
        "openai_api_key": "provider-secret",
        "model_name": "provider-model",
        "runtime_catalog_backend": "database",
        "rag_vector_backend": "pgvector",
        "embedding_backend": "openai",
        "embedding_api_base": "https://model.example/v1",
        "embedding_api_key": "embedding-secret",
        "embedding_api_model": "embedding-model",
        "cors_origins": "https://diu.example",
        field: "",
    }

    with pytest.raises(ValueError, match=message):
        Settings(_env_file=None, **values).validate_production_settings()


def test_blank_optional_values_are_normalized_to_none() -> None:
    settings = Settings(
        _env_file=None,
        database_url=" ",
        openai_api_base="",
        openai_api_key=" ",
        model_name="",
        embedding_model_name=" ",
        hf_token="",
    )

    assert settings.database_url is None
    assert settings.openai_api_base is None
    assert settings.openai_api_key is None
    assert settings.model_name is None
    assert settings.embedding_model_name is None
    assert settings.hf_token is None


def test_startup_validation_accepts_valid_production_settings(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://user:password@db.example/diu",
        openai_api_base="https://model.example/v1",
        openai_api_key="provider-secret",
        model_name="provider-model",
        runtime_catalog_backend="database",
        embedding_backend="openai",
        embedding_api_base="https://model.example/v1",
        embedding_api_key="embedding-secret",
        embedding_api_model="embedding-model",
        cors_origins="https://diu.example",
    )
    monkeypatch.setattr(backend_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        backend_main,
        "get_rag_settings",
        lambda: type("RagSettings", (), {"rag_vector_backend": "pgvector"})(),
    )

    asyncio.run(backend_main.startup_validation())


def test_production_startup_logs_success_without_secrets(monkeypatch, caplog) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://user:super-secret@db.example/diu",
        openai_api_base="https://model.example/v1",
        openai_api_key="api-secret",
        model_name="provider-model",
        runtime_catalog_backend="database",
        embedding_backend="openai",
        embedding_api_base="https://model.example/v1",
        embedding_api_key="embedding-secret",
        embedding_api_model="embedding-model",
        cors_origins="https://diu.example",
    )
    monkeypatch.setattr(backend_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        backend_main,
        "get_rag_settings",
        lambda: type("RagSettings", (), {"rag_vector_backend": "pgvector"})(),
    )

    with caplog.at_level(logging.INFO):
        asyncio.run(backend_main.startup_validation())

    output = caplog.text
    assert "[startup] Environment: production" in output
    assert "[startup] Database: PostgreSQL configured" in output
    assert "[startup] Model endpoint: Configured" in output
    assert "[startup] RAG backend: pgvector" in output
    assert "✅ All required production settings are configured" in output
    assert "super-secret" not in output
    assert "api-secret" not in output


def test_startup_logs_safe_runtime_statuses(monkeypatch, caplog) -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        cors_origins="http://localhost:3000",
    )
    monkeypatch.setattr(backend_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        backend_main,
        "get_rag_settings",
        lambda: type("RagSettings", (), {"rag_vector_backend": "local"})(),
    )

    with caplog.at_level(logging.INFO):
        asyncio.run(backend_main.startup_validation())

    output = caplog.text
    assert "[startup] Environment: development" in output
    assert "[startup] CORS origins: http://localhost:3000" in output
    assert "[startup] Database: not configured" in output
    assert "[startup] Model endpoint: not configured" in output
    assert "[startup] RAG backend: local" in output
    assert "Development mode: optional production settings are not required" in output
    assert "password" not in output.lower()


def test_startup_validation_rejects_incomplete_production_settings(monkeypatch) -> None:
    settings = Settings(_env_file=None, app_env="production")
    monkeypatch.setattr(backend_main, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="DATABASE_URL required in production"):
        asyncio.run(backend_main.startup_validation())


def test_production_requires_hosted_generator_backend() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://user:password@db.example/diu",
        generator_backend="local",
        generator_api_base="https://model.example/v1",
        cors_origins="https://diu.example",
    )

    with pytest.raises(ValueError, match="GENERATOR_BACKEND=openai"):
        settings.validate_production_settings()


def test_production_accepts_canonical_generator_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://user:password@db.example/diu",
        generator_backend="openai",
        generator_api_base="https://model.example/v1",
        generator_api_key="provider-secret",
        generator_api_model="provider-model",
        runtime_catalog_backend="database",
        embedding_backend="openai",
        embedding_api_base="https://model.example/v1",
        embedding_api_key="embedding-secret",
        embedding_api_model="embedding-model",
        cors_origins="https://diu.example",
    )

    settings.validate_production_settings()


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("generator_api_key", "GENERATOR_API_KEY required in production"),
        ("generator_api_model", "GENERATOR_API_MODEL required in production"),
    ],
)
def test_production_requires_hosted_generator_credentials(
    field: str, message: str
) -> None:
    values = {
        "app_env": "production",
        "database_url": "postgresql://user:password@db.example/diu",
        "generator_backend": "openai",
        "generator_api_base": "https://model.example/v1",
        "generator_api_key": "provider-secret",
        "generator_api_model": "provider-model",
        "runtime_catalog_backend": "database",
        "rag_vector_backend": "pgvector",
        "embedding_backend": "openai",
        "embedding_api_base": "https://model.example/v1",
        "embedding_api_key": "embedding-secret",
        "embedding_api_model": "embedding-model",
        "cors_origins": "https://diu.example",
        field: "",
    }

    with pytest.raises(ValueError, match=message):
        Settings(_env_file=None, **values).validate_production_settings()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("runtime_catalog_backend", "local", "RUNTIME_CATALOG_BACKEND=database"),
        ("rag_vector_backend", "local", "RAG_VECTOR_BACKEND=pgvector"),
        ("embedding_backend", "local", "EMBEDDING_BACKEND=openai"),
        ("embedding_api_base", "", "EMBEDDING_API_BASE required"),
        ("embedding_api_key", "", "EMBEDDING_API_KEY required"),
        ("embedding_api_model", "", "EMBEDDING_API_MODEL required"),
    ],
)
def test_production_requires_database_catalog_and_hosted_embeddings(
    field: str, value: str, message: str
) -> None:
    values = {
        "app_env": "production",
        "database_url": "postgresql://user:password@db.example/diu",
        "generator_backend": "openai",
        "generator_api_base": "https://model.example/v1",
        "generator_api_key": "provider-secret",
        "generator_api_model": "provider-model",
        "runtime_catalog_backend": "database",
        "rag_vector_backend": "pgvector",
        "embedding_backend": "openai",
        "embedding_api_base": "https://model.example/v1",
        "embedding_api_key": "embedding-secret",
        "embedding_api_model": "embedding-model",
        "cors_origins": "https://diu.example",
        field: value,
    }

    with pytest.raises(ValueError, match=message):
        Settings(_env_file=None, **values).validate_production_settings()
