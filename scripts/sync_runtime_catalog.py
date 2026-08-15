#!/usr/bin/env python3
"""Synchronize API runtime programs and sources from a validated snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import Settings  # noqa: E402
from backend.repositories.runtime_catalog import (  # noqa: E402
    RuntimeCatalogMetadata,
    RuntimeCatalogRepository,
)
from backend.services.programs_service import ProgramsService  # noqa: E402
from backend.services.sources_service import SourcesService  # noqa: E402
from rag.chunker import load_cleaned_records  # noqa: E402
from rag.config import RagSettings  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleaned-root", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and derive rows without connecting to PostgreSQL.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = synchronize_runtime_catalog(
            cleaned_root=args.cleaned_root,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(
            f"sync_runtime_catalog: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def synchronize_runtime_catalog(
    *,
    cleaned_root: Optional[Path] = None,
    dry_run: bool = False,
    database_url: Optional[str] = None,
    repository: Optional[RuntimeCatalogRepository] = None,
) -> Dict[str, Any]:
    """Validate, derive, and transactionally synchronize the runtime catalog."""

    rag_settings = RagSettings()
    root = Path(cleaned_root or rag_settings.rag_cleaned_data_path).resolve()
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("cleaned manifest must be an object")
    records = load_cleaned_records(root)
    program_models = ProgramsService(records=records).list_programs().programs
    source_models = SourcesService(records=records).list_sources().sources

    programs = [_program_row(program.model_dump(), records) for program in program_models]
    sources = [_source_row(source.model_dump(), records) for source in source_models]
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    metadata = RuntimeCatalogMetadata(
        dataset_version=str(
            manifest.get("raw_dataset_version")
            or manifest.get("cleaned_dataset_version")
            or "unknown"
        ),
        dataset_fingerprint=str(
            manifest.get("raw_dataset_fingerprint")
            or manifest.get("quality_report_hash")
            or manifest_hash
        ),
        manifest_hash=manifest_hash,
        program_count=len(programs),
        source_count=len(sources),
    )
    result: Dict[str, Any] = {
        "cleaned_root": str(root),
        "dataset_version": metadata.dataset_version,
        "dataset_fingerprint": metadata.dataset_fingerprint,
        "manifest_hash": metadata.manifest_hash,
        "programs": metadata.program_count,
        "sources": metadata.source_count,
        "dry_run": dry_run,
        "synchronized": False,
    }
    if dry_run:
        return result

    resolved_repository = repository
    if resolved_repository is None:
        resolved_url = database_url or Settings().database_url
        if not resolved_url:
            raise ValueError("DATABASE_URL is required to synchronize the runtime catalog")
        resolved_repository = RuntimeCatalogRepository(resolved_url)
    resolved_repository.synchronize(
        programs=programs,
        sources=sources,
        metadata=metadata,
    )
    result["synchronized"] = True
    return result


def _program_row(
    program: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    record = _program_provenance_record(program, records)
    return {
        **dict(program),
        "source_id": str(record["source_id"]),
        "source_url": str(record["source_url"]),
        "retrieved_at": record.get("retrieved_at"),
        "document_id": str(record["document_id"]),
        "document_hash": str(record["cleaned_content_hash"]),
        "content_hash": str(record["cleaned_content_hash"]),
        "provenance": {
            "raw_content_hash": record.get("raw_content_hash"),
            "cleaned_content_hash": record.get("cleaned_content_hash"),
            "category": record.get("category"),
        },
    }


def _program_provenance_record(
    program: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    name = str(program["name"]).casefold()
    admission_url = str(program.get("admission_url") or "")
    candidates = [
        record
        for record in records
        if record.get("category")
        in {"undergraduate_programs", "program_specific_admission"}
    ]
    for record in candidates:
        if admission_url and record.get("source_url") == admission_url:
            return record
        if str(record.get("program") or "").casefold() == name:
            return record
        for table in record.get("tables", []):
            headers = [str(value).strip().casefold() for value in table.get("headers", [])]
            if "full program name" not in headers:
                continue
            name_index = headers.index("full program name")
            if any(
                len(row) > name_index and str(row[name_index]).strip().casefold() == name
                for row in table.get("rows", [])
            ):
                return record
    raise ValueError(f"no cleaned-record provenance found for program {program['name']!r}")


def _source_row(
    source: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    record = next(
        (item for item in records if item.get("source_id") == source["id"]),
        None,
    )
    if record is None:
        raise ValueError(f"no cleaned-record provenance found for source {source['id']!r}")
    return {
        **dict(source),
        "document_id": str(record["document_id"]),
        "document_hash": str(record["cleaned_content_hash"]),
        "content_hash": str(record["cleaned_content_hash"]),
        "provenance": {
            "raw_content_hash": record.get("raw_content_hash"),
            "cleaned_content_hash": record.get("cleaned_content_hash"),
            "extraction_status": record.get("extraction_status"),
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
