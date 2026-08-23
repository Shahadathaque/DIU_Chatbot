"""Tests for the chat endpoint (POST /api/chat) using mocked retrieval."""

from __future__ import annotations

from typing import List, Optional

from fastapi.testclient import TestClient

from backend.api.chat import get_chat_service
from backend.main import app
from backend.models.chat import ChatResponse, ChatSource, ChatTurn, Language
from backend.services.chat_service import ChatService, resolve_followup
from tests.rag_helpers import knowledge_chunk


class _FakeRetriever:
    """Retriever-shaped fake returning configured results per query."""

    def __init__(self, results_by_query: Optional[dict] = None) -> None:
        self._results_by_query = results_by_query or {}
        self.calls: List[str] = []

    def retrieve(self, query: str, top_k: int = 5) -> List:
        self.calls.append(query)
        return self._results_by_query.get(query, [])


def _client(retriever: _FakeRetriever) -> TestClient:
    app.dependency_overrides[get_chat_service] = lambda: ChatService(retriever)
    return TestClient(app)


def _reset_overrides() -> None:
    app.dependency_overrides.pop(get_chat_service, None)


def _evidence_result(chunk_id: str, *, content: str, relevance: float) -> object:
    chunk = knowledge_chunk(chunk_id, content=content)
    return _Result(chunk, relevance)


class _Result:
    def __init__(self, chunk, relevance: float) -> None:
        self.chunk = chunk
        self.similarity_score = relevance
        self.relevance_score = relevance


def test_chat_valid_request_returns_evidence_summary() -> None:
    retriever = _FakeRetriever(
        {
            "What documents are required?": [
                _evidence_result(
                    "doc1",
                    content="Verified DIU document requirements evidence.",
                    relevance=0.93,
                )
            ]
        }
    )
    client = _client(retriever)

    response = client.post(
        "/api/chat",
        json={"message": "What documents are required?", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "en"
    assert body["confidence"] == "high"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["url"].startswith("https://")
    assert "verified" in body["answer"].casefold()
    assert retriever.calls == ["What documents are required?"]
    _reset_overrides()


def test_chat_bangla_language_echoed() -> None:
    retriever = _FakeRetriever(
        {
            "ভর্তির জন্য কী লাগে": [
                _evidence_result(
                    "doc2", content="Bengali admission evidence text.", relevance=0.9
                )
            ]
        }
    )
    client = _client(retriever)

    response = client.post(
        "/api/chat",
        json={"message": "ভর্তির জন্য কী লাগে", "language": "bn"},
    )

    assert response.status_code == 200
    assert response.json()["language"] == "bn"
    _reset_overrides()


def test_chat_insufficient_retrieval_returns_low_confidence_no_sources() -> None:
    retriever = _FakeRetriever({})
    client = _client(retriever)

    response = client.post(
        "/api/chat",
        json={"message": "Unknown obscure question", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "low"
    assert body["sources"] == []
    assert body["answer"].strip()
    _reset_overrides()


def test_chat_out_of_domain_request_is_safe() -> None:
    retriever = _FakeRetriever({})
    client = _client(retriever)

    response = client.post(
        "/api/chat",
        json={"message": "What are the requirements at NSU?", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "low"
    assert body["sources"] == []
    _reset_overrides()


def test_chat_blank_message_rejected() -> None:
    client = _client(_FakeRetriever())

    response = client.post(
        "/api/chat", json={"message": "   ", "language": "en"}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    _reset_overrides()


def test_chat_invalid_language_rejected() -> None:
    client = _client(_FakeRetriever())

    response = client.post(
        "/api/chat", json={"message": "Hello", "language": "french"}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    _reset_overrides()


def test_chat_response_model_matches_contract() -> None:
    sample = ChatResponse(
        answer="Sample answer",
        sources=[ChatSource(title="DIU source", url="https://daffodilvarsity.edu.bd/admission")],
        confidence="high",
        language="en",
    )
    payload = sample.model_dump()
    assert set(payload) == {"answer", "sources", "confidence", "language"}
    assert payload["confidence"] in {"high", "medium", "low"}


def test_chat_followup_uses_history_for_retrieval() -> None:
    resolved = "in BDT. Program: Computer Science and Engineering. Topic: tuition fee."
    retriever = _FakeRetriever(
        {
            resolved: [
                _evidence_result(
                    "cse-local-fee",
                    content="CSE local tuition evidence in BDT.",
                    relevance=0.95,
                )
            ]
        }
    )
    client = _client(retriever)

    response = client.post(
        "/api/chat",
        json={
            "message": "in BDT",
            "language": "en",
            "history": [
                {"role": "user", "content": "What is the tuition fee of CSE?"},
                {"role": "assistant", "content": "Previous answer."},
            ],
        },
    )

    assert response.status_code == 200
    assert retriever.calls == [resolved]
    _reset_overrides()


def test_resolve_followup_preserves_topic_across_program_switches() -> None:
    history = [
        ChatTurn(role="user", content="What is the tuition fee of CSE?"),
        ChatTurn(role="assistant", content="Previous answer."),
        ChatTurn(role="user", content="in BDT"),
        ChatTurn(role="assistant", content="Previous BDT answer."),
    ]

    bba = resolve_followup("What about BBA?", history)
    assert "Bachelor of Business Administration" in bba
    assert "tuition fee" in bba
    assert "Computer Science and Engineering" not in bba

    history.extend(
        [
            ChatTurn(role="user", content="What about BBA?"),
            ChatTurn(role="assistant", content="Previous BBA answer."),
        ]
    )
    law = resolve_followup("What about Law?", history)
    assert "LL.B." in law
    assert "tuition fee" in law
    assert "Bachelor of Business Administration" not in law


def test_resolve_followup_preserves_active_program_for_waiver_question() -> None:
    history = [
        ChatTurn(role="user", content="What is the tuition fee of CSE?"),
        ChatTurn(role="assistant", content="Previous answer."),
        ChatTurn(role="user", content="What about SWE?"),
        ChatTurn(role="assistant", content="Previous SWE answer."),
    ]

    resolved = resolve_followup("Is there any waiver?", history)

    assert "waiver" in resolved.casefold()
    assert "Software Engineering" in resolved
    assert "Computer Science and Engineering" not in resolved


def test_resolve_followup_recognizes_misspelled_financial_aid_topics() -> None:
    history = [
        ChatTurn(role="user", content="Tell me about CSE"),
        ChatTurn(role="assistant", content="Previous answer."),
    ]

    waiver = resolve_followup("female waever", history)
    scholarship = resolve_followup("scholership", history)

    assert "Computer Science and Engineering" in waiver
    assert "Computer Science and Engineering" in scholarship


def test_resolve_followup_does_not_reuse_topic_for_a_new_faculty_query() -> None:
    history = [
        ChatTurn(role="user", content="scholarship"),
        ChatTurn(role="assistant", content="Previous scholarship answer."),
    ]

    for message in ("fsit department", "what about fsit department"):
        resolved = resolve_followup(message, history)

        assert resolved == message
        assert "scholarship" not in resolved.casefold()
