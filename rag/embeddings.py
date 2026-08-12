"""Configurable sentence-transformers embeddings for English, Bangla, and Banglish."""

from __future__ import annotations

import math
from typing import Any, Iterable, List, Optional, Protocol, Sequence

from rag.config import DEFAULT_EMBEDDING_MODEL


class Embedder(Protocol):
    """Small dependency-injection boundary used by builders and retrievers."""

    model_name: str
    model_revision: Optional[str]
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        ...

    def embed_query(self, query: str) -> List[float]:
        ...


class SentenceTransformerEmbedder:
    """Normalized dense embeddings backed by a configurable SentenceTransformer.

    The default multilingual E5 model expects asymmetric ``query:`` and
    ``passage:`` prefixes.  Other models receive the text unchanged unless
    ``use_e5_prefixes`` is explicitly enabled.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        *,
        expected_dimension: Optional[int] = None,
        model_revision: Optional[str] = None,
        batch_size: int = 16,
        device: Optional[str] = None,
        use_e5_prefixes: Optional[bool] = None,
        model: Any = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("embedding model name cannot be blank")
        if batch_size < 1:
            raise ValueError("embedding batch size must be positive")
        self.model_name = model_name
        self.model_revision = model_revision
        self.batch_size = batch_size
        self.use_e5_prefixes = (
            "e5" in model_name.lower()
            if use_e5_prefixes is None
            else use_e5_prefixes
        )
        if model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise RuntimeError(
                    "sentence-transformers is required for real embeddings; "
                    "install the pinned project requirements"
                ) from error
            kwargs = {}
            if model_revision:
                kwargs["revision"] = model_revision
            if device:
                kwargs["device"] = device
            model = SentenceTransformer(model_name, **kwargs)
        self._model = model
        model_dimension = int(model.get_sentence_embedding_dimension())
        if expected_dimension is not None and model_dimension != expected_dimension:
            raise ValueError(
                f"embedding dimension mismatch: model {model_name!r} produces "
                f"{model_dimension}, configured EMBEDDING_DIMENSION is "
                f"{expected_dimension}"
            )
        self.dimension = model_dimension

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        prepared = [self._prefix(str(text), "passage") for text in texts]
        return self._encode(prepared)

    def embed_query(self, query: str) -> List[float]:
        if not query.strip():
            raise ValueError("query cannot be blank")
        encoded = self._encode([self._prefix(query, "query")])
        return encoded[0]

    def _prefix(self, text: str, kind: str) -> str:
        if self.use_e5_prefixes:
            return f"{kind}: {text.strip()}"
        return text.strip()

    def _encode(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        values = self._model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        if hasattr(values, "tolist"):
            values = values.tolist()
        result = [[float(item) for item in vector] for vector in values]
        for vector in result:
            if len(vector) != self.dimension:
                raise ValueError(
                    f"encoder returned dimension {len(vector)}; expected {self.dimension}"
                )
            if not all(math.isfinite(item) for item in vector):
                raise ValueError("encoder returned a non-finite embedding")
        return result


def validate_embeddings(
    embeddings: Iterable[Sequence[float]], *, expected_dimension: int
) -> List[List[float]]:
    """Validate and materialize embeddings before database mutation."""

    result: List[List[float]] = []
    for index, embedding in enumerate(embeddings):
        vector = [float(value) for value in embedding]
        if len(vector) != expected_dimension:
            raise ValueError(
                f"embedding {index} has dimension {len(vector)}; "
                f"expected {expected_dimension}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise ValueError(f"embedding {index} contains a non-finite value")
        result.append(vector)
    return result
