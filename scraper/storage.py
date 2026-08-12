"""Append-only storage for raw scraper captures and provenance records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from scraper.exceptions import StorageError
from scraper.utils import safe_identifier
from scraper.utils import sha256_bytes


@dataclass(frozen=True)
class StorageOutcome:
    """Paths and duplicate information produced by a successful store."""

    raw_path: str
    record_path: str
    duplicate_content: bool
    duplicate_record: bool


class RawStore:
    """Write content-addressed captures without modifying existing raw files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def prepare(self) -> None:
        """Create the Phase 4 raw-data layout."""

        for relative in (
            "content/sha256",
            "records",
            "failures",
            "runs",
            "logs",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)

    def has_successful_capture(self, document_id: str) -> bool:
        """Return whether this source already has an immutable success record."""

        document_dir = self.root / "records" / safe_identifier(document_id)
        return document_dir.is_dir() and any(document_dir.glob("*.json"))

    def store_success(
        self,
        *,
        document_id: str,
        content_hash: str,
        raw_bytes: bytes,
        content_kind: str,
        record: Dict[str, Any],
    ) -> StorageOutcome:
        """Store a raw payload once and a provenance record once per source/hash."""

        self.prepare()
        digest = _validate_sha256(content_hash)
        _content_location(content_kind)
        actual_digest = sha256_bytes(raw_bytes)
        if actual_digest != digest:
            raise StorageError(
                f"content_hash does not match raw bytes: expected {digest}, got {actual_digest}"
            )
        raw_relative = Path("content") / "sha256" / digest
        raw_path = self.root / raw_relative
        duplicate_content = raw_path.exists()
        _write_bytes_immutable(raw_path, raw_bytes)

        document_key = safe_identifier(document_id, max_length=120)
        record_relative = Path("records") / document_key / f"{digest}.json"
        record_path = self.root / record_relative
        duplicate_record = record_path.exists()

        stored_record = dict(record)
        stored_record["raw_path"] = raw_relative.as_posix()
        if duplicate_record:
            _verify_existing_record(
                record_path,
                document_id=document_id,
                content_hash=digest,
            )
        else:
            _write_json_immutable(record_path, stored_record)

        return StorageOutcome(
            raw_path=raw_relative.as_posix(),
            record_path=record_relative.as_posix(),
            duplicate_content=duplicate_content,
            duplicate_record=duplicate_record,
        )

    def store_failure(
        self, *, run_id: str, document_id: str, failure: Dict[str, Any]
    ) -> str:
        """Store one concise failure record for a source in a run."""

        self.prepare()
        relative = (
            Path("failures")
            / safe_identifier(run_id)
            / f"{safe_identifier(document_id, max_length=120)}.json"
        )
        _write_json_immutable(self.root / relative, failure)
        return relative.as_posix()

    def store_manifest(self, *, run_id: str, manifest: Dict[str, Any]) -> str:
        """Persist a completed run manifest once."""

        self.prepare()
        relative = Path("runs") / f"{safe_identifier(run_id)}.json"
        _write_json_immutable(self.root / relative, manifest)
        return relative.as_posix()

    def log_path(self, run_id: str) -> Path:
        """Return a safe path for the run log, creating its parent directory."""

        self.prepare()
        return self.root / "logs" / f"{safe_identifier(run_id)}.log"


def _content_location(content_kind: str) -> str:
    normalized = content_kind.strip().lower()
    if normalized == "html":
        return "html"
    if normalized == "pdf":
        return "pdf"
    if normalized == "binary":
        return "binary"
    raise StorageError(f"Unsupported raw content kind: {content_kind!r}")


def _validate_sha256(value: str) -> str:
    digest = value.strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise StorageError("content_hash must be a 64-character SHA-256 hex digest")
    return digest


def _write_bytes_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise StorageError(f"Existing content-addressed file differs: {path}")


def _write_json_immutable(path: Path, value: Dict[str, Any]) -> None:
    serialized = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(serialized)
    except FileExistsError:
        if path.read_bytes() != serialized:
            raise StorageError(f"Existing immutable JSON differs: {path}")


def _verify_existing_record(
    path: Path, *, document_id: str, content_hash: str
) -> None:
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StorageError(f"Existing record is unreadable: {path}") from error
    if (
        existing.get("document_id") != document_id
        or existing.get("content_hash") != content_hash
    ):
        raise StorageError(f"Existing record identity differs: {path}")
