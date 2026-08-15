"""Offline tests for private artifact detection and recovery reporting."""

from __future__ import annotations

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
