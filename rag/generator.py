"""Configurable LLM generator interface for grounded DIU answers.

Heavy optional dependencies (transformers, torch, peft) are loaded lazily by the
concrete adapters, never at import time, so importing this module stays safe for
unit tests and the backend.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, Sequence, runtime_checkable

from rag.config import GeneratorSettings, get_generator_settings


class GeneratorError(Exception):
    """Base error raised by generator backends."""


class GeneratorUnavailableError(GeneratorError):
    """The generator backend is unreachable or failed to produce an answer."""


@runtime_checkable
class Generator(Protocol):
    """Small dependency-injection boundary used by services and factories.

    Structural interface: any object exposing ``model_name``, ``model_revision``
    and a ``generate`` method satisfies the protocol.
    """

    model_name: str
    model_revision: Optional[str]

    def generate(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """Generate a completion for a chat-style ``messages`` list."""
        ...


def create_generator(settings: Optional[GeneratorSettings] = None) -> Generator:
    """Construct the configured generator backend.

    ``local`` runs a Transformers model on-device (Apple MPS or CPU); ``openai``
    calls any OpenAI-compatible HTTP endpoint.  Adapters are imported lazily so a
    single ``Generator`` protocol covers all four research cells.
    """
    settings = settings or get_generator_settings()
    if settings.generator_backend == "local":
        from rag.generators.local import LocalGenerator

        return LocalGenerator(settings)
    if settings.generator_backend == "openai":
        from rag.generators.openai_compatible import OpenAICompatibleGenerator

        return OpenAICompatibleGenerator(settings)
    raise ValueError(
        "unknown GENERATOR_BACKEND {!r}; expected 'local' or 'openai'".format(
            settings.generator_backend
        )
    )


__all__ = [
    "Generator",
    "GeneratorError",
    "GeneratorUnavailableError",
    "create_generator",
]