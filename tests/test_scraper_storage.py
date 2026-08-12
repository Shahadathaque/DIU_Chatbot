"""Tests for immutable, content-addressed raw capture storage."""

import json
from pathlib import Path

import pytest

from scraper.exceptions import StorageError
from scraper.storage import RawStore
from scraper.utils import sha256_bytes


def test_store_success_deduplicates_content_and_preserves_provenance(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path / "raw")
    payload = b"<html><body>Admission information</body></html>"
    digest = sha256_bytes(payload)

    first = store.store_success(
        document_id="diu-adm-001-1111111111111111",
        content_hash=digest,
        raw_bytes=payload,
        content_kind="html",
        record={
            "document_id": "diu-adm-001-1111111111111111",
            "source_id": "DIU-ADM-001",
            "content_hash": digest,
        },
    )
    second = store.store_success(
        document_id="diu-not-002-2222222222222222",
        content_hash=digest,
        raw_bytes=payload,
        content_kind="html",
        record={
            "document_id": "diu-not-002-2222222222222222",
            "source_id": "DIU-NOT-002",
            "content_hash": digest,
        },
    )

    assert first.duplicate_content is False
    assert second.duplicate_content is True
    assert first.raw_path == second.raw_path
    assert first.record_path != second.record_path
    stored = json.loads((store.root / second.record_path).read_text(encoding="utf-8"))
    assert stored["source_id"] == "DIU-NOT-002"
    assert stored["raw_path"] == second.raw_path


def test_existing_document_hash_record_is_not_overwritten(tmp_path: Path) -> None:
    store = RawStore(tmp_path / "raw")
    payload = b"same bytes"
    digest = sha256_bytes(payload)

    first = store.store_success(
        document_id="diu-adm-001-1111111111111111",
        content_hash=digest,
        raw_bytes=payload,
        content_kind="html",
        record={
            "document_id": "diu-adm-001-1111111111111111",
            "content_hash": digest,
            "retrieved_at": "first",
        },
    )
    second = store.store_success(
        document_id="diu-adm-001-1111111111111111",
        content_hash=digest,
        raw_bytes=payload,
        content_kind="html",
        record={
            "document_id": "diu-adm-001-1111111111111111",
            "content_hash": digest,
            "retrieved_at": "second",
        },
    )

    stored = json.loads((store.root / first.record_path).read_text(encoding="utf-8"))
    assert second.duplicate_record is True
    assert stored["retrieved_at"] == "first"


def test_existing_json_collision_with_different_identity_is_rejected(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path / "raw")
    payload = b"same bytes"
    digest = sha256_bytes(payload)
    outcome = store.store_success(
        document_id="diu-adm-001-1111111111111111",
        content_hash=digest,
        raw_bytes=payload,
        content_kind="html",
        record={
            "document_id": "diu-adm-001-1111111111111111",
            "content_hash": digest,
        },
    )
    path = store.root / outcome.record_path
    path.write_text('{"document_id":"wrong","content_hash":"wrong"}\n')

    with pytest.raises(StorageError, match="identity differs"):
        store.store_success(
            document_id="diu-adm-001-1111111111111111",
            content_hash=digest,
            raw_bytes=payload,
            content_kind="html",
            record={
                "document_id": "diu-adm-001-1111111111111111",
                "content_hash": digest,
            },
        )


def test_store_rejects_invalid_content_hash(tmp_path: Path) -> None:
    store = RawStore(tmp_path / "raw")

    with pytest.raises(StorageError, match="SHA-256"):
        store.store_success(
            document_id="diu-adm-001-1111111111111111",
            content_hash="../unsafe",
            raw_bytes=b"data",
            content_kind="binary",
            record={},
        )


def test_store_recomputes_hash_and_rejects_mismatch(tmp_path: Path) -> None:
    store = RawStore(tmp_path / "raw")

    with pytest.raises(StorageError, match="does not match"):
        store.store_success(
            document_id="diu-adm-001-1111111111111111",
            content_hash="0" * 64,
            raw_bytes=b"different",
            content_kind="html",
            record={},
        )
