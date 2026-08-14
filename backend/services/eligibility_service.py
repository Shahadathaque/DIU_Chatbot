"""Eligibility service mapping the deterministic engine to the API contract.

The service is a thin adapter: it loads the versioned ruleset + program
registry, runs the pure ``EligibilityEngine``, and maps the result to the
contract response. The LLM is never involved in eligibility decisions.
"""

from __future__ import annotations

from typing import List, Optional

from backend.models.eligibility import (
    EligibilityRequest,
    EligibilityResponse,
    EligibilityRuleMatch,
    EligibilitySource,
)
from eligibility.engine import EligibilityEngine
from eligibility.loader import (
    DEFAULT_PROGRAMS_PATH,
    DEFAULT_RULESET_PATH,
    load_default_programs,
    load_default_ruleset,
    load_programs,
    load_ruleset,
)
from eligibility.models import EligibilityInput, RuleReference


class EligibilityService:
    """Evaluate an applicant against the versioned eligibility ruleset."""

    def __init__(
        self,
        engine: Optional[EligibilityEngine] = None,
        *,
        ruleset_path: Optional[str] = None,
        programs_path: Optional[str] = None,
    ) -> None:
        if engine is not None:
            self._engine = engine
            return
        ruleset = (
            load_default_ruleset()
            if ruleset_path is None
            else load_ruleset(ruleset_path)
        )
        programs = (
            load_default_programs()
            if programs_path is None
            else load_programs(programs_path)
        )
        self._engine = EligibilityEngine(ruleset, registry=programs)

    @property
    def engine(self) -> EligibilityEngine:
        return self._engine

    def check(self, payload: EligibilityRequest) -> EligibilityResponse:
        inputs = EligibilityInput(
            program=payload.program,
            ssc_gpa=payload.ssc_gpa,
            hsc_gpa=payload.hsc_gpa,
            group=payload.group,
            diploma=payload.diploma,
        )
        result = self._engine.evaluate(inputs)
        return EligibilityResponse(
            status=result.decision.value,
            reason=result.reason,
            source=_source(result.primary_source),
            rule_matches=_rule_matches(result.matches),
            evidence_gaps=list(self._engine.ruleset.evidence_gaps),
        )


def _source(reference: Optional[RuleReference]) -> Optional[EligibilitySource]:
    if reference is None:
        return None
    return EligibilitySource(title=reference.title, url=reference.url)


def _rule_matches(matches: tuple) -> List[EligibilityRuleMatch]:
    return [
        EligibilityRuleMatch(
            rule_id=match.rule_id,
            name=match.name,
            status=match.status.value,
            message=match.message,
        )
        for match in matches
    ]


__all__ = ["EligibilityService"]
