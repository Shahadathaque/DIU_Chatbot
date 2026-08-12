"""Unit tests for runner selection, records, and source-failure isolation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scraper.fetcher import FetchResult
from scraper.runner import RunConfig, run_collection


REGISTRY_HEADER = (
    "source_id,url,page_title,category,program,faculty,priority,dynamic_page,"
    "date_sensitive,scrape_status,last_checked,notes\n"
)


def _registry(tmp_path: Path) -> Path:
    path = tmp_path / "registry.csv"
    path.write_text(
        REGISTRY_HEADER
        + "S-1,https://example.com/one,One,overview,,,high,false,true,verified,2026-01-01,\n"
        + "S-2,https://example.com/two,Two,overview,,,high,false,true,verified,2026-01-01,\n",
        encoding="utf-8",
    )
    return path


def test_dry_run_selects_without_creating_output(tmp_path: Path) -> None:
    output = tmp_path / "raw"
    summary = run_collection(
        RunConfig(
            registry_path=_registry(tmp_path),
            output_root=output,
            project_root=tmp_path,
            allowed_host_suffixes=("example.com",),
            dry_run=True,
            limit=1,
        )
    )

    assert summary.selected == 1
    assert summary.attempted == 0
    assert summary.results[0]["status"] == "would_process"
    assert not output.exists()


def test_collection_isolates_failure_and_sanitizes_headers(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeRobotsChecker:
        def __init__(self, **kwargs) -> None:
            self.reviews = {}

        def review(self, url: str):
            return SimpleNamespace(allowed=True, outcome="allowed")

        def close(self) -> None:
            return None

    calls = 0

    def fake_fetch(source, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("first failed with a long private-looking trace")
        return FetchResult(
            body=b"<!doctype html><html><head><title>Two</title></head><body>Admission</body></html>",
            fetch_method="requests",
            status_code=200,
            final_url=source.url,
            mime_type="text/html",
            headers={"content-type": "text/html", "set-cookie": "secret=value"},
        )

    monkeypatch.setattr("scraper.fetcher.fetch_source", fake_fetch)
    monkeypatch.setattr("scraper.policy.RobotsChecker", FakeRobotsChecker)
    monkeypatch.setattr("scraper.rate_limit.HostRateLimiter.wait", lambda self, url: 0.0)
    monkeypatch.setattr("scraper.rate_limit.HostRateLimiter.mark", lambda self, url: None)

    output = tmp_path / "raw"
    summary = run_collection(
        RunConfig(
            registry_path=_registry(tmp_path),
            output_root=output,
            project_root=tmp_path,
            allowed_host_suffixes=("example.com",),
            minimum_delay_seconds=0,
            maximum_delay_seconds=0,
            max_retries=0,
        )
    )

    assert summary.attempted == 2
    assert summary.failed == 1
    assert summary.successful == 1
    record_path = output / summary.results[1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["source_id"] == "S-2"
    assert record["content_hash"]
    assert record["source_url"] == "https://example.com/two"
    assert "set-cookie" not in record["response_headers"]
