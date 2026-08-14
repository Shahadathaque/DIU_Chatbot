"""Transformers-based local generator running on Apple MPS or CPU.

The model and tokenizer are loaded lazily on the first ``generate`` call so
module import stays cheap and no weights are downloaded at import time.  The
default model is ``Qwen/Qwen2.5-1.5B-Instruct``, which covers English, Bangla,
and Banglish.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import torch

from rag.config import GeneratorSettings


def _resolve_device(preferred: Optional[str]) -> str:
    """Choose the best available device unless the caller prefers a specific one."""
    if preferred:
        return preferred
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class LocalGenerator:
    """Lazy-loading Transformers causal language model with chat-template prompting."""

    def __init__(
        self,
        settings: GeneratorSettings,
        *,
        model: Any = None,
        tokenizer: Any = None,
    ) -> None:
        self.model_name = settings.generator_model_name
        self.model_revision = settings.generator_model_revision
        self.max_new_tokens = settings.generator_max_new_tokens
        self.temperature = settings.generator_temperature
        self.top_p = settings.generator_top_p
        self.device = _resolve_device(settings.generator_device)
        self._lora_adapter = settings.generator_lora_adapter
        self._model = model
        self._tokenizer = tokenizer

    def _load(self) -> None:
        """Load tokenizer + model on first use; a later LoRA adapter is optional."""
        if self._model is not None and self._tokenizer is not None:
            return
        from transformers import AutoModelForCausalLM, AutoTokenizer

        kwargs: Dict[str, Any] = {}
        if self.model_revision:
            kwargs["revision"] = self.model_revision
        tokenizer = AutoTokenizer.from_pretrained(self.model_name, **kwargs)
        model = AutoModelForCausalLM.from_pretrained(
            self.model_name, torch_dtype=torch.float16, **kwargs
        )
        if self._lora_adapter is not None:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, str(self._lora_adapter))
        model.to(self.device)
        model.eval()
        self._tokenizer = tokenizer
        self._model = model

    def generate(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        self._load()
        prompt = self._tokenizer.apply_chat_template(
            list(messages), tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self.device)
        resolved_temperature = (
            self.temperature if temperature is None else temperature
        )
        resolved_max_tokens = (
            self.max_new_tokens if max_new_tokens is None else max_new_tokens
        )
        resolved_top_p = self.top_p if top_p is None else top_p
        with torch.inference_mode():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=resolved_max_tokens,
                do_sample=resolved_temperature > 0.0,
                temperature=resolved_temperature,
                top_p=resolved_top_p,
            )
        new_tokens = output_ids[0, inputs["input_ids"].shape[-1] :]
        text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
        return text.strip()


__all__ = ["LocalGenerator", "_resolve_device"]