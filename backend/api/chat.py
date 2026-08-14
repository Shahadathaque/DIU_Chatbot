"""Chat endpoint (POST /api/chat)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.models.chat import ChatRequest, ChatResponse
from backend.services.chat_service import ChatService
from rag.generator import Generator, create_generator
from rag.retriever import create_retriever

router = APIRouter(tags=["chat"])


@lru_cache
def get_generator() -> Generator:
    """Build the configured generator backend (lazy; no weights at import)."""
    return create_generator()


@lru_cache
def get_chat_service() -> ChatService:
    """Build the production chat service backed by the real retriever."""
    return ChatService(create_retriever(), generator=get_generator())


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return service.answer(payload.message, payload.language, history=payload.history)