"""Unit tests for controlled source-registry parsing and selection."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scraper.exceptions import (
    DuplicateSourceURLError,
    RegistryValidationError,
)
from scraper.models import SourceRecord
from scraper.registry import filter_sources, load_registry


HEADERS = [
    "source_id",
    "url",
    "page_title",
    "category",
    "program",
    "faculty",
    "priority",
    "dynamic_page",
    "date_sensitive",
    "currency_status",
    "scrape_status",
    "last_checked",
    "approved_dependency_urls",
    "notes",
    "refresh_hint",
]


def _row(**overrides: str) -> dict[str, str]:
    values = {
        "source_id": "DIU-ADM-001",
        "url": "https://daffodilvarsity.edu.bd/admission",
        "page_title": "Admissions",
        "category": "admission_overview",
        "program": "",
        "faculty": "",
        "priority": "high",
        "dynamic_page": "true",
        "date_sensitive": "false",
        "currency_status": "uncertain",
        "scrape_status": "active",
        "last_checked": "2026-08-10",
        "approved_dependency_urls": "",
        "notes": "Official source",
        "refresh_hint": "weekly",
    }
    values.update(overrides)
    return values


def _write_registry(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_load_registry_parses_booleans_and_retains_all_metadata(tmp_path: Path) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(path, [_row()])

    sources = load_registry(path)

    assert len(sources) == 1
    source = sources[0]
    assert isinstance(source, SourceRecord)
    assert source.dynamic_page is True
    assert source.date_sensitive is False
    assert source.program is None
    assert source.currency_status == "uncertain"
    assert source.scrape_status == "active"
    assert source.extras == {"refresh_hint": "weekly"}
    assert source.to_metadata()["extras"]["refresh_hint"] == "weekly"


@pytest.mark.parametrize("field", ["source_id", "url", "page_title", "category"])
def test_load_registry_rejects_missing_required_values(
    tmp_path: Path, field: str
) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(path, [_row(**{field: ""})])

    with pytest.raises(RegistryValidationError, match=field):
        load_registry(path)


@pytest.mark.parametrize("field", ["dynamic_page", "date_sensitive"])
def test_load_registry_rejects_non_boolean_values(
    tmp_path: Path, field: str
) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(path, [_row(**{field: "yes"})])

    with pytest.raises(RegistryValidationError, match="true.*false"):
        load_registry(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("currency_status", "fresh"),
        ("scrape_status", "verified"),
    ],
)
def test_load_registry_rejects_unknown_state_values(
    tmp_path: Path, field: str, value: str
) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(path, [_row(**{field: value})])

    with pytest.raises(RegistryValidationError, match=field):
        load_registry(path)


def test_registry_parses_only_exact_https_dependencies(tmp_path: Path) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(
        path,
        [
            _row(
                approved_dependency_urls=(
                    "https://api.example.test/notices|"
                    "https://api.example.test/faculties"
                )
            )
        ],
    )

    source = load_registry(path)[0]

    assert source.approved_dependency_urls == (
        "https://api.example.test/notices",
        "https://api.example.test/faculties",
    )


def test_registry_rejects_dependency_on_static_source(tmp_path: Path) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(
        path,
        [
            _row(
                dynamic_page="false",
                approved_dependency_urls="https://api.example.test/notices",
            )
        ],
    )

    with pytest.raises(RegistryValidationError, match="dynamic sources"):
        load_registry(path)


@pytest.mark.parametrize("source_id", ["../DIU", "DIU/ADM", "DIU--ADM", "DIU ADM"])
def test_load_registry_rejects_path_ambiguous_source_ids(
    tmp_path: Path, source_id: str
) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(path, [_row(source_id=source_id)])

    with pytest.raises(RegistryValidationError, match="source_id"):
        load_registry(path)


def test_load_registry_detects_duplicate_canonical_urls(tmp_path: Path) -> None:
    path = tmp_path / "registry.csv"
    _write_registry(
        path,
        [
            _row(),
            _row(
                source_id="DIU-ADM-002",
                url=(
                    "HTTPS://DAFFODILVARSITY.EDU.BD/admission/"
                    "?utm_source=audit#details"
                ),
            ),
        ],
    )

    with pytest.raises(DuplicateSourceURLError, match="canonical URL"):
        load_registry(path)


def test_filter_sources_combines_fields_url_and_limit() -> None:
    sources = [
        SourceRecord.from_mapping(_row()),
        SourceRecord.from_mapping(
            _row(
                source_id="DIU-DOC-001",
                url="https://daffodilvarsity.edu.bd/checklist.pdf?b=2&a=1",
                page_title="Checklist",
                category="documents",
                priority="medium",
                dynamic_page="false",
            )
        ),
        SourceRecord.from_mapping(
            _row(
                source_id="DIU-DOC-002",
                url="https://daffodilvarsity.edu.bd/flow.pdf",
                page_title="Flow",
                category="documents",
                priority="medium",
                dynamic_page="false",
            )
        ),
    ]

    assert [
        source.source_id
        for source in filter_sources(sources, category="DOCUMENTS", limit=1)
    ] == ["DIU-DOC-001"]
    assert [
        source.source_id
        for source in filter_sources(
            sources,
            priority="medium",
            url="https://DAFFODILVARSITY.edu.bd/checklist.pdf?a=1&b=2#ignored",
        )
    ] == ["DIU-DOC-001"]
    assert filter_sources(sources, source_id="missing") == []
    assert filter_sources(sources, limit=0) == []


def test_repository_registry_is_valid_and_complete() -> None:
    sources = load_registry("data/source_registry.csv")

    assert len(sources) == 18
    assert all(isinstance(source.dynamic_page, bool) for source in sources)
    assert all(source.canonical_url.startswith("https://") for source in sources)
    assert {source.scrape_status for source in sources} == {"active", "manual_review"}
    assert all(source.currency_status for source in sources)
