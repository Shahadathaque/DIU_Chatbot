#!/usr/bin/env python3
"""Build or safely update the DIU retrieval knowledge base."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.chunker import chunk_records, load_cleaned_records  # noqa: E402
from rag.config import RagSettings  # noqa: E402
from rag.embeddings import SentenceTransformerEmbedder  # noqa: E402
from rag.vector_store import create_vector_store  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleaned-root", type=Path, default=None)
    parser.add_argument("--limit", type=_positive_int, default=None)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Replace the complete configured index before inserting selected data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and chunk only; do not load a model or connect to storage.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_knowledge_base(
            cleaned_root=args.cleaned_root,
            limit=args.limit,
            rebuild=args.rebuild,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"build_knowledge_base: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_knowledge_base(
    *,
    cleaned_root: Optional[Path] = None,
    limit: Optional[int] = None,
    rebuild: bool = False,
    dry_run: bool = False,
    settings: Optional[RagSettings] = None,
) -> Dict[str, Any]:
    """Validate, chunk, embed, and idempotently index selected records."""

    if rebuild and limit is not None and not dry_run:
        raise ValueError(
            "--rebuild cannot be combined with --limit because that would replace "
            "the complete index with a partial dataset"
        )
    settings = settings or RagSettings()
    root = Path(cleaned_root or settings.rag_cleaned_data_path)
    records = load_cleaned_records(root)
    if limit is not None:
        records = records[:limit]
    chunks = chunk_records(records, settings=settings)
    report: Dict[str, Any] = {
        "backend": settings.rag_vector_backend,
        "cleaned_root": str(root),
        "documents": len(records),
        "chunks": len(chunks),
        "chunk_types": dict(sorted(Counter(chunk.content_type for chunk in chunks).items())),
        "currency_statuses": dict(
            sorted(Counter(chunk.currency_status for chunk in chunks).items())
        ),
        "dry_run": dry_run,
        "embedding_model": settings.embedding_model_name,
        "embedding_model_revision": settings.embedding_model_revision,
        "embedding_dimension": settings.embedding_dimension,
    }
    if dry_run:
        report["stored"] = False
        return report

    if not records:
        raise ValueError(
            "refusing to mutate the knowledge base from a dataset with zero records"
        )
    if not chunks:
        raise ValueError(
            "refusing to mutate the knowledge base because chunking produced zero chunks"
        )

    store = create_vector_store(settings)
    if not rebuild:
        # Validate configuration/schema before the comparatively expensive model
        # load and corpus embedding. Rebuild setup stays inside the store's atomic
        # replacement transaction after embeddings have succeeded.
        store.setup()
    embedder = SentenceTransformerEmbedder(
        settings.embedding_model_name,
        expected_dimension=settings.embedding_dimension,
        model_revision=settings.embedding_model_revision,
        batch_size=settings.embedding_batch_size,
        device=settings.embedding_device,
    )
    embeddings = embedder.embed_documents([chunk.content for chunk in chunks])
    index_report = store.upsert_chunks(
        chunks,
        embeddings,
        processed_document_ids={record["document_id"] for record in records},
        rebuild=rebuild,
    )
    report["stored"] = True
    report["index"] = index_report.to_dict()
    return report


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
