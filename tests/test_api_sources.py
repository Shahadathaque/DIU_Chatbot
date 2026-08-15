"""Tests for the sources endpoint (GET /api/sources)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.sources import get_sources_service
from backend.main import app
from backend.services.sources_service import SourcesService
from tests.rag_helpers import cleaned_record


def _client(service: SourcesService) -> TestClient:
    app.dependency_overrides[get_sources_service] = lambda: service
    return TestClient(app)


def _reset_overrides() -> None:
    app.dependency_overrides.pop(get_sources_service, None)


def _source_record(source_id: str, *, category: str = "admission_overview") -> dict:
    return cleaned_record(
        source_id=source_id,
        document_id=source_id.casefold(),
        category=category,
        title=f"{source_id} official title",
    )


def test_sources_returns_registered_sources() -> None:
    records = [
        _source_record("DIU-ADM-001", category="admission_overview"),
        _source_record("DIU-DOC-001", category="required_admission_documents"),
    ]
    service = SourcesService(records=records)
    client = _client(service)

    response = client.get("/api/sources")

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 2
    assert sources[0]["id"] == "DIU-ADM-001"
    assert sources[0]["title"] == "DIU-ADM-001 official title"
    assert sources[0]["url"].startswith("https://")
    assert sources[0]["retrieved_at"] is not None
    assert sources[0]["category"] == "admission_overview"
    _reset_overrides()


def test_sources_sorted_by_id() -> None:
    records = [_source_record("DIU-ZZZ-001"), _source_record("DIU-AAA-001")]
    service = SourcesService(records=records)
    client = _client(service)

    response = client.get("/api/sources")

    ids = [item["id"] for item in response.json()["sources"]]
    assert ids == ["DIU-AAA-001", "DIU-ZZZ-001"]
    _reset_overrides()


def test_sources_empty_records_returns_empty_list() -> None:
    service = SourcesService(records=[])
    client = _client(service)

    response = client.get("/api/sources")

    assert response.status_code == 200
    assert response.json() == {"sources": []}
    _reset_overrides()


def test_sources_database_backend_does_not_load_local_files(monkeypatch) -> None:
    class FakeRepository:
        def list_sources(self):
            return [
                {
                    "id": "DIU-ADM-001",
                    "title": "Official DIU admission",
                    "url": "https://daffodilvarsity.edu.bd/admission",
                    "retrieved_at": "2026-08-15T00:00:00Z",
                    "category": "admission_overview",
                }
            ]

    service = SourcesService(repository=FakeRepository())
    monkeypatch.setattr(
        service,
        "_load_records",
        lambda: (_ for _ in ()).throw(AssertionError("local files must not load")),
    )

    response = service.list_sources()

    assert [source.id for source in response.sources] == ["DIU-ADM-001"]


def test_missing_cleaned_dataset_returns_recovery_error(tmp_path) -> None:
    service = SourcesService(cleaned_root=str(tmp_path / "missing-cleaned"))
    client = _client(service)

    response = client.get("/api/sources")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "artifact_unavailable"
    assert "cleaned" in response.json()["error"]["message"]
    _reset_overrides()
