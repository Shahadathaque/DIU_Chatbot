"""Regression tests for the complete admission-section coverage audit."""

from scripts.audit_admission_coverage import COVERAGE_CASES, audit


def test_audit_covers_every_required_admission_section() -> None:
    assert len(COVERAGE_CASES) == 21
    assert all(len(case.variants) >= 3 for case in COVERAGE_CASES)
    assert audit() == []
