"""Tests for the OpenAI-compatible generator using httpx MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from rag.config import GeneratorSettings
from rag.generator import GeneratorUnavailableError
from rag.generators.openai_compatible import OpenAICompatibleGenerator


def _settings(**overrides) -> GeneratorSettings:
    values = {
        "generator_backend": "openai",
        "generator_api_base": "https://api.example.com/v1",
        "generator_api_key": "secret-key",
        "_env_file": None,
    }
    values.update(overrides)
    return GeneratorSettings(**values)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openai_generate_success() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "  Grounded answer.  "}}]}
        )

    messages = [{"role": "user", "content": "hello"}]
    generator = OpenAICompatibleGenerator(_settings(), client=_client(handler))

    output = generator.generate(messages)

    assert output == "Grounded answer."
    assert captured["url"].endswith("/chat/completions")
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["content_type"] == "application/json"
    assert captured["body"]["model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert captured["body"]["messages"] == messages
    assert captured["body"]["max_tokens"] == 256
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["top_p"] == 0.9


def test_openai_generate_per_call_overrides() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    generator = OpenAICompatibleGenerator(_settings(), client=_client(handler))
    generator.generate(
        [{"role": "user", "content": "hello"}],
        max_new_tokens=10,
        temperature=0.0,
        top_p=0.5,
    )

    assert captured["body"]["max_tokens"] == 10
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["top_p"] == 0.5


def test_openai_api_model_override() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    generator = OpenAICompatibleGenerator(
        _settings(generator_api_model="custom-model"), client=_client(handler)
    )
    generator.generate([{"role": "user", "content": "hello"}])

    assert captured["body"]["model"] == "custom-model"
    assert generator.model_name == "custom-model"


def test_openai_reasoning_effort_is_optional_and_forwarded() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    generator = OpenAICompatibleGenerator(
        _settings(generator_api_reasoning_effort="minimal"),
        client=_client(handler),
    )
    generator.generate([{"role": "user", "content": "hello"}])

    assert captured["body"]["reasoning_effort"] == "minimal"


def test_openai_generate_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    generator = OpenAICompatibleGenerator(_settings(), client=_client(handler))
    with pytest.raises(GeneratorUnavailableError):
        generator.generate([{"role": "user", "content": "hello"}])


def test_openai_generate_network_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    generator = OpenAICompatibleGenerator(_settings(), client=_client(handler))
    with pytest.raises(GeneratorUnavailableError):
        generator.generate([{"role": "user", "content": "hello"}])


def test_openai_generate_unexpected_body_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    generator = OpenAICompatibleGenerator(_settings(), client=_client(handler))
    with pytest.raises(GeneratorUnavailableError):
        generator.generate([{"role": "user", "content": "hello"}])


def test_openai_missing_api_base_rejected() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleGenerator(
            _settings(generator_api_base=""),
        )
