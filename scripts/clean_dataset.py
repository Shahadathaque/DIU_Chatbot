#!/usr/bin/env python3
"""Build immutable cleaned dataset v1 from the finalized raw snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cleaning import CLEANING_PIPELINE_VERSION  # noqa: E402
from cleaning.filters import annotate_duplicates  # noqa: E402
from cleaning.html_cleaner import clean_html  # noqa: E402
from cleaning.models import CleanedRecord  # noqa: E402
from cleaning.normalizer import normalize_text, text_removed_percent  # noqa: E402
from cleaning.pdf_extractor import extract_pdf  # noqa: E402
from cleaning.utils import (  # noqa: E402
    files_fingerprint,
    git_state,
    read_json,
    safe_child,
    sha256_file,
    sha256_text,
    tree_fingerprint,
    utc_now_iso,
    write_json_new,
)
from cleaning.validator import dataset_statistics  # noqa: E402
from scraper.registry import load_registry  # noqa: E402


PIPELINE_FILES = (
    "cleaning/__init__.py",
    "cleaning/models.py",
    "cleaning/html_cleaner.py",
    "cleaning/pdf_extractor.py",
    "cleaning/normalizer.py",
    "cleaning/filters.py",
    "cleaning/validator.py",
    "cleaning/utils.py",
    "scripts/clean_dataset.py",
    "scripts/validate_clean_dataset.py",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=PROJECT_ROOT / "data/raw/collection-v2-finalized",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data/cleaned/v2",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "data/source_registry.csv",
    )
    parser.add_argument(
        "--dataset-version",
        help=(
            "raw dataset version to select when the raw root contains run "
            "manifests (for example: v2); inferred only when exactly one exists"
        ),
    )
    parser.add_argument("--near-duplicate-threshold", type=_threshold, default=0.92)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_cleaned_dataset(
            raw_root=args.raw_root,
            output_root=args.output_root,
            registry_path=args.registry,
            near_duplicate_threshold=args.near_duplicate_threshold,
            project_root=PROJECT_ROOT,
            dataset_version=args.dataset_version,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"clean_dataset: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_cleaned_dataset(
    *,
    raw_root: Path,
    output_root: Path,
    registry_path: Path,
    near_duplicate_threshold: float,
    project_root: Path,
    dataset_version: str | None = None,
) -> Dict[str, Any]:
    raw_root = Path(raw_root)
    output_root = Path(output_root)
    registry_path = Path(registry_path)
    project_root = Path(project_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"cleaned output directory is not empty: {output_root}")
    if not raw_root.is_dir():
        raise ValueError(f"raw dataset root does not exist: {raw_root}")

    sources = {source.source_id: source for source in load_registry(registry_path)}
    raw_manifest_path, raw_manifest = _raw_manifest(
        raw_root, dataset_version=dataset_version
    )
    run = raw_manifest.get("run")
    if not isinstance(run, dict) or not isinstance(run.get("results"), list):
        raise ValueError("raw manifest does not contain run.results")
    successful = [
        result
        for result in run["results"]
        if isinstance(result, dict) and result.get("status") == "successful"
    ]
    expected = {
        source.source_id
        for source in sources.values()
        if source.scrape_status in {"active", "manual_review"}
    }
    observed = {str(result.get("source_id")) for result in successful}
    if observed != expected:
        raise ValueError(
            "raw successful-source set does not match active/manual-review registry set"
        )

    cleaned_at = utc_now_iso()
    records: List[Dict[str, Any]] = []
    for result in sorted(successful, key=lambda item: str(item.get("source_id"))):
        source_id = str(result["source_id"])
        source = sources[source_id]
        raw_record_relative = str(result.get("record_path"))
        raw_record_path = safe_child(raw_root, raw_record_relative)
        if raw_record_path is None or not raw_record_path.is_file():
            raise ValueError(f"{source_id}: raw record path is invalid")
        raw_record = read_json(raw_record_path)
        raw_payload_path = safe_child(raw_root, raw_record.get("raw_path"))
        if raw_payload_path is None or not raw_payload_path.is_file():
            raise ValueError(f"{source_id}: raw payload path is invalid")
        raw_bytes = raw_payload_path.read_bytes()

        quality_flags = _metadata_flags(raw_record)
        if raw_record.get("content_type") == "html":
            cleaned = clean_html(
                raw_bytes,
                title=source.page_title,
                category=source.category,
                raw_extracted_text=str(raw_record.get("content") or ""),
                dynamic_page=source.dynamic_page,
                source_id=source_id,
                dependency_responses=raw_record.get("dependency_responses") or {},
            )
            cleaned_content = cleaned.text
            source_text_length = cleaned.source_text_length
            tables = cleaned.tables
            pages = []
            quality_flags.extend(cleaned.quality_flags)
            extraction_status = cleaned.extraction_status
            extraction_method = "beautifulsoup_dom_cleaning"
            extraction_quality = cleaned.extraction_quality
        elif raw_record.get("content_type") == "pdf":
            extracted = extract_pdf(raw_bytes)
            cleaned_content = normalize_text(
                f"{source.page_title}\n\n{extracted.text}"
            )
            source_text_length = extracted.source_text_length
            tables = extracted.tables
            pages = extracted.pages
            quality_flags.extend(extracted.quality_flags)
            extraction_status = extracted.extraction_status
            extraction_method = extracted.extraction_method
            extraction_quality = extracted.extraction_quality
            if source_id == "DIU-ADM-002":
                quality_flags.append("pdf_layout_complex")
                extraction_quality = "good_with_layout_warnings"
        else:
            raise ValueError(
                f"{source_id}: unsupported raw content type {raw_record.get('content_type')!r}"
            )

        if not cleaned_content.strip():
            cleaned_content = source.page_title
            quality_flags.extend(["empty_section", "short_content"])
            extraction_status = "partial"
            extraction_quality = "limited"
        if len(cleaned_content) < 200:
            quality_flags.append("short_content")

        record = CleanedRecord(
            document_id=source.document_id,
            source_id=source.source_id,
            source_url=source.url,
            canonical_url=source.canonical_url,
            final_url=str(raw_record["final_url"]),
            title=source.page_title,
            observed_title=raw_record.get("observed_title"),
            category=source.category,
            program=source.program,
            faculty=source.faculty,
            priority=source.priority,
            source_last_checked=source.last_checked,
            source_notes=source.notes,
            raw_dataset_version=str(raw_record["raw_dataset_version"]),
            raw_run_id=str(raw_record["run_id"]),
            raw_record_path=raw_record_relative,
            raw_path=str(raw_record["raw_path"]),
            raw_content_hash=str(raw_record["raw_content_hash"]),
            raw_extracted_content_hash=raw_record.get("extracted_content_hash"),
            hash_algorithm=str(raw_record.get("hash_algorithm", "sha256")),
            raw_response_bytes=int(raw_record["response_bytes"]),
            source_text_length=source_text_length,
            cleaned_content=cleaned_content,
            cleaned_content_hash=sha256_text(cleaned_content),
            cleaned_text_length=len(cleaned_content),
            text_removed_percent=text_removed_percent(
                source_text_length, len(cleaned_content)
            ),
            content_type=str(raw_record["content_type"]),
            mime_type=str(raw_record["mime_type"]),
            attempted_at=str(raw_record["attempted_at"]),
            retrieved_at=str(raw_record["retrieved_at"]),
            cleaned_at=cleaned_at,
            currency_status=source.currency_status,
            date_sensitive=source.date_sensitive,
            manual_review=source.scrape_status == "manual_review",
            scrape_status=source.scrape_status,
            dynamic_page=source.dynamic_page,
            capture_representation=str(raw_record["capture_representation"]),
            capture_redactions=list(raw_record.get("capture_redactions", [])),
            fetch_method=str(raw_record["fetch_method"]),
            http_status=int(raw_record["http_status"]),
            browser_version=raw_record.get("browser_version"),
            approved_dependency_urls=list(raw_record.get("approved_dependency_urls", [])),
            observed_dependency_urls=list(raw_record.get("observed_dependency_urls", [])),
            materialized_shadow_roots=int(
                raw_record.get("materialized_shadow_roots", 0)
            ),
            collector_version=str(raw_record["collector_version"]),
            cleaning_pipeline_version=CLEANING_PIPELINE_VERSION,
            extraction_status=extraction_status,
            extraction_method=extraction_method,
            extraction_quality=extraction_quality,
            quality_flags=sorted(set(quality_flags)),
            tables=tables,
            pages=pages,
        ).to_dict()
        records.append(record)

    duplicates = annotate_duplicates(
        records, near_threshold=near_duplicate_threshold
    )
    for record in records:
        record["quality_flags"] = sorted(set(record.get("quality_flags", [])))
        record["related_documents"] = sorted(
            record.get("related_documents", []),
            key=lambda item: (item["relationship"], item["document_id"]),
        )

    statistics = dataset_statistics(records)
    quality_report = _quality_report(
        records,
        statistics=statistics,
        duplicates=duplicates,
        generated_at=cleaned_at,
        near_duplicate_threshold=near_duplicate_threshold,
    )

    records_root = output_root / "records"
    records_root.mkdir(parents=True, exist_ok=True)
    record_entries = []
    for record in records:
        relative = Path("records") / f"{str(record['source_id']).casefold()}.json"
        path = output_root / relative
        write_json_new(path, record)
        record_entries.append(
            {
                "source_id": record["source_id"],
                "document_id": record["document_id"],
                "record_path": relative.as_posix(),
                "record_file_hash": sha256_file(path),
                "cleaned_content_hash": record["cleaned_content_hash"],
                "raw_content_hash": record["raw_content_hash"],
            }
        )

    quality_path = output_root / "quality_report.json"
    write_json_new(quality_path, quality_report)
    state = git_state(project_root)
    manifest = {
        "cleaned_dataset_version": "v1",
        "dataset_status": "partial"
        if statistics["partial_extractions"] or statistics["failed_extractions"]
        else "complete",
        "cleaning_pipeline_version": CLEANING_PIPELINE_VERSION,
        "raw_dataset_version": raw_manifest.get("raw_dataset_version"),
        "raw_dataset_status": raw_manifest.get("dataset_status"),
        "raw_manifest_path": raw_manifest_path.relative_to(raw_root).as_posix(),
        "raw_manifest_hash": sha256_file(raw_manifest_path),
        "raw_dataset_fingerprint": tree_fingerprint(raw_root),
        "source_registry_fingerprint": sha256_file(registry_path),
        "cleaning_pipeline_fingerprint": files_fingerprint(
            project_root, PIPELINE_FILES
        ),
        "pipeline_files": list(PIPELINE_FILES),
        "requirements_fingerprint": sha256_file(project_root / "requirements.txt"),
        "processing_timestamp": cleaned_at,
        "processing_config": {
            "near_duplicate_threshold": near_duplicate_threshold,
            "ocr_enabled": False,
            "pdf_table_minimum_density": 0.72,
            "short_content_threshold_characters": 200,
        },
        "git_revision": state["revision"],
        "git_worktree_dirty": state["worktree_dirty"],
        "dependencies": _dependencies(),
        "statistics": statistics,
        "quality_report_path": "quality_report.json",
        "quality_report_hash": sha256_file(quality_path),
        "records": record_entries,
    }
    write_json_new(output_root / "manifest.json", manifest)
    return {
        "output": output_root.as_posix(),
        "dataset_status": manifest["dataset_status"],
        "statistics": statistics,
        "quality_flag_counts": quality_report["quality_flag_counts"],
    }


def _raw_manifest(
    raw_root: Path, *, dataset_version: str | None = None
) -> tuple[Path, Dict[str, Any]]:
    candidates = []
    for path in sorted((raw_root / "runs").glob("*.json")):
        value = read_json(path)
        if dataset_version is None or value.get("raw_dataset_version") == dataset_version:
            candidates.append((path, value))
    if len(candidates) != 1:
        label = f" {dataset_version}" if dataset_version else ""
        raise ValueError(
            f"expected one raw{label} manifest; found {len(candidates)}"
        )
    return candidates[0]


def _metadata_flags(raw_record: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    currency = raw_record.get("currency_status")
    if currency == "historical":
        flags.append("historical")
    elif currency == "uncertain":
        flags.append("uncertain_currency")
    if raw_record.get("scrape_status") == "manual_review":
        flags.append("manual_review")
    if raw_record.get("capture_redactions"):
        flags.append("raw_capture_security_values_redacted")
    return flags


def _quality_report(
    records: Sequence[Dict[str, Any]],
    *,
    statistics: Dict[str, Any],
    duplicates: Dict[str, List[Dict[str, Any]]],
    generated_at: str,
    near_duplicate_threshold: float,
) -> Dict[str, Any]:
    flag_counts = Counter(
        flag for record in records for flag in record.get("quality_flags", [])
    )
    return {
        "cleaned_dataset_version": "v1",
        "generated_at": generated_at,
        "statistics": statistics,
        "quality_flag_counts": dict(sorted(flag_counts.items())),
        "flagged_records": [
            {
                "source_id": record["source_id"],
                "document_id": record["document_id"],
                "extraction_status": record["extraction_status"],
                "quality_flags": record["quality_flags"],
            }
            for record in records
            if record.get("quality_flags")
        ],
        "manual_review_records": [
            {
                "source_id": record["source_id"],
                "currency_status": record["currency_status"],
                "extraction_status": record["extraction_status"],
            }
            for record in records
            if record.get("manual_review")
        ],
        "table_records": [
            {"source_id": record["source_id"], "table_count": len(record["tables"])}
            for record in records
            if record.get("tables")
        ],
        "duplicate_detection": {
            "method": "exact cleaned SHA-256 plus five-token-shingle overlap similarity",
            "near_duplicate_threshold": near_duplicate_threshold,
            **duplicates,
        },
        "known_source_gaps": [
            "DIU-PROG-002 has no substantive BBA admission content and remains manual review.",
            "No dedicated verified diploma eligibility source exists in registry v1.",
            "Historical and uncertain sources require downstream currency gates.",
        ],
    }


def _dependencies() -> Dict[str, str | None]:
    values: Dict[str, str | None] = {}
    for distribution in ("beautifulsoup4", "pdfplumber", "pypdf"):
        try:
            values[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            values[distribution] = None
    return values


def _threshold(value: str) -> float:
    parsed = float(value)
    if not 0.0 < parsed <= 1.0:
        raise argparse.ArgumentTypeError("must be greater than 0 and at most 1")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
