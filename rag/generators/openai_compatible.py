"""OpenAI-compatible HTTP generator adapter using httpx (no ``openai`` package).

Works against any service exposing ``POST <base>/chat/completions``, including
Ollama's local ``/v1`` endpoint or hosted providers, so it doubles as a free
local fallback when Transformers-on-MPS is too slow.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Sequence

import httpx

from rag.config import GeneratorSettings
from rag.generator import GeneratorUnavailableError

_REQUEST_TIMEOUT_SECONDS = 60.0


class OpenAICompatibleGenerator:
    """Call an OpenAI-compatible chat-completions endpoint with httpx."""

    def __init__(
        self,
        settings: GeneratorSettings,
        *,
        client: Optional[httpx.Client] = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        base_url = (settings.generator_api_base or "").rstrip("/")
        if not base_url:
            raise ValueError(
                "GENERATOR_API_BASE is required when GENERATOR_BACKEND=openai"
            )
        self.model_name = (
            settings.generator_api_model or settings.generator_model_name
        )
        self.model_revision: Optional[str] = None
        self.max_new_tokens = settings.generator_max_new_tokens
        self.temperature = settings.generator_temperature
        self.top_p = settings.generator_top_p
        self._base_url = base_url
        self._api_key = settings.generator_api_key
        self._reasoning_effort = settings.generator_api_reasoning_effort
        self._max_retries = settings.generator_api_max_retries
        self._retry_backoff = settings.generator_api_retry_backoff
        self._client = client
        self._sleep = sleeper

    def _endpoint(self) -> str:
        return f"{self._base_url}/chat/completions"

    def generate(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self.model_name,
            "messages": [dict(message) for message in messages],
            "max_tokens": (
                self.max_new_tokens if max_new_tokens is None else max_new_tokens
            ),
            "temperature": self.temperature if temperature is None else temperature,
            "top_p": self.top_p if top_p is None else top_p,
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        response = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._client is not None:
                    response = self._client.post(
                        self._endpoint(), json=payload, headers=headers
                    )
                else:
                    with httpx.Client(
                        timeout=httpx.Timeout(_REQUEST_TIMEOUT_SECONDS)
                    ) as client:
                        response = client.post(
                            self._endpoint(), json=payload, headers=headers
                        )
            except httpx.HTTPError as error:
                if attempt < self._max_retries:
                    self._sleep(self._retry_backoff * (2**attempt))
                    continue
                raise GeneratorUnavailableError(
                    "generator request failed: {}".format(error.__class__.__name__)
                ) from error
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self._max_retries:
                    self._sleep(_retry_delay(response, self._retry_backoff, attempt))
                    continue
            break
        assert response is not None
        if response.status_code >= 400:
            raise GeneratorUnavailableError(
                "generator returned HTTP {}".format(response.status_code)
            )
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise GeneratorUnavailableError(
                "generator returned an unexpected response body"
            ) from error
        return str(content).strip()


def _retry_delay(response: httpx.Response, backoff: float, attempt: int) -> float:
    delay = backoff * (2**attempt)
    try:
        retry_after = float(response.headers.get("Retry-After", "0"))
    except ValueError:
        retry_after = 0.0
    return min(30.0, max(delay, retry_after))


__all__ = ["OpenAICompatibleGenerator"]
