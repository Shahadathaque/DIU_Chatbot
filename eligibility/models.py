"""Deterministic domain models for the DIU eligibility rule engine.

These models are pure data containers. They deliberately depend on no LLM,
HTTP, database, or frontend code so the eligibility engine stays a
self-contained deterministic evaluator.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


class RuleStatus(str, enum.Enum):
    """Evaluation result of one rule against an applicant's inputs."""

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    MISSING_INPUT = "missing_input"


class Decision(str, enum.Enum):
    """Overall deterministic eligibility decision."""

    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    INSUFFICIENT_INFORMATION = "insufficient_information"


@dataclass(frozen=True)
class RuleReference:
    """A provenance-linked reference to an official DIU source."""

    title: str
    url: str
    source_id: Optional[str] = None
    document_id: Optional[str] = None


@dataclass(frozen=True)
class ProgramRecord:
    """One recognized undergraduate program from the collected registry."""

    id: str
    name: str
    tags: Tuple[str, ...] = ()
    degree: Optional[str] = None
    faculty: Optional[str] = None
    references: Tuple[RuleReference, ...] = ()


@dataclass(frozen=True)
class ProgramRegistry:
    """Versioned, source-linked program registry (rules/programs.v1.json)."""

    registry_id: str
    version: str
    schema_version: str
    status: str
    description: str
    provenance: dict
    evidence_gaps: Tuple[str, ...]
    programs: Tuple[ProgramRecord, ...]
    content_hash: str

    def find(self, program: Optional[str]) -> Optional[ProgramRecord]:
        """Return the first registry record matching an identifier.

        Matching is case-insensitive against ``id``, any tag, and the full
        name. ``None`` is returned when no record matches.
        """
        if not program:
            return None
        query = program.strip().casefold()
        for record in self.programs:
            if record.id.casefold() == query:
                return record
            if any(tag.casefold() == query for tag in record.tags):
                return record
            if record.name.casefold() == query:
                return record
        return None


@dataclass(frozen=True)
class Rule:
    """One rule inside a ruleset."""

    rule_id: str
    name: str
    type: str
    required_inputs: Tuple[str, ...]
    decisive: bool
    description: str
    references: Tuple[RuleReference, ...] = ()
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Ruleset:
    """Versioned, source-linked eligibility ruleset."""

    ruleset_id: str
    version: str
    schema_version: str
    status: str
    decisive: bool
    description: str
    provenance: dict
    evidence_gaps: Tuple[str, ...]
    rules: Tuple[Rule, ...]
    content_hash: str


@dataclass(frozen=True)
class EligibilityInput:
    """Applicant inputs the deterministic engine can reason about."""

    program: Optional[str] = None
    ssc_gpa: Optional[float] = None
    hsc_gpa: Optional[float] = None
    group: Optional[str] = None
    diploma: Optional[bool] = None


@dataclass(frozen=True)
class RuleMatch:
    """Evaluation outcome of one rule for a given applicant."""

    rule_id: str
    name: str
    status: RuleStatus
    message: str
    references: Tuple[RuleReference, ...] = ()


@dataclass(frozen=True)
class EligibilityResult:
    """Full deterministic evaluation outcome."""

    decision: Decision
    matches: Tuple[RuleMatch, ...]
    reason: str
    ruleset_id: str
    ruleset_version: str
    ruleset_hash: str
    primary_source: Optional[RuleReference] = None


__all__ = [
    "Decision",
    "EligibilityInput",
    "EligibilityResult",
    "ProgramRecord",
    "ProgramRegistry",
    "Rule",
    "RuleMatch",
    "RuleReference",
    "RuleStatus",
    "Ruleset",
]
