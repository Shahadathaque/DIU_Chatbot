"""Tests for the additive SSE chat endpoint."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import backend.api.chat as chat_api
from backend.api.chat import get_chat_service
from backend.main import app
from backend.models.chat import ChatResponse


class _FakeService:
    def answer(self, message, language, history=None):
        assert message == "What documents are needed?"
        assert language == "en"
        assert history is None
        return ChatResponse(
            answer="Bring the documents listed by DIU.",
            sources=[],
            confidence="medium",
            language="en",
        )


def test_stream_endpoint_emits_tokens_and_final_response() -> None:
    app.dependency_overrides[get_chat_service] = lambda: _FakeService()
    try:
        response = TestClient(app).post(
            "/api/chat/stream",
            json={"message": "What documents are needed?", "language": "en"},
        )
    finally:
        app.dependency_overrides.pop(get_chat_service, None)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.startswith(
        'event: status\ndata: {"status": "processing"}\n\n'
    )
    assert '"token"' in response.text
    done = [
        block
        for block in response.text.split("\n\n")
        if "event: done" in block
    ][0]
    payload = json.loads(next(line[6:] for line in done.splitlines() if line.startswith("data:")))
    assert payload["response"]["answer"].startswith("Bring the documents")


def test_stream_endpoint_emits_safe_error_after_headers() -> None:
    class FailingService:
        def answer(self, message, language, history=None):
            del message, language, history
            raise RuntimeError("private database connection details")

    app.dependency_overrides[get_chat_service] = lambda: FailingService()
    try:
        response = TestClient(app).post(
            "/api/chat/stream",
            json={"message": "What documents are needed?", "language": "en"},
        )
    finally:
        app.dependency_overrides.pop(get_chat_service, None)

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "The admission service was interrupted" in response.text
    assert "private database connection details" not in response.text
    assert "event: done" not in response.text


def test_stream_endpoint_validates_before_service_resolution(monkeypatch) -> None:
    called = False

    def service_factory():
        nonlocal called
        called = True
        return _FakeService()

    monkeypatch.setattr(chat_api, "_build_chat_service", service_factory)
    response = TestClient(app).post("/api/chat/stream", json={"language": "en"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert called is False
