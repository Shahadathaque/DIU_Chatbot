"""Chat request and response models matching contracts/api-contract.md."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Language = Literal["en", "bn", "banglish"]
Confidence = Literal["high", "medium", "low"]


class ChatTurn(BaseModel):
    """One prior conversational turn supplied by the client for context."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    """Request body for ``POST /api/chat``."""

    message: str = Field(..., min_length=1, max_length=2000)
    language: Language
    history: Optional[List[ChatTurn]] = None

    @field_validator("message")
    @classmethod
    def message_must_be_non_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("message must be a non-empty string after trimming")
        if len(trimmed) > 2000:
            raise ValueError("message must be at most 2000 characters after trimming")
        return trimmed


class ChatSource(BaseModel):
    """An official DIU source cited for an answer."""

    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """Response body for ``POST /api/chat``."""

    answer: str = Field(..., min_length=1)
    sources: List[ChatSource] = Field(default_factory=list)
    confidence: Confidence
    language: Language