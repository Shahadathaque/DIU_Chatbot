"""Configurable sentence-transformers embeddings for English, Bangla, and Banglish."""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Iterable, List, Optional, Protocol, Sequence

import httpx

from rag.config import DEFAULT_EMBEDDING_MODEL, RagSettings, get_rag_settings


class EmbeddingUnavailableError(RuntimeError):
    """Raised when a hosted embedding provider cannot produce valid vectors."""


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


class OpenAICompatibleEmbedder:
    """Embedding adapter for OpenAI-compatible hosted HTTP endpoints."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: Optional[str],
        model_name: str,
        dimension: int,
        model_revision: Optional[str] = None,
        batch_size: int = 16,
        timeout: float = 30.0,
        request_interval: float = 0.0,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        send_dimensions: bool = True,
        client: Optional[httpx.Client] = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_base.strip():
            raise ValueError("embedding API base cannot be blank")
        if not model_name.strip():
            raise ValueError("embedding API model cannot be blank")
        if dimension < 1 or batch_size < 1:
            raise ValueError("embedding dimension and batch size must be positive")
        if request_interval < 0:
            raise ValueError("embedding request interval cannot be negative")
        if not 0 <= max_retries <= 5 or retry_backoff < 0:
            raise ValueError("embedding retry settings are invalid")
        self.model_name = model_name
        self.model_revision = model_revision
        self.dimension = dimension
        self.batch_size = batch_size
        self._base_url = api_base.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._request_interval = request_interval
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._send_dimensions = send_dimensions
        self._client = client
        self._sleep = sleeper

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        values: List[List[float]] = []
        prepared = [str(text).strip() for text in texts]
        for start in range(0, len(prepared), self.batch_size):
            if start and self._request_interval:
                self._sleep(self._request_interval)
            values.extend(self._request(prepared[start : start + self.batch_size]))
        return values

    def embed_query(self, query: str) -> List[float]:
        if not query.strip():
            raise ValueError("query cannot be blank")
        return self._request([query.strip()])[0]

    def _request(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": list(texts),
        }
        if self._send_dimensions:
            payload["dimensions"] = self.dimension
        response = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._client is not None:
                    response = self._client.post(
                        f"{self._base_url}/embeddings", json=payload, headers=headers
                    )
                else:
                    with httpx.Client(timeout=httpx.Timeout(self._timeout)) as client:
                        response = client.post(
                            f"{self._base_url}/embeddings", json=payload, headers=headers
                        )
            except httpx.HTTPError as error:
                if attempt < self._max_retries:
                    self._sleep(self._retry_backoff * (2**attempt))
                    continue
                raise EmbeddingUnavailableError(
                    f"embedding request failed: {error.__class__.__name__}"
                ) from error
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self._max_retries:
                    self._sleep(_retry_delay(response, self._retry_backoff, attempt))
                    continue
            break
        assert response is not None
        if response.status_code >= 400:
            raise EmbeddingUnavailableError(
                f"embedding provider returned HTTP {response.status_code}"
            )
        try:
            body = response.json()
            entries = list(body["data"])
            # Some OpenAI-compatible providers omit an index when its value is
            # zero (for example, Gemini's compatibility endpoint). Preserve
            # response order as the fallback while still honoring explicit
            # indexes when they are present.
            entries = [
                entry
                for _index, entry in sorted(
                    enumerate(entries),
                    key=lambda pair: int(pair[1].get("index", pair[0])),
                )
            ]
            raw_vectors = [item["embedding"] for item in entries]
        except (KeyError, TypeError, ValueError) as error:
            raise EmbeddingUnavailableError(
                "embedding provider returned an unexpected response body"
            ) from error
        if len(raw_vectors) != len(texts):
            raise EmbeddingUnavailableError(
                "embedding provider returned the wrong number of vectors"
            )
        try:
            vectors = validate_embeddings(
                raw_vectors, expected_dimension=self.dimension
            )
        except (TypeError, ValueError) as error:
            raise EmbeddingUnavailableError(str(error)) from error
        return [_normalized(vector) for vector in vectors]


def create_embedder(
    settings: Optional[RagSettings] = None,
    *,
    model_name: Optional[str] = None,
    model_revision: Optional[str] = None,
    dimension: Optional[int] = None,
) -> Embedder:
    """Construct the configured local or hosted embedding backend."""

    resolved = settings or get_rag_settings()
    selected_model = model_name or resolved.embedding_model_name
    selected_revision = (
        resolved.embedding_model_revision
        if model_revision is None
        else model_revision
    )
    selected_dimension = dimension or resolved.embedding_dimension
    if resolved.embedding_backend == "openai":
        return OpenAICompatibleEmbedder(
            api_base=resolved.embedding_api_base or "",
            api_key=resolved.embedding_api_key,
            model_name=selected_model,
            model_revision=selected_revision,
            dimension=selected_dimension,
            batch_size=resolved.embedding_batch_size,
            timeout=resolved.embedding_api_timeout,
            request_interval=resolved.embedding_api_request_interval,
            max_retries=resolved.embedding_api_max_retries,
            retry_backoff=resolved.embedding_api_retry_backoff,
            send_dimensions=resolved.embedding_api_send_dimensions,
        )
    return SentenceTransformerEmbedder(
        selected_model,
        expected_dimension=selected_dimension,
        model_revision=selected_revision,
        batch_size=resolved.embedding_batch_size,
        device=resolved.embedding_device,
    )


def _normalized(vector: Sequence[float]) -> List[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        raise EmbeddingUnavailableError("embedding provider returned a zero vector")
    return [value / magnitude for value in vector]


def _retry_delay(response: httpx.Response, backoff: float, attempt: int) -> float:
    delay = backoff * (2**attempt)
    try:
        retry_after = float(response.headers.get("Retry-After", "0"))
    except ValueError:
        retry_after = 0.0
    return min(30.0, max(delay, retry_after))


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
