from __future__ import annotations

import json
from pathlib import Path

from cleaning.utils import sha256_bytes, sha256_text
from cleaning.validator import validate_cleaned_dataset
from scraper.registry import load_registry
from scripts.clean_dataset import PROJECT_ROOT, build_cleaned_dataset


def test_cleaning_preserves_provenance_currency_and_manual_review(tmp_path: Path) -> None:
    raw_root, registry_path = _raw_fixture(tmp_path)
    output_root = tmp_path / "cleaned"

    build_cleaned_dataset(
        raw_root=raw_root,
        output_root=output_root,
        registry_path=registry_path,
        near_duplicate_threshold=0.92,
        project_root=PROJECT_ROOT,
    )
    record = json.loads((output_root / "records/test-001.json").read_text())

    assert record["source_id"] == "TEST-001"
    assert record["raw_dataset_version"] == "v1"
    assert record["currency_status"] == "uncertain"
    assert record["manual_review"] is True
    assert "manual_review" in record["quality_flags"]
    assert "uncertain_currency" in record["quality_flags"]
    assert record["raw_content_hash"] == sha256_bytes(
        (raw_root / record["raw_path"]).read_bytes()
    )

    validation = validate_cleaned_dataset(
        cleaned_root=output_root,
        raw_root=raw_root,
        registry_path=registry_path,
        project_root=PROJECT_ROOT,
    )
    assert validation["passed"], validation["errors"]
    assert validation["validated_records"] == 1


def test_cleaned_validator_detects_record_tampering(tmp_path: Path) -> None:
    raw_root, registry_path = _raw_fixture(tmp_path)
    output_root = tmp_path / "cleaned"
    build_cleaned_dataset(
        raw_root=raw_root,
        output_root=output_root,
        registry_path=registry_path,
        near_duplicate_threshold=0.92,
        project_root=PROJECT_ROOT,
    )
    record_path = output_root / "records/test-001.json"
    record = json.loads(record_path.read_text())
    record["cleaned_content"] += " invented claim"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    validation = validate_cleaned_dataset(
        cleaned_root=output_root,
        raw_root=raw_root,
        registry_path=registry_path,
        project_root=PROJECT_ROOT,
    )
    assert validation["passed"] is False
    assert any("hash mismatch" in error for error in validation["errors"])


def _raw_fixture(tmp_path: Path) -> tuple[Path, Path]:
    registry_path = tmp_path / "source_registry.csv"
    registry_path.write_text(
        "source_id,url,page_title,category,program,faculty,priority,dynamic_page,"
        "date_sensitive,currency_status,scrape_status,last_checked,"
        "approved_dependency_urls,notes\n"
        "TEST-001,https://example.edu/admission,Admission Requirements,"
        "admission_overview,,,high,false,true,uncertain,manual_review,"
        "2026-08-12,,Synthetic offline fixture\n",
        encoding="utf-8",
    )
    source = load_registry(registry_path)[0]
    raw_root = tmp_path / "raw"
    raw_bytes = (
        b"<html><body><nav>Forum</nav><main><h1>Admission Requirements</h1>"
        b"<p>Applicants need GPA 3.00 for this program.</p></main>"
        b"<footer>Visitor Statistics</footer></body></html>"
    )
    digest = sha256_bytes(raw_bytes)
    raw_path = Path("content/sha256") / digest
    (raw_root / raw_path).parent.mkdir(parents=True)
    (raw_root / raw_path).write_bytes(raw_bytes)
    raw_record_path = Path("records") / source.document_id / f"{digest}.json"
    (raw_root / raw_record_path).parent.mkdir(parents=True)
    extracted = "Forum\nAdmission Requirements\nApplicants need GPA 3.00 for this program.\nVisitor Statistics"
    raw_record = {
        "approved_dependency_urls": [],
        "attempted_at": "2026-08-12T00:00:00.000000Z",
        "browser_version": None,
        "canonical_url": source.canonical_url,
        "capture_redactions": [],
        "capture_representation": "http_response_entity_bytes",
        "category": source.category,
        "collector_version": "fixture-1.0",
        "content": extracted,
        "content_hash": digest,
        "content_type": "html",
        "currency_status": source.currency_status,
        "date_sensitive": source.date_sensitive,
        "document_id": source.document_id,
        "dynamic_page": source.dynamic_page,
        "extracted_content_hash": sha256_text(extracted),
        "faculty": source.faculty,
        "fetch_method": "requests",
        "final_url": source.url,
        "hash_algorithm": "sha256",
        "http_status": 200,
        "materialized_shadow_roots": 0,
        "mime_type": "text/html",
        "observed_dependency_urls": [],
        "observed_title": "Admission Requirements",
        "priority": source.priority,
        "program": source.program,
        "raw_content_hash": digest,
        "raw_dataset_version": "v1",
        "raw_path": raw_path.as_posix(),
        "response_bytes": len(raw_bytes),
        "retrieved_at": "2026-08-12T00:00:01.000000Z",
        "run_id": "run-fixture",
        "scrape_status": source.scrape_status,
        "source_id": source.source_id,
        "source_url": source.url,
        "title": source.page_title,
    }
    (raw_root / raw_record_path).write_text(
        json.dumps(raw_record), encoding="utf-8"
    )
    run_path = raw_root / "runs/run-fixture.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps(
            {
                "raw_dataset_version": "v1",
                "dataset_status": "complete",
                "run": {
                    "run_id": "run-fixture",
                    "results": [
                        {
                            "source_id": source.source_id,
                            "status": "successful",
                            "record_path": raw_record_path.as_posix(),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return raw_root, registry_path
