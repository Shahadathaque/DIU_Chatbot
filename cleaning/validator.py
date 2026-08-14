"""Independent integrity and provenance validation for cleaned dataset v1."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Set
from urllib.parse import urlsplit

from cleaning.normalizer import normalize_text
from cleaning.pdf_extractor import extract_pdf
from cleaning.utils import (
    files_fingerprint,
    parse_utc_timestamp,
    read_json,
    safe_child,
    sha256_bytes,
    sha256_file,
    sha256_text,
    tree_fingerprint,
)
from scraper.registry import load_registry
from scraper.utils import canonicalize_url


VALIDATOR_VERSION = "phase5-1.0"
REQUIRED_FIELDS = frozenset(
    {
        "document_id",
        "source_id",
        "source_url",
        "canonical_url",
        "final_url",
        "title",
        "category",
        "priority",
        "raw_dataset_version",
        "raw_run_id",
        "raw_record_path",
        "raw_path",
        "raw_content_hash",
        "hash_algorithm",
        "raw_response_bytes",
        "source_text_length",
        "cleaned_content",
        "cleaned_content_hash",
        "cleaned_text_length",
        "content_type",
        "mime_type",
        "attempted_at",
        "retrieved_at",
        "cleaned_at",
        "currency_status",
        "date_sensitive",
        "manual_review",
        "scrape_status",
        "dynamic_page",
        "capture_representation",
        "collector_version",
        "cleaning_pipeline_version",
        "extraction_status",
        "extraction_method",
        "extraction_quality",
        "quality_flags",
        "tables",
        "pages",
        "related_documents",
    }
)
LOCAL_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)")
TOKEN_VALUE_PATTERN = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/=-]{12,}|"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|private[_-]?key|"
    r"csrf[_-]?token|xsrf[_-]?token)\s*[:=]\s*['\"]?"
    r"[A-Za-z0-9._~+/=-]{12,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
KNOWN_FORM_VALUES = (
    "02/27/2002",
    "bijoy.292",
    "davidat@auf.edu.ph",
)
WORD_PATTERN = re.compile(r"[\w]+(?:[.'’-][\w]+)*", re.UNICODE)


def validate_cleaned_dataset(
    *,
    cleaned_root: Path,
    raw_root: Path,
    registry_path: Path,
    project_root: Path,
) -> Dict[str, Any]:
    cleaned_root = Path(cleaned_root)
    raw_root = Path(raw_root)
    registry_path = Path(registry_path)
    project_root = Path(project_root)
    errors: List[str] = []
    warnings: List[str] = []

    manifest_path = cleaned_root / "manifest.json"
    quality_path = cleaned_root / "quality_report.json"
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return _report([f"manifest is unreadable: {error}"], warnings, [])

    if manifest.get("raw_dataset_fingerprint") != tree_fingerprint(raw_root):
        errors.append("raw dataset tree fingerprint mismatch")
    if manifest.get("source_registry_fingerprint") != sha256_file(registry_path):
        errors.append("source registry fingerprint mismatch")
    if manifest.get("quality_report_hash") != sha256_file(quality_path):
        errors.append("quality report hash mismatch")

    pipeline_files = manifest.get("pipeline_files")
    if not isinstance(pipeline_files, list) or not all(
        isinstance(item, str) for item in pipeline_files
    ):
        errors.append("manifest pipeline_files is invalid")
    else:
        try:
            actual_pipeline_hash = files_fingerprint(project_root, pipeline_files)
        except OSError as error:
            errors.append(f"cleaning pipeline files are unreadable: {error}")
        else:
            if actual_pipeline_hash != manifest.get("cleaning_pipeline_fingerprint"):
                errors.append("cleaning pipeline fingerprint mismatch")

    sources = {source.source_id: source for source in load_registry(registry_path)}
    entries = manifest.get("records")
    if not isinstance(entries, list):
        errors.append("manifest records is not a list")
        entries = []

    records: List[Dict[str, Any]] = []
    document_ids: Dict[str, str] = {}
    source_ids: Set[str] = set()
    hash_sources: Dict[str, List[str]] = defaultdict(list)

    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("manifest contains a non-object record entry")
            continue
        record_path = safe_child(cleaned_root, entry.get("record_path"))
        if record_path is None or not record_path.is_file():
            errors.append(f"invalid or missing cleaned record path: {entry.get('record_path')!r}")
            continue
        if sha256_file(record_path) != entry.get("record_file_hash"):
            errors.append(f"{entry.get('source_id')}: cleaned record file hash mismatch")
        try:
            record = read_json(record_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"cleaned record is unreadable: {error}")
            continue
        records.append(record)
        _validate_record(
            record,
            raw_root=raw_root,
            sources=sources,
            document_ids=document_ids,
            source_ids=source_ids,
            hash_sources=hash_sources,
            errors=errors,
            warnings=warnings,
        )

    expected_source_ids = {
        source.source_id
        for source in sources.values()
        if source.scrape_status in {"active", "manual_review"}
    }
    missing = sorted(expected_source_ids - source_ids)
    unexpected = sorted(source_ids - expected_source_ids)
    if missing:
        errors.append(f"registered source records missing: {', '.join(missing)}")
    if unexpected:
        errors.append(f"unexpected cleaned source records: {', '.join(unexpected)}")

    _validate_duplicate_annotations(records, hash_sources, errors)
    statistics = _statistics(records)
    manifest_statistics = manifest.get("statistics")
    if manifest_statistics != statistics:
        errors.append("manifest statistics do not match cleaned records")
    try:
        quality = read_json(quality_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"quality report is unreadable: {error}")
    else:
        if quality.get("statistics") != statistics:
            errors.append("quality report statistics do not match cleaned records")

    return _report(errors, warnings, records, statistics=statistics)


def _validate_record(
    record: Dict[str, Any],
    *,
    raw_root: Path,
    sources: Mapping[str, Any],
    document_ids: Dict[str, str],
    source_ids: Set[str],
    hash_sources: Dict[str, List[str]],
    errors: List[str],
    warnings: List[str],
) -> None:
    source_id = str(record.get("source_id", ""))
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        errors.append(f"{source_id}: missing required fields: {', '.join(missing)}")
    source = sources.get(source_id)
    if source is None:
        errors.append(f"{source_id!r}: source ID is absent from registry")
        return
    source_ids.add(source_id)

    if record.get("document_id") != source.document_id:
        errors.append(f"{source_id}: document_id does not match registry")
    prior = document_ids.get(str(record.get("document_id")))
    if prior is not None and prior != source_id:
        errors.append(f"{source_id}: duplicate document_id also used by {prior}")
    document_ids[str(record.get("document_id"))] = source_id

    expected_metadata = {
        "source_url": source.url,
        "canonical_url": source.canonical_url,
        "title": source.page_title,
        "category": source.category,
        "program": source.program,
        "faculty": source.faculty,
        "priority": source.priority,
        "date_sensitive": source.date_sensitive,
        "currency_status": source.currency_status,
        "scrape_status": source.scrape_status,
        "manual_review": source.scrape_status == "manual_review",
        "dynamic_page": source.dynamic_page,
    }
    for name, expected in expected_metadata.items():
        if record.get(name) != expected:
            errors.append(f"{source_id}: {name} does not preserve registry metadata")

    for name in ("source_url", "canonical_url", "final_url"):
        value = record.get(name)
        try:
            canonicalize_url(value)
        except Exception:
            errors.append(f"{source_id}: {name} is not a valid HTTP(S) URL")
        else:
            if urlsplit(str(value)).scheme not in {"http", "https"}:
                errors.append(f"{source_id}: {name} has an invalid scheme")

    for name in ("attempted_at", "retrieved_at", "cleaned_at"):
        if not parse_utc_timestamp(record.get(name)):
            errors.append(f"{source_id}: {name} is not a valid UTC timestamp")

    flags = record.get("quality_flags")
    if not isinstance(flags, list) or not all(isinstance(item, str) for item in flags):
        errors.append(f"{source_id}: quality_flags is invalid")
        flags = []
    if source.scrape_status == "manual_review" and "manual_review" not in flags:
        errors.append(f"{source_id}: manual-review quality flag was not preserved")
    if source.currency_status == "historical" and "historical" not in flags:
        errors.append(f"{source_id}: historical quality flag was not preserved")
    if source.currency_status == "uncertain" and "uncertain_currency" not in flags:
        errors.append(f"{source_id}: uncertain currency flag was not preserved")
    if source_id == "DIU-PROG-002" and "dynamic_content_incomplete" not in flags:
        errors.append(f"{source_id}: known incomplete dynamic content is not flagged")

    cleaned_content = record.get("cleaned_content")
    if not isinstance(cleaned_content, str) or not cleaned_content.strip():
        errors.append(f"{source_id}: cleaned content is empty")
        cleaned_content = ""
    if sha256_text(cleaned_content) != record.get("cleaned_content_hash"):
        errors.append(f"{source_id}: cleaned content hash mismatch")
    if len(cleaned_content) != record.get("cleaned_text_length"):
        errors.append(f"{source_id}: cleaned text length mismatch")
    hash_sources[str(record.get("cleaned_content_hash"))].append(source_id)

    serialized = json.dumps(record, ensure_ascii=False)
    if LOCAL_PATH_PATTERN.search(serialized):
        errors.append(f"{source_id}: local filesystem path persisted")
    if TOKEN_VALUE_PATTERN.search(serialized):
        errors.append(f"{source_id}: secret/token-like value persisted")
    if source_id == "DIU-APP-001":
        lowered = cleaned_content.casefold()
        for value in KNOWN_FORM_VALUES:
            if value.casefold() in lowered:
                errors.append(f"{source_id}: captured form/default value persisted")

    raw_record_path = safe_child(raw_root, record.get("raw_record_path"))
    if raw_record_path is None or not raw_record_path.is_file():
        errors.append(f"{source_id}: raw record path is invalid or missing")
        return
    try:
        raw_record = read_json(raw_record_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"{source_id}: raw record is unreadable: {error}")
        return
    raw_path = safe_child(raw_root, record.get("raw_path"))
    if raw_path is None or not raw_path.is_file():
        errors.append(f"{source_id}: raw payload path is invalid or missing")
        return
    raw_bytes = raw_path.read_bytes()
    digest = sha256_bytes(raw_bytes)
    if digest != record.get("raw_content_hash") or digest != raw_record.get(
        "raw_content_hash"
    ):
        errors.append(f"{source_id}: raw content hash mismatch")
    if len(raw_bytes) != record.get("raw_response_bytes"):
        errors.append(f"{source_id}: raw response byte count mismatch")
    for name in (
        "document_id",
        "source_id",
        "source_url",
        "canonical_url",
        "final_url",
        "retrieved_at",
        "attempted_at",
        "content_type",
        "mime_type",
        "hash_algorithm",
        "collector_version",
        "raw_dataset_version",
    ):
        if record.get(name) != raw_record.get(name):
            errors.append(f"{source_id}: {name} does not preserve raw provenance")

    allowed_text = str(raw_record.get("content") or "") + "\n" + source.page_title
    # Official absolute links retained by cleaning may combine source-provided
    # route fields with the already-provenanced DIU origin. Include those raw
    # provenance URLs and captured dependency URLs in the traceability corpus.
    for name in ("source_url", "canonical_url", "final_url"):
        allowed_text += "\n" + str(raw_record.get(name) or "")
    for value in raw_record.get("approved_dependency_urls") or []:
        if isinstance(value, str):
            allowed_text += "\n" + value
    dependency_responses = raw_record.get("dependency_responses")
    if isinstance(dependency_responses, dict):
        for url, value in dependency_responses.items():
            if isinstance(url, str):
                allowed_text += "\n" + url
            if isinstance(value, str):
                allowed_text += "\n" + value
                allowed_text += "\n" + _decoded_json_strings(value)
    if record.get("content_type") == "pdf":
        try:
            extraction = extract_pdf(raw_bytes)
        except Exception as error:
            errors.append(f"{source_id}: independent PDF extraction failed: {error}")
            return
        allowed_text += "\n" + extraction.text
        allowed_text += "\n" + _table_text([table.to_dict() for table in extraction.tables])
    candidate_text = cleaned_content + "\n" + _table_text(record.get("tables", []))
    missing_tokens = sorted(_tokens(candidate_text) - _tokens(allowed_text))
    if missing_tokens:
        errors.append(
            f"{source_id}: cleaned facts contain source-untraceable tokens: "
            + ", ".join(missing_tokens[:8])
        )


def _tokens(text: object) -> Set[str]:
    return {
        token.casefold()
        for token in WORD_PATTERN.findall(normalize_text(text))
        if not token.isdigit()
    }


def _decoded_json_strings(text: str) -> str:
    """Flatten every string value decoded from a JSON dependency response.

    Dependency responses are stored as raw JSON text, so unicode characters may
    be escaped (for example ``\\u2019``). Decoding the payload lets the
    traceability check see the same characters that survive into cleaned output.
    """

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return ""
    values: List[str] = []

    def visit(node: object) -> None:
        if isinstance(node, str):
            values.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return "\n".join(values)


def _table_text(tables: object) -> str:
    if not isinstance(tables, list):
        return ""
    values: List[str] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        for row in [table.get("headers", []), *table.get("rows", [])]:
            if isinstance(row, list):
                values.extend(str(cell) for cell in row)
    return "\n".join(values)


def _validate_duplicate_annotations(
    records: Sequence[Dict[str, Any]],
    hash_sources: Mapping[str, List[str]],
    errors: List[str],
) -> None:
    duplicate_sources = {
        source_id
        for source_ids in hash_sources.values()
        if len(source_ids) > 1
        for source_id in source_ids
    }
    for record in records:
        has_flag = "duplicate_content" in record.get("quality_flags", [])
        if has_flag != (record.get("source_id") in duplicate_sources):
            errors.append(f"{record.get('source_id')}: exact duplicate annotation mismatch")


def _statistics(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    content_types = Counter(str(record.get("content_type")) for record in records)
    statuses = Counter(str(record.get("extraction_status")) for record in records)
    currencies = Counter(str(record.get("currency_status")) for record in records)
    categories = Counter(str(record.get("category")) for record in records)
    raw_lengths = [int(record.get("source_text_length", 0)) for record in records]
    cleaned_lengths = [int(record.get("cleaned_text_length", 0)) for record in records]
    removal = [float(record.get("text_removed_percent", 0.0)) for record in records]
    return {
        "total_raw_documents": len(records),
        "total_cleaned_documents": len(records),
        "html_documents": content_types.get("html", 0),
        "pdf_documents": content_types.get("pdf", 0),
        "successful_extractions": statuses.get("success", 0),
        "partial_extractions": statuses.get("partial", 0),
        "failed_extractions": statuses.get("failed", 0),
        "current_records": currencies.get("current_date_sensitive", 0),
        "historical_records": currencies.get("historical", 0),
        "uncertain_records": currencies.get("uncertain", 0),
        "stable_reference_records": currencies.get("stable_reference", 0),
        "manual_review_records": sum(bool(record.get("manual_review")) for record in records),
        "records_containing_tables": sum(bool(record.get("tables")) for record in records),
        "structured_tables": sum(len(record.get("tables", [])) for record in records),
        "exact_duplicate_pairs": sum(
            1
            for left_index, left in enumerate(records)
            for right in records[left_index + 1 :]
            if left.get("cleaned_content_hash") == right.get("cleaned_content_hash")
        ),
        "near_duplicate_pairs": sum(
            1
            for left_index, left in enumerate(records)
            for right in records[left_index + 1 :]
            if any(
                relation.get("document_id") == right.get("document_id")
                and relation.get("relationship") == "near_duplicate"
                for relation in left.get("related_documents", [])
                if isinstance(relation, dict)
            )
        ),
        "average_raw_text_length": round(sum(raw_lengths) / len(raw_lengths), 2)
        if raw_lengths
        else 0.0,
        "average_cleaned_text_length": round(
            sum(cleaned_lengths) / len(cleaned_lengths), 2
        )
        if cleaned_lengths
        else 0.0,
        "average_text_removed_percent": round(sum(removal) / len(removal), 2)
        if removal
        else 0.0,
        "documents_by_category": dict(sorted(categories.items())),
    }


def dataset_statistics(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return _statistics(records)


def _report(
    errors: List[str],
    warnings: List[str],
    records: Sequence[Dict[str, Any]],
    *,
    statistics: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "validator_version": VALIDATOR_VERSION,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "validated_records": len(records),
        "statistics": statistics or _statistics(records),
    }
