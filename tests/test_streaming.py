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
    assert '"token"' in response.text
    done = [
        block
        for block in response.text.split("\n\n")
        if "event: done" in block
    ][0]
    payload = json.loads(next(line[6:] for line in done.splitlines() if line.startswith("data:")))
    assert payload["response"]["answer"].startswith("Bring the documents")


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
