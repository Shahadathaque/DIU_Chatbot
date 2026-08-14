"""Source response models matching contracts/api-contract.md."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    """One available DIU source."""

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    retrieved_at: Optional[str] = None
    category: Optional[str] = None


class SourcesResponse(BaseModel):
    """Response body for ``GET /api/sources``."""

    sources: List[SourceInfo] = Field(default_factory=list)