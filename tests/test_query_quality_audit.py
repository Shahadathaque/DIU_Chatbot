"""Regression test for the deterministic adversarial query-quality audit."""

from scripts.audit_query_quality import audit


def test_query_quality_audit_passes() -> None:
    assert audit()["failures"] == []
