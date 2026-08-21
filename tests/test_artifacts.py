"""Offline tests for private artifact detection and recovery reporting."""

from __future__ import annotations

import json

from scripts import artifacts


def test_missing_artifacts_are_reported_without_network_or_model_loading(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(artifacts, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(artifacts, "CLEANED_ROOT", tmp_path / "cleaned")
    monkeypatch.setattr(artifacts, "KB_PATH", tmp_path / "kb.json")
    monkeypatch.setattr(artifacts, "EVALUATION_PATH", tmp_path / "questions.json")

    checks = artifacts.inspect_artifacts()

    assert [check.name for check in checks] == [
        "raw snapshot",
        "cleaned dataset",
        "local knowledge base",
        "held-out evaluation dataset",
    ]
    assert not artifacts.all_artifacts_ready(checks)
    assert all(not check.exists for check in checks)


def test_recovery_instructions_are_checksum_oriented() -> None:
    instructions = artifacts.recovery_instructions()

    assert any("validate_raw_dataset.py" in item for item in instructions)
    assert any("validate_clean_dataset.py" in item for item in instructions)
    assert any("manifests" in item and "hashes" in item for item in instructions)


def test_raw_artifact_check_uses_manifest_dataset_version(tmp_path, monkeypatch) -> None:
    raw_root = tmp_path / "raw"
    runs = raw_root / "runs"
    runs.mkdir(parents=True)
    (runs / "run.json").write_text(
        json.dumps({"raw_dataset_version": "v2"}), encoding="utf-8"
    )
    captured = {}

    def validate_dataset(**kwargs):
        captured.update(kwargs)
        return {"integrity_status": "passed", "counts": {"successful": 18}}

    monkeypatch.setattr(artifacts, "RAW_ROOT", raw_root)
    monkeypatch.setattr(
        "scripts.validate_raw_dataset.validate_dataset", validate_dataset
    )

    check = artifacts._raw_check()

    assert check.ready
    assert captured["dataset_version"] == "v2"
