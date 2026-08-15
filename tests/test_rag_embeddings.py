from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

import httpx
import pytest

from rag.config import RagSettings
from rag.embeddings import (
    EmbeddingUnavailableError,
    OpenAICompatibleEmbedder,
    SentenceTransformerEmbedder,
    create_embedder,
)


class FakeSentenceTransformer:
    def __init__(self, dimension: int = 3) -> None:
        self.dimension = dimension
        self.calls: List[Dict[str, Any]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension

    def encode(self, texts: Sequence[str], **kwargs: Any) -> List[List[float]]:
        self.calls.append({"texts": list(texts), **kwargs})
        return [[1.0] + [0.0] * (self.dimension - 1) for _ in texts]


def test_multilingual_e5_uses_query_and_passage_prefixes() -> None:
    model = FakeSentenceTransformer()
    embedder = SentenceTransformerEmbedder(
        "intfloat/multilingual-e5-base",
        expected_dimension=3,
        batch_size=2,
        model=model,
    )

    assert embedder.embed_documents([" DIU fees ", "ড্যাফোডিলে ভর্তি"]) == [
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
    ]
    assert embedder.embed_query(" admission documents ") == [1.0, 0.0, 0.0]
    assert model.calls[0]["texts"] == [
        "passage: DIU fees",
        "passage: ড্যাফোডিলে ভর্তি",
    ]
    assert model.calls[1]["texts"] == ["query: admission documents"]
    assert model.calls[0]["batch_size"] == 2
    assert model.calls[0]["normalize_embeddings"] is True
    assert model.calls[0]["show_progress_bar"] is False


def test_embedder_rejects_configured_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="embedding dimension mismatch"):
        SentenceTransformerEmbedder(
            "intfloat/multilingual-e5-base",
            expected_dimension=768,
            model=FakeSentenceTransformer(dimension=3),
        )


def test_openai_compatible_embedder_batches_normalizes_and_authenticates() -> None:
    captured: list[dict[str, Any]] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append(
            {
                "url": str(request.url),
                "authorization": request.headers.get("Authorization"),
                "body": body,
            }
        )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [3.0, 4.0]}
                    for index, _text in enumerate(body["input"])
                ]
            },
        )

    embedder = OpenAICompatibleEmbedder(
        api_base="https://model.example/v1/",
        api_key="secret",
        model_name="hosted-embedding",
        dimension=2,
        batch_size=2,
        request_interval=0.25,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleeps.append,
    )

    assert embedder.embed_documents(["one", "two", "three"]) == [
        [0.6, 0.8],
        [0.6, 0.8],
        [0.6, 0.8],
    ]
    assert len(captured) == 2
    assert sleeps == [0.25]
    assert captured[0]["url"] == "https://model.example/v1/embeddings"
    assert captured[0]["authorization"] == "Bearer secret"
    assert captured[0]["body"] == {
        "model": "hosted-embedding",
        "input": ["one", "two"],
        "dimensions": 2,
    }


def test_openai_compatible_embedder_rejects_invalid_provider_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    embedder = OpenAICompatibleEmbedder(
        api_base="https://model.example/v1",
        api_key=None,
        model_name="hosted-embedding",
        dimension=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(EmbeddingUnavailableError, match="wrong number"):
        embedder.embed_query("DIU admission")


def test_openai_compatible_embedder_accepts_omitted_zero_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [1.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0]},
                ]
            },
        )

    embedder = OpenAICompatibleEmbedder(
        api_base="https://model.example/v1",
        api_key=None,
        model_name="hosted-embedding",
        dimension=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert embedder.embed_documents(["first", "second"]) == [
        [1.0, 0.0],
        [0.0, 1.0],
    ]


def test_create_embedder_selects_hosted_backend() -> None:
    settings = RagSettings(
        _env_file=None,
        embedding_backend="openai",
        embedding_api_base="https://model.example/v1",
        embedding_api_key="secret",
        embedding_api_model="hosted-embedding",
        embedding_dimension=768,
    )

    embedder = create_embedder(settings)

    assert isinstance(embedder, OpenAICompatibleEmbedder)
    assert embedder.model_name == "hosted-embedding"
    assert embedder.dimension == 768
    assert embedder.model_revision is None
