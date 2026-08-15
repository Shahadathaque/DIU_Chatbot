"""Tests for contract-compliant error handling and backend startup."""

from __future__ import annotations

from fastapi.testclient import TestClient
import backend.api.chat as chat_api

from backend.api.chat import get_chat_service
from backend.core.errors import ApiError
from backend.main import app
from backend.models.errors import ErrorBody, ErrorDetail, ErrorResponse


def _reset_overrides() -> None:
    app.dependency_overrides.pop(get_chat_service, None)


def test_backend_starts_and_health_is_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {"database", "model_endpoint", "rag_backend"}


def test_browser_origin_receives_cors_headers() -> None:
    client = TestClient(app)
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_for_post_allowed() -> None:
    client = TestClient(app)
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )
    assert "POST" in (response.headers.get("access-control-allow-methods") or "")
    assert "content-type" in (response.headers.get("access-control-allow-headers") or "").lower()


def test_disallowed_origin_gets_no_cors_allow_origin() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_validation_error_uses_contract_shape() -> None:
    client = TestClient(app)
    response = client.post("/api/chat", json={"language": "en"})
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)
    assert body["error"]["details"][0]["field"]


def test_invalid_chat_request_does_not_build_production_dependencies(monkeypatch) -> None:
    def _forbidden():
        raise AssertionError("invalid requests must not build retriever or generator")

    monkeypatch.setattr(chat_api, "_build_chat_service", _forbidden)
    response = TestClient(app).post("/api/chat", json={"language": "en"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_api_error_uses_contract_shape() -> None:
    def _failing_service():
        raise ApiError(
            status_code=503,
            code="service_unavailable",
            message="The knowledge service is temporarily unavailable.",
        )

    app.dependency_overrides[get_chat_service] = _failing_service
    client = TestClient(app)
    response = client.post("/api/chat", json={"message": "Hello", "language": "en"})
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert body["error"]["message"]
    _reset_overrides()


def test_unexpected_error_uses_contract_shape() -> None:
    def _exploding_service():
        raise RuntimeError("boom")

    app.dependency_overrides[get_chat_service] = _exploding_service
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/chat", json={"message": "Hello", "language": "en"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "boom" not in body["error"]["message"]
    _reset_overrides()


def test_error_response_model_matches_contract() -> None:
    sample = ErrorResponse(
        error=ErrorBody(
            code="validation_error",
            message="The request could not be validated.",
            details=[ErrorDetail(field="message", message="This field is required.")],
        )
    )
    payload = sample.model_dump()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "details"}
    assert payload["error"]["details"][0] == {
        "field": "message",
        "message": "This field is required.",
    }
