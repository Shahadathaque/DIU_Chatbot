#!/usr/bin/env python3
"""Validate one immutable raw-dataset snapshot against the source registry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.registry import load_registry  # noqa: E402
from scraper.utils import sha256_bytes  # noqa: E402


VALIDATOR_VERSION = "phase4.1-1.0"
REQUIRED_RECORD_FIELDS = frozenset(
    {
        "document_id",
        "source_id",
        "source_url",
        "canonical_url",
        "title",
        "category",
        "priority",
        "dynamic_page",
        "date_sensitive",
        "currency_status",
        "scrape_status",
        "retrieved_at",
        "attempted_at",
        "run_id",
        "collector_version",
        "raw_dataset_version",
        "content_type",
        "mime_type",
        "fetch_method",
        "capture_representation",
        "content_hash",
        "raw_content_hash",
        "hash_algorithm",
        "http_status",
        "response_bytes",
        "response_headers",
        "attempts",
        "raw_path",
    }
)
REQUIRED_FAILURE_FIELDS = frozenset(
    {
        "document_id",
        "source_id",
        "source_url",
        "canonical_url",
        "title",
        "category",
        "attempted_at",
        "retrieved_at",
        "run_id",
        "collector_version",
        "raw_dataset_version",
        "fetch_method",
        "error_type",
        "error_message",
        "attempts",
    }
)
PROHIBITED_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-csrf-token",
        "x-xsrf-token",
    }
)
LOCAL_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)")
TOKEN_PATTERN = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/=-]{12,}|"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|private[_-]?key|"
    r"csrf[_-]?token|xsrf[_-]?token)"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "data/source_registry.csv",
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument(
        "--report",
        type=Path,
        help="optional immutable JSON validation report path",
    )
    parser.add_argument(
        "--short-text-threshold",
        type=int,
        default=200,
        help="flag non-PDF extracted text shorter than this many characters",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_dataset(
        output_root=args.output_root,
        registry_path=args.registry,
        dataset_version=args.dataset_version,
        short_text_threshold=args.short_text_threshold,
    )
    if args.report:
        _write_json_immutable(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["errors"] else 0


def validate_dataset(
    *,
    output_root: Path,
    registry_path: Path,
    dataset_version: str,
    short_text_threshold: int = 200,
) -> dict[str, Any]:
    """Return a machine-readable integrity and coverage report."""

    root = output_root.resolve()
    sources = {source.source_id: source for source in load_registry(registry_path)}
    errors: list[str] = []
    warnings: list[str] = []
    manifests = []
    for path in sorted((root / "runs").glob("*.json")):
        value = _read_json(path, errors)
        if value and value.get("raw_dataset_version") == dataset_version:
            manifests.append((path, value))
    if len(manifests) != 1:
        errors.append(
            f"expected exactly one manifest for dataset {dataset_version!r}; found {len(manifests)}"
        )
        manifest_path = None
        manifest: dict[str, Any] = {}
    else:
        manifest_path, manifest = manifests[0]

    run = manifest.get("run", {}) if isinstance(manifest, dict) else {}
    results = run.get("results", []) if isinstance(run, dict) else []
    if not isinstance(results, list):
        errors.append("manifest run.results is not a list")
        results = []

    records = []
    failures = []
    document_ids: dict[str, str] = {}
    hash_sources: dict[str, list[str]] = defaultdict(list)
    source_counts: Counter[str] = Counter()
    content_type_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    suspicious_short = []

    for result in results:
        if not isinstance(result, dict):
            errors.append("manifest contains a non-object result")
            continue
        source_id = str(result.get("source_id", ""))
        source = sources.get(source_id)
        if source is None:
            errors.append(f"manifest result has unknown source_id {source_id!r}")
            continue
        if result.get("source_url") != source.url:
            errors.append(f"{source_id}: manifest URL does not match registry")
        status = result.get("status")
        relative_key = "record_path" if status == "successful" else "failure_path"
        if status not in {"successful", "failed", "skipped_existing"}:
            errors.append(f"{source_id}: unsupported result status {status!r}")
            continue
        if status == "skipped_existing":
            warnings.append(f"{source_id}: dataset manifest used an existing capture")
            continue
        artifact_path = _safe_child(root, result.get(relative_key), errors, source_id)
        if artifact_path is None:
            continue
        artifact = _read_json(artifact_path, errors)
        if not artifact:
            continue
        if artifact.get("raw_dataset_version") != dataset_version:
            errors.append(f"{source_id}: artifact dataset version mismatch")
        if artifact.get("source_id") != source_id or artifact.get("source_url") != source.url:
            errors.append(f"{source_id}: artifact identity does not match registry")
        if artifact.get("document_id") != source.document_id:
            errors.append(f"{source_id}: document_id does not match registry identity")
        document_id = str(artifact.get("document_id", ""))
        prior_source = document_ids.get(document_id)
        if prior_source and prior_source != source_id:
            errors.append(
                f"duplicate document_id {document_id!r}: {prior_source}, {source_id}"
            )
        document_ids[document_id] = source_id

        serialized = json.dumps(artifact, ensure_ascii=False)
        if LOCAL_PATH_PATTERN.search(serialized):
            errors.append(f"{source_id}: artifact contains an absolute local user path")
        if TOKEN_PATTERN.search(serialized):
            errors.append(f"{source_id}: artifact contains a secret/token-like value")

        if status == "failed":
            missing = sorted(REQUIRED_FAILURE_FIELDS - set(artifact))
            if missing:
                errors.append(f"{source_id}: failure missing fields: {', '.join(missing)}")
            failures.append(artifact)
            source_counts["failed"] += 1
            continue

        missing = sorted(REQUIRED_RECORD_FIELDS - set(artifact))
        if missing:
            errors.append(f"{source_id}: record missing fields: {', '.join(missing)}")
        headers = artifact.get("response_headers", {})
        if not isinstance(headers, dict):
            errors.append(f"{source_id}: response_headers is not an object")
        elif PROHIBITED_HEADER_NAMES.intersection(key.casefold() for key in headers):
            errors.append(f"{source_id}: prohibited credential/session header persisted")

        raw_path = _safe_child(root, artifact.get("raw_path"), errors, source_id)
        if raw_path is not None and raw_path.is_file():
            raw_bytes = raw_path.read_bytes()
            digest = sha256_bytes(raw_bytes)
            if digest != artifact.get("raw_content_hash") or digest != artifact.get(
                "content_hash"
            ):
                errors.append(f"{source_id}: raw SHA-256 mismatch")
            if len(raw_bytes) != artifact.get("response_bytes"):
                errors.append(f"{source_id}: recorded response byte count mismatch")
            if artifact.get("content_type") != "pdf":
                raw_text = raw_bytes.decode("utf-8", errors="replace")
                if LOCAL_PATH_PATTERN.search(raw_text):
                    errors.append(
                        f"{source_id}: raw payload contains an absolute local user path"
                    )
                if TOKEN_PATTERN.search(raw_text):
                    errors.append(
                        f"{source_id}: raw payload contains a secret/token-like value"
                    )
            hash_sources[digest].append(source_id)
        elif raw_path is not None:
            errors.append(f"{source_id}: raw payload is missing")

        content = artifact.get("content")
        if (
            artifact.get("content_type") != "pdf"
            and (not isinstance(content, str) or len(content.strip()) < short_text_threshold)
        ):
            suspicious_short.append(
                {
                    "source_id": source_id,
                    "text_characters": len(content.strip()) if isinstance(content, str) else 0,
                }
            )
        records.append(artifact)
        source_counts["successful"] += 1
        content_type_counts[str(artifact.get("content_type"))] += 1
        category_counts[str(artifact.get("category"))] += 1

    _validate_manifest_arithmetic(run, errors)
    duplicate_hashes = [
        {"content_hash": digest, "source_ids": sorted(source_ids)}
        for digest, source_ids in sorted(hash_sources.items())
        if len(source_ids) > 1
    ]
    if duplicate_hashes:
        warnings.append(
            f"found {len(duplicate_hashes)} raw content hash shared by multiple sources"
        )
    if suspicious_short:
        warnings.append(
            f"flagged {len(suspicious_short)} non-PDF record(s) below the short-text threshold"
        )

    return {
        "validator_version": VALIDATOR_VERSION,
        "validated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_dataset_version": dataset_version,
        "integrity_status": "passed" if not errors else "failed",
        "dataset_status": manifest.get("dataset_status"),
        "manifest_path": (
            manifest_path.relative_to(root).as_posix() if manifest_path else None
        ),
        "registry_hash": (
            sha256_bytes(registry_path.read_bytes()) if registry_path.is_file() else None
        ),
        "collector_tree_hash": manifest.get("collector_tree_hash"),
        "code_revision": manifest.get("code_revision"),
        "code_worktree_dirty": manifest.get("code_worktree_dirty"),
        "counts": {
            "selected": run.get("selected", 0),
            "attempted": run.get("attempted", 0),
            "successful": source_counts["successful"],
            "failed": source_counts["failed"],
            "skipped": run.get("skipped", 0),
        },
        "source_ids": sorted(document_ids.values()),
        "content_types": dict(sorted(content_type_counts.items())),
        "categories": dict(sorted(category_counts.items())),
        "duplicate_content_hashes": duplicate_hashes,
        "suspicious_short_documents": suspicious_short,
        "privacy_checks": {
            "prohibited_headers_absent": not any(
                "header" in error for error in errors
            ),
            "secret_token_patterns_absent": not any(
                "secret/token" in error for error in errors
            ),
            "absolute_local_user_paths_absent": not any(
                "local user path" in error for error in errors
            ),
        },
        "errors": errors,
        "warnings": warnings,
    }


def _safe_child(
    root: Path, value: object, errors: list[str], source_id: str
) -> Optional[Path]:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        errors.append(f"{source_id}: artifact path is missing or non-portable")
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        errors.append(f"{source_id}: artifact path escapes output root")
        return None
    return candidate


def _read_json(path: Path, errors: list[str]) -> Optional[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(f"invalid JSON {path.name}: {type(error).__name__}")
        return None
    if not isinstance(value, dict):
        errors.append(f"JSON artifact is not an object: {path.name}")
        return None
    return value


def _validate_manifest_arithmetic(run: dict[str, Any], errors: list[str]) -> None:
    attempted = run.get("attempted")
    successful = run.get("successful")
    failed = run.get("failed")
    selected = run.get("selected")
    skipped = run.get("skipped")
    if not all(
        isinstance(value, int)
        for value in (attempted, successful, failed, selected, skipped)
    ):
        errors.append("manifest count fields are not all integers")
        return
    if attempted != successful + failed:
        errors.append("manifest arithmetic failed: attempted != successful + failed")
    if selected != attempted + skipped:
        errors.append("manifest arithmetic failed: selected != attempted + skipped")
    type_total = sum(
        run.get(name, 0) for name in ("html", "pdf", "binary")
    )
    if type_total != successful:
        errors.append("manifest arithmetic failed: content types != successful")


def _write_json_immutable(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError as error:
        raise SystemExit(f"validation report already exists: {path}") from error


if __name__ == "__main__":
    raise SystemExit(main())
