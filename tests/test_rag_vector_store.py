from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.config import DEFAULT_EMBEDDING_REVISION, PROJECT_ROOT, RagSettings
from rag.vector_store import (
    LocalVectorStore,
    PgVectorStore,
    VectorStoreConfigurationError,
    create_vector_store,
)
from tests.rag_helpers import knowledge_chunk


def test_pgvector_requires_immutable_commit_revision_in_every_factory_path() -> None:
    with pytest.raises(VectorStoreConfigurationError, match="40-character"):
        PgVectorStore(
            "postgresql://example.invalid/diu",
            embedding_dimension=3,
            embedding_model_name="example/model",
            embedding_model_revision=None,
        )

    settings = RagSettings(
        _env_file=None,
        database_url="postgresql://example.invalid/diu",
        embedding_model_name="example/model",
        embedding_model_revision="main",
        embedding_dimension=3,
    )
    with pytest.raises(VectorStoreConfigurationError, match="40-character"):
        create_vector_store(settings)

    store = PgVectorStore(
        "postgresql://example.invalid/diu",
        embedding_dimension=768,
        embedding_model_name="intfloat/multilingual-e5-base",
        embedding_model_revision=DEFAULT_EMBEDDING_REVISION,
    )
    assert store.embedding_model_revision == DEFAULT_EMBEDDING_REVISION


def test_pgvector_accepts_provider_versioned_hosted_embedding_model() -> None:
    settings = RagSettings(
        _env_file=None,
        database_url="postgresql://example.invalid/diu",
        embedding_backend="openai",
        embedding_api_base="https://model.example/v1",
        embedding_api_model="gemini-embedding-2",
        embedding_dimension=768,
    )

    store = create_vector_store(settings)

    assert isinstance(store, PgVectorStore)
    assert store.embedding_model_name == "gemini-embedding-2"
    assert store.embedding_model_revision is None


def test_pgvector_pool_checks_idle_connections_before_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_with = {}
    connection_context = object()

    class FakeConnectionPool:
        @staticmethod
        def check_connection(_connection) -> None:
            return None

        def __init__(self, **kwargs) -> None:
            created_with.update(kwargs)

        def connection(self):
            return connection_context

    monkeypatch.setitem(
        sys.modules,
        "psycopg_pool",
        SimpleNamespace(ConnectionPool=FakeConnectionPool),
    )
    store = PgVectorStore(
        "postgresql://example.invalid/diu",
        embedding_dimension=3,
        embedding_model_name="example/model",
        embedding_model_revision="a" * 40,
    )

    result = store._connection(SimpleNamespace(), object())

    assert result is connection_context
    assert created_with["check"] is FakeConnectionPool.check_connection


def test_table_names_are_lowercase_for_safe_regclass_lookup() -> None:
    with pytest.raises(ValueError, match="lowercase"):
        RagSettings(_env_file=None, rag_table_name="DIU_Chunks")
    with pytest.raises(VectorStoreConfigurationError, match="lowercase"):
        PgVectorStore(
            "postgresql://example.invalid/diu",
            table_name="DIU_Chunks",
            embedding_dimension=3,
            embedding_model_name="example/model",
            embedding_model_revision="a" * 40,
        )


def test_relative_environment_paths_resolve_from_project_root() -> None:
    settings = RagSettings(
        _env_file=None,
        rag_cleaned_data_path=Path("data/example-cleaned"),
        rag_local_store_path=Path("data/example-store.json"),
    )

    assert settings.rag_cleaned_data_path == PROJECT_ROOT / "data/example-cleaned"
    assert settings.rag_local_store_path == PROJECT_ROOT / "data/example-store.json"


def test_local_rebuild_validates_before_replacing_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    store = LocalVectorStore(
        path,
        embedding_dimension=2,
        embedding_model_name="fixture-model",
        embedding_model_revision="fixture-revision",
    )
    original = knowledge_chunk("original")
    store.upsert_chunks([original], [[1.0, 0.0]])
    original_file = path.read_bytes()

    with pytest.raises(ValueError, match="same length"):
        store.upsert_chunks(
            [knowledge_chunk("replacement")], [], rebuild=True
        )

    assert path.read_bytes() == original_file
    assert store.count() == 1
    assert store.search([1.0, 0.0])[0].chunk.chunk_id == "original"


def test_local_rebuild_restores_memory_and_file_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "store.json"
    store = LocalVectorStore(
        path,
        embedding_dimension=2,
        embedding_model_name="fixture-model",
        embedding_model_revision="fixture-revision",
    )
    store.upsert_chunks([knowledge_chunk("original")], [[1.0, 0.0]])
    original_file = path.read_bytes()

    def fail_write() -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(store, "_write_file", fail_write)
    with pytest.raises(OSError, match="simulated write failure"):
        store.upsert_chunks(
            [knowledge_chunk("replacement")], [[0.0, 1.0]], rebuild=True
        )

    assert path.read_bytes() == original_file
    assert store.count() == 1
    assert store.search([1.0, 0.0])[0].chunk.chunk_id == "original"
