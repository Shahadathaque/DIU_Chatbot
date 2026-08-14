"""Tests for generator settings and the generator factory."""

from __future__ import annotations

import pytest

from rag.config import (
    DEFAULT_GENERATOR_MODEL,
    GeneratorSettings,
    get_generator_settings,
)
from rag.generator import Generator, create_generator
from rag.generators.local import LocalGenerator
from rag.generators.openai_compatible import OpenAICompatibleGenerator


def test_generator_settings_defaults() -> None:
    settings = GeneratorSettings(_env_file=None)
    assert settings.generator_backend == "local"
    assert settings.generator_model_name == DEFAULT_GENERATOR_MODEL
    assert settings.generator_model_revision is None
    assert settings.generator_device is None
    assert settings.generator_max_new_tokens == 256
    assert settings.generator_temperature == 0.0
    assert settings.generator_top_p == 0.9
    assert settings.generator_api_base is None
    assert settings.generator_api_key is None
    assert settings.generator_api_model is None
    assert settings.generator_lora_adapter is None


def test_generator_settings_blank_optionals_become_none(monkeypatch) -> None:
    monkeypatch.setenv("GENERATOR_MODEL_REVISION", "")
    monkeypatch.setenv("GENERATOR_DEVICE", "")
    monkeypatch.setenv("GENERATOR_API_BASE", "   ")
    monkeypatch.setenv("GENERATOR_API_KEY", "")
    monkeypatch.setenv("GENERATOR_API_MODEL", "")
    monkeypatch.setenv("GENERATOR_LORA_ADAPTER", "")
    settings = GeneratorSettings(_env_file=None)
    assert settings.generator_model_revision is None
    assert settings.generator_device is None
    assert settings.generator_api_base is None
    assert settings.generator_api_key is None
    assert settings.generator_api_model is None
    assert settings.generator_lora_adapter is None


def test_generator_settings_blank_model_uses_default(monkeypatch) -> None:
    monkeypatch.setenv("GENERATOR_MODEL_NAME", "")
    settings = GeneratorSettings(_env_file=None)
    assert settings.generator_model_name == DEFAULT_GENERATOR_MODEL


def test_generator_settings_lora_adapter_resolved_to_absolute_path(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GENERATOR_LORA_ADAPTER", "adapters/diu-v1")
    settings = GeneratorSettings(_env_file=None)
    assert settings.generator_lora_adapter is not None
    assert settings.generator_lora_adapter.is_absolute()
    assert settings.generator_lora_adapter.name == "diu-v1"


def test_generator_settings_invalid_temperature_rejected() -> None:
    with pytest.raises(Exception):
        GeneratorSettings(generator_temperature=-0.1, _env_file=None)


def test_create_generator_local_backend() -> None:
    settings = GeneratorSettings(generator_backend="local", _env_file=None)
    generator = create_generator(settings)
    assert isinstance(generator, LocalGenerator)
    assert isinstance(generator, Generator)


def test_create_generator_openai_backend() -> None:
    settings = GeneratorSettings(
        generator_backend="openai",
        generator_api_base="https://api.example.com/v1",
        _env_file=None,
    )
    generator = create_generator(settings)
    assert isinstance(generator, OpenAICompatibleGenerator)
    assert isinstance(generator, Generator)


def test_create_generator_unknown_backend_rejected() -> None:
    settings = GeneratorSettings(generator_backend="local", _env_file=None)
    settings.generator_backend = "llama.cpp"
    with pytest.raises(ValueError):
        create_generator(settings)


def test_get_generator_settings_is_cached() -> None:
    first = get_generator_settings()
    second = get_generator_settings()
    assert first is second