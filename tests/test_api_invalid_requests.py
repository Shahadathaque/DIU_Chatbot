"""Validation-boundary tests for API request bodies.

FastAPI validates request bodies before resolving service dependencies. These
tests keep that boundary explicit and ensure 422 responses use the shared
error envelope without constructing model-backed services.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

import backend.api.chat as chat_api
import backend.api.eligibility as eligibility_api
from backend.main import app


client = TestClient(app)


def _assert_validation_error(response, field: str) -> None:
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "The request could not be validated."
    assert error["details"]
    assert error["details"][0]["field"] == field
    assert error["details"][0]["message"]


def _forbid_service_initialization() -> Callable[[], object]:
    def forbidden() -> object:
        raise AssertionError("invalid requests must not initialize services")

    return forbidden


def test_chat_invalid_request_returns_422() -> None:
    response = client.post("/api/chat", json={"language": "en"})

    _assert_validation_error(response, "message")


def test_chat_invalid_language_returns_422() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "Hello", "language": "french"},
    )

    _assert_validation_error(response, "language")


def test_chat_empty_message_returns_422() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "   ", "language": "en"},
    )

    _assert_validation_error(response, "message")


def test_eligibility_invalid_request_returns_422() -> None:
    response = client.post("/api/eligibility", json={})

    _assert_validation_error(response, "program")


def test_eligibility_invalid_type_returns_422() -> None:
    response = client.post(
        "/api/eligibility",
        json={"program": "CSE", "ssc_gpa": "not-a-number", "diploma": False},
    )

    _assert_validation_error(response, "ssc_gpa")


def test_chat_validation_precedes_service_initialization(monkeypatch) -> None:
    forbidden = _forbid_service_initialization()
    monkeypatch.setattr(chat_api, "_build_chat_service", forbidden)
    response = client.post("/api/chat", json={"language": "en"})

    _assert_validation_error(response, "message")


def test_eligibility_validation_precedes_service_initialization(monkeypatch) -> None:
    forbidden = _forbid_service_initialization()
    monkeypatch.setattr(eligibility_api, "EligibilityService", forbidden)
    response = client.post("/api/eligibility", json={})

    _assert_validation_error(response, "program")


def test_programs_has_no_request_body_to_validate() -> None:
    """GET /api/programs is read-only; unsupported methods are rejected."""

    response = client.post("/api/programs", json={})

    assert response.status_code == 405


def test_sources_has_no_request_body_to_validate() -> None:
    """GET /api/sources is read-only; unsupported methods are rejected."""

    response = client.post("/api/sources", json={})

    assert response.status_code == 405
