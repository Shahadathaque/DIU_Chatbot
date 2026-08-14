"""Tests for LocalGenerator using mocked tokenizer and model (no downloads)."""

from __future__ import annotations

import torch

from rag.config import GeneratorSettings
from rag.generators.local import LocalGenerator, _resolve_device


class _FakeInputs(dict):
    def __init__(self, input_ids: torch.Tensor) -> None:
        super().__init__(input_ids=input_ids)

    def to(self, device: str) -> "_FakeInputs":
        return self


class _FakeTokenizer:
    def __init__(self) -> None:
        self.applied_messages = None
        self.encoded_prompt = None

    def apply_chat_template(
        self, messages, tokenize: bool = False, add_generation_prompt: bool = True
    ) -> str:
        self.applied_messages = list(messages)
        return "rendered-prompt"

    def __call__(self, prompt: str, return_tensors: str = "pt") -> _FakeInputs:
        self.encoded_prompt = prompt
        return _FakeInputs(torch.tensor([[101, 102, 103]]))

    def decode(self, tokens, skip_special_tokens: bool = True) -> str:
        return "  generated answer  "


class _FakeModel:
    def __init__(self) -> None:
        self.last_kwargs = None

    def generate(self, **kwargs) -> torch.Tensor:
        self.last_kwargs = dict(kwargs)
        return torch.tensor([[101, 102, 103, 104, 105, 106]])


def _settings(**overrides) -> GeneratorSettings:
    values = {"generator_device": "cpu", "_env_file": None}
    values.update(overrides)
    return GeneratorSettings(**values)


def test_local_generator_uses_injected_model_and_template() -> None:
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    messages = [{"role": "user", "content": "hello"}]
    generator = LocalGenerator(_settings(), model=model, tokenizer=tokenizer)

    output = generator.generate(messages)

    assert output == "generated answer"
    assert tokenizer.applied_messages == messages
    assert generator.device == "cpu"
    assert model.last_kwargs["max_new_tokens"] == 256
    assert model.last_kwargs["temperature"] == 0.0
    assert model.last_kwargs["top_p"] == 0.9
    assert model.last_kwargs["do_sample"] is False


def test_local_generator_temperature_zero_is_greedy() -> None:
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    generator = LocalGenerator(
        _settings(generator_temperature=0.0), model=model, tokenizer=tokenizer
    )

    generator.generate([{"role": "user", "content": "hello"}])

    assert model.last_kwargs["do_sample"] is False
    assert model.last_kwargs["temperature"] == 0.0


def test_local_generator_per_call_overrides() -> None:
    tokenizer = _FakeTokenizer()
    model = _FakeModel()
    generator = LocalGenerator(_settings(), model=model, tokenizer=tokenizer)

    generator.generate(
        [{"role": "user", "content": "hello"}],
        max_new_tokens=10,
        temperature=0.9,
        top_p=0.5,
    )

    assert model.last_kwargs["max_new_tokens"] == 10
    assert model.last_kwargs["temperature"] == 0.9
    assert model.last_kwargs["top_p"] == 0.5


def test_local_generator_lazy_loads_no_model_on_construction() -> None:
    generator = LocalGenerator(_settings())
    assert generator._model is None
    assert generator._tokenizer is None


def test_local_generator_keeps_lora_adapter_path_without_loading() -> None:
    model = _FakeModel()
    tokenizer = _FakeTokenizer()
    generator = LocalGenerator(
        _settings(generator_lora_adapter="adapters/diu-v1"),
        model=model,
        tokenizer=tokenizer,
    )

    assert str(generator._lora_adapter).endswith("diu-v1")
    generator.generate([{"role": "user", "content": "hello"}])
    assert model.last_kwargs is not None


def test_resolve_device_preferred_value_wins() -> None:
    assert _resolve_device("cpu") == "cpu"
    assert _resolve_device("mps") == "mps"


def test_resolve_device_auto_returns_available_or_cpu() -> None:
    assert _resolve_device(None) in {"mps", "cpu"}