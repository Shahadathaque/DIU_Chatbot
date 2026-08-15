from __future__ import annotations

from pathlib import Path

import pytest

from rag.config import RagSettings
from scripts import build_knowledge_base as builder
from tests.rag_helpers import cleaned_record, write_cleaned_dataset


def _settings(tmp_path: Path) -> RagSettings:
    return RagSettings(
        _env_file=None,
        rag_vector_backend="local",
        rag_local_store_path=tmp_path / "must-not-be-created.json",
        embedding_dimension=2,
        rag_chunk_size=300,
        rag_chunk_overlap=30,
        rag_min_chunk_size=20,
    )


def test_dry_run_honors_limit_without_loading_model_or_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        cleaned_record(
            source_id="DIU-TEST-001",
            content="Current DIU admission requirements and application details.",
        ),
        cleaned_record(
            source_id="DIU-TEST-002",
            content="DIU tuition, scholarship, and waiver information.",
            category="tuition_and_fees",
        ),
    ]
    root = write_cleaned_dataset(tmp_path / "cleaned", records)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("dry-run must not initialize embeddings or storage")

    monkeypatch.setattr(builder, "create_embedder", forbidden)
    monkeypatch.setattr(builder, "create_vector_store", forbidden)
    report = builder.build_knowledge_base(
        cleaned_root=root,
        limit=1,
        dry_run=True,
        settings=_settings(tmp_path),
    )

    assert report["documents"] == 1
    assert report["chunks"] >= 1
    assert report["stored"] is False
    assert report["dry_run"] is True
    assert not (tmp_path / "must-not-be-created.json").exists()


def test_rebuild_rejects_partial_limit_before_reading_or_mutating(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--rebuild cannot be combined with --limit"):
        builder.build_knowledge_base(
            cleaned_root=tmp_path / "missing-dataset",
            limit=1,
            rebuild=True,
            settings=_settings(tmp_path),
        )


def test_missing_production_database_fails_before_model_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = write_cleaned_dataset(tmp_path / "cleaned", [cleaned_record()])
    settings = RagSettings(
        _env_file=None,
        database_url=None,
        rag_vector_backend="pgvector",
        embedding_dimension=2,
        rag_chunk_size=300,
        rag_chunk_overlap=30,
        rag_min_chunk_size=20,
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("model must not load before database configuration")

    monkeypatch.setattr(builder, "create_embedder", forbidden)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        builder.build_knowledge_base(cleaned_root=root, settings=settings)


def test_mutating_build_rejects_empty_manifest_before_storage_or_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = write_cleaned_dataset(tmp_path / "cleaned", [])

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("empty builds must fail before model or storage setup")

    monkeypatch.setattr(builder, "create_embedder", forbidden)
    monkeypatch.setattr(builder, "create_vector_store", forbidden)

    with pytest.raises(ValueError, match="zero records"):
        builder.build_knowledge_base(
            cleaned_root=root,
            rebuild=True,
            settings=_settings(tmp_path),
        )
    assert not (tmp_path / "must-not-be-created.json").exists()


def test_mutating_build_rejects_zero_chunks_before_storage_or_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = write_cleaned_dataset(tmp_path / "cleaned", [cleaned_record()])

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("empty builds must fail before model or storage setup")

    monkeypatch.setattr(builder, "chunk_records", lambda *args, **kwargs: [])
    monkeypatch.setattr(builder, "create_embedder", forbidden)
    monkeypatch.setattr(builder, "create_vector_store", forbidden)

    with pytest.raises(ValueError, match="zero chunks"):
        builder.build_knowledge_base(cleaned_root=root, settings=_settings(tmp_path))
    assert not (tmp_path / "must-not-be-created.json").exists()
