#!/usr/bin/env python3
"""Search the indexed DIU knowledge base without generating an answer."""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.retriever import create_retriever  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Admission question to retrieve evidence for.")
    parser.add_argument("--top-k", type=_positive_int, default=5)
    parser.add_argument("--category", default=None)
    parser.add_argument("--program", default=None)
    parser.add_argument("--min-similarity", type=float, default=None)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--include-historical", action="store_true")
    parser.add_argument("--include-uncertain", action="store_true")
    parser.add_argument("--include-manual-review", action="store_true")
    parser.add_argument("--include-partial", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        results = create_retriever().retrieve(
            args.query,
            top_k=args.top_k,
            category=args.category,
            program=args.program,
            include_historical=args.include_historical,
            include_uncertain=args.include_uncertain,
            include_manual_review=args.include_manual_review,
            include_partial=args.include_partial,
            min_similarity_score=args.min_similarity,
            min_relevance_score=args.min_score,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"search_knowledge: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    if not results:
        print("No eligible evidence met the relevance threshold.")
        return 0
    for rank, result in enumerate(results, start=1):
        chunk = result.chunk
        print(f"[{rank}] relevance={result.relevance_score:.4f} semantic={result.similarity_score:.4f}")
        print(f"Title: {chunk.title}")
        print(f"Category: {chunk.category}")
        print(f"Program: {chunk.program or '-'}")
        print(
            "Freshness: "
            f"{chunk.currency_status}; manual_review={str(chunk.manual_review).lower()}"
        )
        print(f"Source: {chunk.source_url}")
        print(f"Chunk: {chunk.chunk_id}")
        print(textwrap.fill(chunk.content, width=100, replace_whitespace=False))
        if rank != len(results):
            print("-" * 100)
    return 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
