#!/usr/bin/env python3
"""Inspect and verify the local DIU data/evaluation artifacts.

The repository intentionally does not track scraped data, embeddings, model
weights, or held-out evaluation files.  This module provides one deterministic
check that reports which private artifacts are present and validates their
embedded SHA-256/provenance metadata without loading a model or making network
requests.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
RAW_ROOT = PROJECT_ROOT / "data/raw/collection-v2-finalized"
CLEANED_ROOT = PROJECT_ROOT / "data/cleaned/v2"
KB_PATH = PROJECT_ROOT / "data/chunks/local_knowledge_base.json"
EVALUATION_PATH = PROJECT_ROOT / "data/evaluation/questions.v1.json"


@dataclass(frozen=True)
class ArtifactCheck:
    """Machine-readable status for one required private artifact."""

    name: str
    path: str
    exists: bool
    valid: bool
    detail: str

    @property
    def ready(self) -> bool:
        return self.exists and self.valid


def _missing(name: str, path: Path, detail: str | None = None) -> ArtifactCheck:
    return ArtifactCheck(
        name=name,
        path=str(path),
        exists=False,
        valid=False,
        detail=detail or "missing",
    )


def _present(name: str, path: Path, detail: str) -> ArtifactCheck:
    return ArtifactCheck(
        name=name,
        path=str(path),
        exists=True,
        valid=True,
        detail=detail,
    )


def _invalid(name: str, path: Path, error: BaseException) -> ArtifactCheck:
    return ArtifactCheck(
        name=name,
        path=str(path),
        exists=True,
        valid=False,
        detail=f"invalid: {type(error).__name__}: {error}",
    )


def _raw_check() -> ArtifactCheck:
    manifest_paths = sorted((RAW_ROOT / "runs").glob("*.json"))
    if not RAW_ROOT.is_dir() or not manifest_paths:
        return _missing(
            "raw snapshot",
            RAW_ROOT,
            "restore the immutable raw snapshot or run the controlled scraper",
        )
    try:
        from scripts.validate_raw_dataset import validate_dataset

        if len(manifest_paths) != 1:
            raise ValueError(
                "expected exactly one immutable raw run manifest; found {}".format(
                    len(manifest_paths)
                )
            )
        manifest = json.loads(manifest_paths[0].read_text(encoding="utf-8"))
        dataset_version = manifest.get("raw_dataset_version")
        if not isinstance(dataset_version, str) or not dataset_version.strip():
            raise ValueError("raw run manifest has no raw_dataset_version")

        report = validate_dataset(
            output_root=RAW_ROOT,
            registry_path=PROJECT_ROOT / "data/source_registry.csv",
            dataset_version=dataset_version,
        )
        if report.get("integrity_status") != "passed":
            return _invalid(
                "raw snapshot",
                RAW_ROOT,
                ValueError("raw validator reported integrity_status=failed"),
            )
        return _present(
            "raw snapshot",
            RAW_ROOT,
            f"validated {report.get('counts', {}).get('successful', 'available')} source records",
        )
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        return _invalid("raw snapshot", RAW_ROOT, error)


def _cleaned_check(raw: ArtifactCheck) -> ArtifactCheck:
    manifest_path = CLEANED_ROOT / "manifest.json"
    if not manifest_path.is_file():
        return _missing(
            "cleaned dataset",
            CLEANED_ROOT,
            "restore the cleaned snapshot or run scripts/clean_dataset.py",
        )
    if not raw.ready:
        return _invalid(
            "cleaned dataset",
            CLEANED_ROOT,
            ValueError("raw snapshot is required for checksum/provenance validation"),
        )
    try:
        from cleaning.validator import validate_cleaned_dataset

        report = validate_cleaned_dataset(
            cleaned_root=CLEANED_ROOT,
            raw_root=RAW_ROOT,
            registry_path=PROJECT_ROOT / "data/source_registry.csv",
            project_root=PROJECT_ROOT,
        )
        if not report.get("passed", False):
            errors = report.get("errors", [])
            return _invalid(
                "cleaned dataset",
                CLEANED_ROOT,
                ValueError("; ".join(errors[:3]) or "validation failed"),
            )
        return _present("cleaned dataset", CLEANED_ROOT, "manifest and record hashes verified")
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        return _invalid("cleaned dataset", CLEANED_ROOT, error)


def _knowledge_base_check() -> ArtifactCheck:
    if not KB_PATH.is_file():
        return _missing(
            "local knowledge base",
            KB_PATH,
            "restore the local index or run scripts/build_knowledge_base.py --rebuild",
        )
    try:
        from rag.config import (
            DEFAULT_EMBEDDING_DIMENSION,
            DEFAULT_EMBEDDING_MODEL,
            DEFAULT_EMBEDDING_REVISION,
        )
        from rag.vector_store import LocalVectorStore

        store = LocalVectorStore(
            KB_PATH,
            embedding_dimension=DEFAULT_EMBEDDING_DIMENSION,
            embedding_model_name=DEFAULT_EMBEDDING_MODEL,
            embedding_model_revision=DEFAULT_EMBEDDING_REVISION,
        )
        store.setup()
        return _present("local knowledge base", KB_PATH, f"validated {store.count()} indexed chunks")
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        return _invalid("local knowledge base", KB_PATH, error)


def _evaluation_check(kb: ArtifactCheck, cleaned: ArtifactCheck) -> ArtifactCheck:
    if not EVALUATION_PATH.is_file():
        return _missing(
            "held-out evaluation dataset",
            EVALUATION_PATH,
            "restore the private held-out dataset from research backup",
        )
    if not kb.ready or not cleaned.ready:
        return _invalid(
            "held-out evaluation dataset",
            EVALUATION_PATH,
            ValueError("cleaned dataset and knowledge base are required for provenance validation"),
        )
    try:
        from evaluation.schema import load_eval_dataset

        dataset = load_eval_dataset(
            EVALUATION_PATH,
            KB_PATH,
            CLEANED_ROOT / "manifest.json",
        )
        return _present("held-out evaluation dataset", EVALUATION_PATH, f"validated {len(dataset.questions)} questions")
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        return _invalid("held-out evaluation dataset", EVALUATION_PATH, error)


def inspect_artifacts() -> list[ArtifactCheck]:
    """Return all artifact statuses without downloading or loading models."""

    raw = _raw_check()
    cleaned = _cleaned_check(raw)
    kb = _knowledge_base_check()
    evaluation = _evaluation_check(kb, cleaned)
    return [raw, cleaned, kb, evaluation]


def all_artifacts_ready(checks: Iterable[ArtifactCheck]) -> bool:
    return all(check.ready for check in checks)


def recovery_instructions() -> list[str]:
    """Return reproducible, checksum-verifying recovery commands."""

    return [
        "Restore the private raw snapshot into data/raw/collection-v2-finalized.",
        "Read raw_dataset_version from the run manifest, then run: .venv/bin/python scripts/validate_raw_dataset.py --output-root data/raw/collection-v2-finalized --dataset-version <version>.",
        "Build cleaned data: .venv/bin/python scripts/clean_dataset.py --raw-root data/raw/collection-v2-finalized --output-root data/cleaned/v2.",
        "Validate cleaned data: .venv/bin/python scripts/validate_clean_dataset.py --cleaned-root data/cleaned/v2 --raw-root data/raw/collection-v2-finalized.",
        "Restore the private held-out dataset into data/evaluation/questions.v1.json.",
        "Build the local index: .venv/bin/python scripts/build_knowledge_base.py --rebuild.",
        "Run this checker again; manifests, record hashes, KB metadata, and evaluation provenance must all validate.",
    ]


def _render(checks: Sequence[ArtifactCheck]) -> str:
    lines = ["DIU Admission AI artifact check"]
    for check in checks:
        state = "ready" if check.ready else "missing" if not check.exists else "invalid"
        lines.append(f"- {check.name}: {state} ({check.path}) — {check.detail}")
    if not all_artifacts_ready(checks):
        lines.append("Recovery steps:")
        lines.extend(f"  {index}. {step}" for index, step in enumerate(recovery_instructions(), 1))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = inspect_artifacts()
    if args.json:
        print(json.dumps([asdict(check) | {"ready": check.ready} for check in checks], indent=2))
    else:
        print(_render(checks))
    return 0 if all_artifacts_ready(checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
