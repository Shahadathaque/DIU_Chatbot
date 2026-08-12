#!/usr/bin/env python3
"""CLI for controlled, registry-driven DIU admission source collection."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.exceptions import ScraperError  # noqa: E402
from scraper.runner import RunConfig, run_collection  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect only DIU admission sources registered in "
            "data/source_registry.csv. Collection is sequential and append-only."
        )
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data/raw",
        help="append-only raw output directory (default: data/raw)",
    )
    parser.add_argument("--source-id", action="append", default=[], help="exact source ID; repeatable")
    parser.add_argument("--category", action="append", default=[], help="exact category; repeatable")
    parser.add_argument("--priority", action="append", default=[], help="exact priority; repeatable")
    parser.add_argument("--url", action="append", default=[], help="exact registered URL; repeatable")
    parser.add_argument("--limit", type=_nonnegative_int, help="maximum selected sources")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help=(
            "skip document IDs with a prior success; by default sources are "
            "rechecked and unchanged bytes are deduplicated"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and show selection without network access or writes",
    )
    parser.add_argument("--min-delay", type=_positive_float, default=2.0, help="minimum per-host delay in seconds (default: 2)")
    parser.add_argument("--max-delay", type=_positive_float, default=5.0, help="maximum per-host delay in seconds (default: 5)")
    parser.add_argument("--connect-timeout", type=_positive_float, default=10.0, help="HTTP connect timeout in seconds (default: 10)")
    parser.add_argument("--request-timeout", type=_positive_float, default=30.0, help="HTTP read/robots timeout in seconds (default: 30)")
    parser.add_argument("--playwright-timeout", type=_positive_int, default=30000, help="Playwright navigation timeout in milliseconds (default: 30000)")
    parser.add_argument("--retries", type=_retry_count, default=2, help="bounded transient retries, 0–5 (default: 2)")
    parser.add_argument(
        "--dataset-version",
        help="raw dataset version recorded in every record and run manifest (for example: v1)",
    )
    parser.add_argument("--seed", type=int, default=20260812, help="delay randomization seed (default: 20260812)")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="include tracebacks in the run log and console for debugging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_delay < args.min_delay:
        parser.error("--max-delay must be greater than or equal to --min-delay")

    config = RunConfig(
        registry_path=PROJECT_ROOT / "data/source_registry.csv",
        output_root=args.output_root,
        project_root=PROJECT_ROOT,
        source_ids=tuple(args.source_id),
        categories=tuple(args.category),
        priorities=tuple(args.priority),
        urls=tuple(args.url),
        limit=args.limit,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        minimum_delay_seconds=args.min_delay,
        maximum_delay_seconds=args.max_delay,
        random_seed=args.seed,
        connect_timeout_seconds=args.connect_timeout,
        request_timeout_seconds=args.request_timeout,
        playwright_timeout_ms=args.playwright_timeout,
        max_retries=args.retries,
        dataset_version=args.dataset_version,
        debug=args.debug,
    )

    try:
        summary = run_collection(config)
    except (ScraperError, ImportError, OSError, ValueError) as error:
        print(f"scrape_diu: {type(error).__name__}: {error}", file=sys.stderr)
        return 2

    _print_summary(summary.to_dict())
    # Every source is attempted before a partial-failure status is returned.
    return 1 if summary.failed else 0


def _print_summary(summary: dict[str, object]) -> None:
    mode = "DRY RUN" if summary["dry_run"] else "COLLECTION"
    print(f"{mode} {summary['run_id']}")
    for result in summary["results"]:  # type: ignore[union-attr]
        marker = {
            "successful": "OK",
            "failed": "FAIL",
            "would_process": "WOULD PROCESS",
            "would_skip": "WOULD SKIP",
            "skipped_existing": "SKIP",
        }.get(result["status"], str(result["status"]).upper())
        details = f"{result['source_id']} [{result['fetch_method']}] {result['source_url']}"
        if result["status"] == "failed":
            details += f" — {result['error_type']}: {result['error_message']}"
        print(f"{marker}: {details}")

    for name in (
        "selected",
        "attempted",
        "successful",
        "failed",
        "skipped",
        "html",
        "dynamic",
        "pdf",
        "binary",
    ):
        print(f"{name.replace('_', ' ').title()}: {summary[name]}")
    if summary.get("manifest_path"):
        print(f"Manifest: {summary['manifest_path']}")
    if summary.get("log_path"):
        print(f"Log: {summary['log_path']}")


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _retry_count(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 5:
        raise argparse.ArgumentTypeError("must be between 0 and 5")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be finite and non-negative")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
