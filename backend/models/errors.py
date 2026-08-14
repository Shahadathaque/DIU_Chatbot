"""Contract-compliant API error models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """One field-level validation or application error."""

    field: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ErrorBody(BaseModel):
    """The stable application error envelope."""

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    details: List[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Top-level error response matching contracts/api-contract.md."""

    error: ErrorBody