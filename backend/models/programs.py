"""Program response models matching contracts/api-contract.md."""

from typing import List, Optional

from pydantic import BaseModel, Field


class Program(BaseModel):
    """One DIU program with stable identifiers and optional metadata."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    degree: Optional[str] = None
    faculty: Optional[str] = None
    admission_url: Optional[str] = None


class ProgramsResponse(BaseModel):
    """Response body for ``GET /api/programs``."""

    programs: List[Program] = Field(default_factory=list)