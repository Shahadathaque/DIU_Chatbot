"""Tests for the health-check endpoint."""

from types import SimpleNamespace
import sys

import httpx
from fastapi.testclient import TestClient

import backend.api.health as health_api
import backend.main as backend_main
from backend.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"]
    assert body["timestamp"].endswith("Z")
    assert set(body["checks"]) == {"database", "model_endpoint", "rag_backend"}
    assert all(
        value in {"ok", "not_configured", "error"}
        for value in body["checks"].values()
    )


def test_api_health_alias_returns_detailed_status() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["rag_backend"] in {"ok", "not_configured", "error"}


def test_startup_validation_runs_before_health_request(monkeypatch) -> None:
    settings = backend_main.get_settings()
    monkeypatch.setattr(backend_main, "get_settings", lambda: settings)

    with TestClient(app) as startup_client:
        response = startup_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_health_check_reports_configured_connection(monkeypatch) -> None:
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query):
            assert query == "SELECT 1"

        def fetchone(self):
            return (1,)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return FakeCursor()

    fake_psycopg = SimpleNamespace(
        connect=lambda url, connect_timeout: FakeConnection()
    )
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    assert health_api._check_database("postgresql://db.example/diu") == "ok"


def test_database_health_check_reports_connection_error(monkeypatch) -> None:
    fake_psycopg = SimpleNamespace(
        connect=lambda url, connect_timeout: (_ for _ in ()).throw(OSError("down"))
    )
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    assert health_api._check_database("postgresql://db.example/diu") == "error"


def test_model_endpoint_health_check_handles_success_and_failure(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class FakeClient:
        def __init__(self, response):
            self.response = response

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, endpoint, headers):
            assert endpoint == "https://model.example/v1/models"
            assert headers == {"Authorization": "Bearer test-key"}
            return self.response

    monkeypatch.setattr(
        health_api.httpx,
        "Client",
        lambda timeout: FakeClient(FakeResponse(200)),
    )
    assert health_api._check_model_endpoint("https://model.example/v1/", "test-key") == "ok"

    monkeypatch.setattr(
        health_api.httpx,
        "Client",
        lambda timeout: FakeClient(FakeResponse(503)),
    )
    assert health_api._check_model_endpoint("https://model.example/v1", "test-key") == "error"


def test_model_endpoint_health_check_reports_http_error(monkeypatch) -> None:
    class FailingClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, endpoint, headers):
            raise httpx.HTTPError("unreachable")

    monkeypatch.setattr(health_api.httpx, "Client", lambda timeout: FailingClient())

    assert health_api._check_model_endpoint("https://model.example/v1", None) == "error"


def test_rag_health_check_reports_pgvector_and_unknown_backends(monkeypatch) -> None:
    monkeypatch.setattr(
        health_api,
        "get_rag_settings",
        lambda: SimpleNamespace(rag_vector_backend="pgvector", database_url="postgresql://db"),
    )
    assert health_api._check_rag_backend() == "ok"

    monkeypatch.setattr(
        health_api,
        "get_rag_settings",
        lambda: SimpleNamespace(rag_vector_backend="pgvector", database_url=None),
    )
    assert health_api._check_rag_backend() == "not_configured"

    monkeypatch.setattr(
        health_api,
        "get_rag_settings",
        lambda: SimpleNamespace(rag_vector_backend="other", database_url=None),
    )
    assert health_api._check_rag_backend() == "error"
