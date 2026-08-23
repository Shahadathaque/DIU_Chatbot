"""Permanent coverage for the cleaned-table tuition catalog audit."""

from scripts.audit_tuition_retrieval import run_audience_audit, run_audit


def test_every_tuition_program_and_harmless_name_variant_resolves_exactly() -> None:
    report = run_audit()

    assert report["total_programs"] == 50
    assert report["programs_passed"] == 50
    assert report["total_queries"] >= 200
    assert report["failed"] == 0, report["failures"]


def test_every_international_tuition_row_preserves_audience_and_currency_lane() -> None:
    report = run_audience_audit()

    assert report["international_programs"] == 9
    assert report["programs_with_local_comparison"] == 9
    assert report["total_queries"] == 45
    assert report["failed"] == 0, report["failures"]
