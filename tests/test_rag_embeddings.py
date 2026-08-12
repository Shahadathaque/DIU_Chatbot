from __future__ import annotations

from typing import Any, Dict, List, Sequence

import pytest

from rag.embeddings import SentenceTransformerEmbedder


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
