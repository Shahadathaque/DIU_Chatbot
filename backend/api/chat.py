"""Chat endpoint (POST /api/chat)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import AsyncIterator

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from backend.core.errors import ApiError, ArtifactUnavailableError
from backend.core.rate_limit import enforce_chat_rate_limit
from backend.models.chat import ChatRequest, ChatResponse
from backend.services.chat_service import ChatService
from rag.generator import Generator, create_generator
from rag.config import get_rag_settings
from rag.retriever import create_retriever

router = APIRouter(tags=["chat"])


@lru_cache
def get_generator() -> Generator:
    """Build the configured generator backend (lazy; no weights at import)."""
    return create_generator()


@lru_cache
def _build_chat_service() -> ChatService:
    """Build and cache the production chat service after request validation."""
    settings = get_rag_settings()
    if settings.rag_vector_backend == "local" and not settings.rag_local_store_path.is_file():
        raise ArtifactUnavailableError(
            artifact="local knowledge base",
            path=str(settings.rag_local_store_path),
            recovery="Restore the private index or run scripts/build_knowledge_base.py --rebuild.",
        )
    try:
        return ChatService(create_retriever(settings), generator=get_generator())
    except ArtifactUnavailableError:
        raise
    except (OSError, RuntimeError, ValueError, ConnectionError) as error:
        raise ApiError(
            status_code=503,
            code="knowledge_service_unavailable",
            message="The admission knowledge service is not ready.",
            details=[{"field": "reason", "message": str(error)}],
        ) from error


def get_chat_service(payload: ChatRequest = Body(...)) -> ChatService:
    """Resolve chat dependencies only after FastAPI validates the request body."""
    del payload
    return _build_chat_service()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    _rate_limit: None = Depends(enforce_chat_rate_limit),
) -> ChatResponse:
    return service.answer(payload.message, payload.language, history=payload.history)


def _sse_event(payload: object, *, event: str | None = None) -> str:
    """Encode one JSON Server-Sent Event without leaking implementation details."""

    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _text_tokens(text: str) -> list[str]:
    """Split a completed answer into readable SSE chunks.

    The local Transformers adapter is synchronous, so this fallback cannot
    expose model-native token timing. It still gives clients a stable streaming
    contract and allows hosted adapters to be upgraded independently.
    """

    chunks: list[str] = []
    current = ""
    for character in text:
        current += character
        if character.isspace() or character in ".!?;:\n":
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks or [text]


@router.post("/api/chat/stream", response_class=StreamingResponse)
async def stream_chat(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    _rate_limit: None = Depends(enforce_chat_rate_limit),
) -> StreamingResponse:
    """Stream a validated chat response as SSE without changing ``/api/chat``."""

    async def events() -> AsyncIterator[str]:
        response = await run_in_threadpool(
            service.answer,
            payload.message,
            payload.language,
            payload.history,
        )
        full = ""
        for token in _text_tokens(response.answer):
            full += token
            yield _sse_event({"token": token, "full": full})
        yield _sse_event({"response": response.model_dump()}, event="done")

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
