"""Tests for the opt-in cross-encoder reranking hook."""

from __future__ import annotations

from rag.config import DEFAULT_RERANKER_MODEL, RagSettings
from typing import List, Sequence

from rag.retriever import Retriever
from rag.vector_store import InMemoryVectorStore
from tests.rag_helpers import knowledge_chunk


class FakeEmbedder:
    model_name = "fixture-embedding"
    model_revision = None
    dimension = 2

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return [[1.0, 0.0] for _text in texts]

    def embed_query(self, query: str) -> List[float]:
        return [1.0, 0.0]


class _FakeReranker:
    def __init__(self) -> None:
        self.calls = []

    def score(self, query, documents):
        self.calls.append((query, documents))
        return list(reversed(range(len(documents))))


def test_reranker_is_opt_in_and_configured() -> None:
    settings = RagSettings(_env_file=None)
    assert settings.rag_reranker_enabled is False
    assert settings.rag_reranker_model_name == DEFAULT_RERANKER_MODEL


def test_retriever_calls_injected_reranker() -> None:
    first = knowledge_chunk(
        "first",
        category="required_admission_documents",
        content="DIU admission documents certificate",
    )
    second = knowledge_chunk(
        "second",
        category="required_admission_documents",
        content="DIU admission documents transcript",
    )
    store = InMemoryVectorStore(
        embedding_dimension=2,
        embedding_model_name="fixture-embedding",
    )
    store.upsert_chunks([first, second], [[1.0, 0.0], [1.0, 0.0]])
    reranker = _FakeReranker()
    retriever = Retriever(
        FakeEmbedder(),
        store,
        min_similarity_score=-1.0,
        min_relevance_score=-1.0,
        reranker=reranker,
    )

    results = retriever.retrieve("DIU admission documents", top_k=2)

    assert reranker.calls
    assert len(results) == 2
