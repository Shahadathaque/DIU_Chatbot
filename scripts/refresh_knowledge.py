#!/usr/bin/env python3
"""Safely refresh DIU sources, vectors, and runtime catalogs as one publication."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import Settings  # noqa: E402
from backend.repositories.runtime_catalog import RuntimeCatalogRepository  # noqa: E402
from cleaning.validator import validate_cleaned_dataset  # noqa: E402
from rag.chunker import chunk_records, load_cleaned_records  # noqa: E402
from rag.config import RagSettings  # noqa: E402
from rag.embeddings import create_embedder  # noqa: E402
from rag.refresh import (  # noqa: E402
    PostgresRefreshPublisher,
    RefreshCandidate,
    execute_refresh,
)
from rag.vector_store import PgVectorStore, create_vector_store  # noqa: E402
from scraper.runner import RunConfig, run_collection  # noqa: E402
from scripts.clean_dataset import build_cleaned_dataset  # noqa: E402
from scripts.sync_runtime_catalog import prepare_runtime_catalog  # noqa: E402
from scripts.validate_raw_dataset import validate_dataset  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work-root",
        type=Path,
        default=PROJECT_ROOT / ".refresh-work",
        help="append-only refresh snapshots and safe reports",
    )
    parser.add_argument(
        "--minimum-program-ratio",
        type=float,
        default=0.5,
        help="reject candidates below this fraction of the active program count",
    )
    parser.add_argument("--min-delay", type=float, default=2.0)
    parser.add_argument("--max-delay", type=float, default=5.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = refresh_knowledge(
            work_root=args.work_root,
            minimum_program_ratio=args.minimum_program_ratio,
            minimum_delay=args.min_delay,
            maximum_delay=args.max_delay,
        )
    except Exception as error:
        # Never include request bodies, database URLs, or credentials in this
        # scheduled-job error. Provider exceptions are already sanitized.
        print(
            f"refresh_knowledge: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def refresh_knowledge(
    *,
    work_root: Path,
    minimum_program_ratio: float = 0.5,
    minimum_delay: float = 2.0,
    maximum_delay: float = 5.0,
) -> dict[str, Any]:
    """Collect and validate an isolated snapshot, then publish it atomically."""

    version = datetime.now(timezone.utc).strftime("refresh-%Y%m%dt%H%M%S%f")
    snapshot_root = Path(work_root).resolve() / version
    raw_root = snapshot_root / "raw"
    cleaned_root = snapshot_root / "cleaned"
    raw_root.mkdir(parents=True, exist_ok=False)

    registry = PROJECT_ROOT / "data/source_registry.csv"
    summary = run_collection(
        RunConfig(
            registry_path=registry,
            output_root=raw_root,
            project_root=PROJECT_ROOT,
            minimum_delay_seconds=minimum_delay,
            maximum_delay_seconds=maximum_delay,
            dataset_version=version,
        )
    )
    if summary.failed or not summary.successful or summary.successful != summary.selected:
        raise RuntimeError(
            "collection was incomplete; candidate publication was cancelled "
            f"(selected={summary.selected}, successful={summary.successful}, "
            f"failed={summary.failed})"
        )
    raw_report = validate_dataset(
        output_root=raw_root,
        registry_path=registry,
        dataset_version=version,
    )
    if raw_report["errors"]:
        raise RuntimeError("raw candidate validation failed")

    build_cleaned_dataset(
        raw_root=raw_root,
        output_root=cleaned_root,
        registry_path=registry,
        near_duplicate_threshold=0.92,
        project_root=PROJECT_ROOT,
        dataset_version=version,
    )
    cleaned_report = validate_cleaned_dataset(
        cleaned_root=cleaned_root,
        raw_root=raw_root,
        registry_path=registry,
        project_root=PROJECT_ROOT,
    )
    if not cleaned_report["passed"]:
        raise RuntimeError("cleaned candidate validation failed")

    rag_settings = RagSettings()
    app_settings = Settings()
    if rag_settings.rag_vector_backend != "pgvector":
        raise ValueError("scheduled refresh requires RAG_VECTOR_BACKEND=pgvector")
    if rag_settings.embedding_backend != "openai":
        raise ValueError("scheduled refresh requires the hosted production embedder")
    if app_settings.runtime_catalog_backend != "database":
        raise ValueError("scheduled refresh requires RUNTIME_CATALOG_BACKEND=database")
    if not app_settings.database_url:
        raise ValueError("DATABASE_URL is required for scheduled refresh")

    records = load_cleaned_records(cleaned_root)
    chunks = chunk_records(records, settings=rag_settings)
    programs, sources, metadata, _root = prepare_runtime_catalog(
        cleaned_root=cleaned_root
    )
    candidate = RefreshCandidate(
        records=records,
        chunks=chunks,
        programs=programs,
        sources=sources,
        metadata=metadata,
    )
    store = create_vector_store(rag_settings)
    if not isinstance(store, PgVectorStore):  # defensive after config validation
        raise ValueError("scheduled refresh could not construct pgvector storage")
    publisher = PostgresRefreshPublisher(
        store,
        RuntimeCatalogRepository(app_settings.database_url),
    )
    result = execute_refresh(
        candidate,
        embedder=create_embedder(rag_settings),
        publisher=publisher,
        minimum_program_ratio=minimum_program_ratio,
    )
    return {
        "status": "published",
        "dataset_version": version,
        "snapshot_root": str(snapshot_root),
        "raw": {
            "selected": summary.selected,
            "successful": summary.successful,
            "failed": summary.failed,
        },
        "cleaned_records": len(records),
        **result.to_dict(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
