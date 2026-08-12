"""Tests for scraper CLI validation and exit semantics."""

from types import SimpleNamespace

import pytest

from scraper.runner import RunSummary
from scripts import scrape_diu


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0"])
def test_cli_rejects_non_finite_or_zero_delay(value: str) -> None:
    with pytest.raises(SystemExit) as caught:
        scrape_diu.build_parser().parse_args(["--min-delay", value])

    assert caught.value.code == 2


def test_cli_returns_partial_failure_after_completed_run(monkeypatch) -> None:
    summary = RunSummary(
        run_id="run-test",
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:01Z",
        selected=1,
        attempted=1,
        failed=1,
        dry_run=False,
        results=[
            {
                "status": "failed",
                "source_id": "DIU-DOC-001",
                "fetch_method": "requests_pdf",
                "source_url": "https://daffodilvarsity.edu.bd/file.pdf",
                "error_type": "FetchError",
                "error_message": "HTTP 404",
            }
        ],
    )
    monkeypatch.setattr(scrape_diu, "run_collection", lambda config: summary)

    assert scrape_diu.main(["--dry-run"]) == 1
