#!/usr/bin/env python3
"""Validate cleaned dataset v1 against its raw snapshot and registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cleaning.validator import validate_cleaned_dataset  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cleaned-root",
        type=Path,
        default=PROJECT_ROOT / "data/cleaned/v2",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=PROJECT_ROOT / "data/raw/collection-v2-finalized",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "data/source_registry.csv",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_cleaned_dataset(
        cleaned_root=args.cleaned_root,
        raw_root=args.raw_root,
        registry_path=args.registry,
        project_root=PROJECT_ROOT,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
