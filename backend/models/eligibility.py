"""Eligibility request and response models matching contracts/api-contract.md.

The request model accepts ``ssc_gpa``/``hsc_gpa``/``group`` as optional and
``diploma`` as required per the contract, so the backend can return
``insufficient_information`` instead of forcing the client to invent values.
The response model mirrors the contract's ``status``/``reason``/``source``
shape; ``rule_matches`` and ``evidence_gaps`` are additive optional fields
exposing the deterministic rule-engine evidence without breaking the contract.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

EligibilityStatus = Literal[
    "eligible", "not_eligible", "insufficient_information"
]


class EligibilityRequest(BaseModel):
    """Request body for ``POST /api/eligibility``."""

    program: str = Field(..., min_length=1)
    ssc_gpa: Optional[float] = Field(None, ge=0.0, le=5.0)
    hsc_gpa: Optional[float] = Field(None, ge=0.0, le=5.0)
    group: Optional[str] = None
    diploma: bool

    @field_validator("program")
    @classmethod
    def program_must_be_non_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("program must be a non-empty string after trimming")
        return trimmed

    @field_validator("group")
    @classmethod
    def group_must_be_non_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("group must be a non-empty string after trimming")
        return trimmed


class EligibilitySource(BaseModel):
    """An official DIU source cited for an eligibility result."""

    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)


class EligibilityRuleMatch(BaseModel):
    """One rule-evaluation outcome exposed as additive evidence."""

    rule_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    status: Literal["pass", "fail", "not_applicable", "missing_input"]
    message: str = Field(..., min_length=1)


class EligibilityResponse(BaseModel):
    """Response body for ``POST /api/eligibility``."""

    status: EligibilityStatus
    reason: str = Field(..., min_length=1)
    source: Optional[EligibilitySource] = None
    rule_matches: List[EligibilityRuleMatch] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)


__all__ = [
    "EligibilityRequest",
    "EligibilityResponse",
    "EligibilityRuleMatch",
    "EligibilitySource",
    "EligibilityStatus",
]