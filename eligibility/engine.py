"""Pure deterministic DIU eligibility evaluator.

This module has no LLM, HTTP, database, or network dependency. It interprets
the JSON-loaded ruleset against applicant inputs and returns an honest
``EligibilityResult``.

Decision precedence (per TASK-03):

1. Any decisive failed rule -> not_eligible
2. Required missing information -> insufficient_information
3. If all available rules pass but the ruleset is not decisive enough to
   establish actual admission eligibility -> insufficient_information
4. ``eligible`` is allowed ONLY when the ruleset contains sufficient decisive
   evidence for eligibility.

The current v1 ruleset is intentionally non-decisive (``decisive=false``), so
even a complete applicant who passes every structural rule receives
``insufficient_information`` rather than a fabricated positive decision.
"""

from __future__ import annotations

from typing import Optional

from eligibility.models import (
    Decision,
    EligibilityInput,
    EligibilityResult,
    ProgramRegistry,
    Rule,
    RuleMatch,
    RuleReference,
    RuleStatus,
    Ruleset,
)


class EligibilityEngine:
    """Evaluate a loaded ruleset against applicant inputs.

    ``registry`` is only required when a rule of type ``program_registry`` is
    present. It is kept as an explicit constructor argument so the engine stays
    a pure function of the loaded data.
    """

    def __init__(self, ruleset: Ruleset, registry: Optional[ProgramRegistry] = None) -> None:
        self._ruleset = ruleset
        self._registry = registry
        self._decisive_by_rule = {rule.rule_id: rule.decisive for rule in ruleset.rules}

    @property
    def ruleset(self) -> Ruleset:
        return self._ruleset

    def evaluate(self, inputs: EligibilityInput) -> EligibilityResult:
        matches = tuple(self._evaluate_rule(rule, inputs) for rule in self._ruleset.rules)
        decision = self._decide(matches)
        reason = self._build_reason(decision, matches)
        return EligibilityResult(
            decision=decision,
            matches=matches,
            reason=reason,
            ruleset_id=self._ruleset.ruleset_id,
            ruleset_version=self._ruleset.version,
            ruleset_hash=self._ruleset.content_hash,
            primary_source=self._primary_source(matches),
        )

    def _evaluate_rule(self, rule: Rule, inputs: EligibilityInput) -> RuleMatch:
        if rule.type == "program_registry":
            return self._program_registry(rule, inputs)
        if rule.type == "diploma_pathway":
            return self._diploma_pathway(rule, inputs)
        if rule.type == "numeric_range":
            return self._numeric_range(rule, inputs)
        return RuleMatch(
            rule_id=rule.rule_id,
            name=rule.name,
            status=RuleStatus.NOT_APPLICABLE,
            message=f"Unsupported rule type {rule.type!r}.",
            references=rule.references,
        )

    def _program_registry(self, rule: Rule, inputs: EligibilityInput) -> RuleMatch:
        program = inputs.program
        if program is None or not program.strip():
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.MISSING_INPUT,
                message="A program identifier is required to evaluate program recognition.",
                references=rule.references,
            )
        record = self._registry.find(program) if self._registry else None
        if record is not None:
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.PASS,
                message=(
                    f"The program {program.strip()!r} is a recognized undergraduate program "
                    f"in the collected DIU program registry."
                ),
                references=record.references or rule.references,
            )
        return RuleMatch(
            rule_id=rule.rule_id,
            name=rule.name,
            status=RuleStatus.NOT_APPLICABLE,
            message=(
                f"The program {program.strip()!r} is not present in the collected DIU "
                "program registry. The registry is known to be incomplete, so this does "
                "not prove the program is not recognized; it cannot establish admission "
                "eligibility."
            ),
            references=rule.references,
        )

    @staticmethod
    def _diploma_pathway(rule: Rule, inputs: EligibilityInput) -> RuleMatch:
        if inputs.diploma is None:
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.MISSING_INPUT,
                message="A diploma flag is required to evaluate the admission pathway.",
                references=rule.references,
            )
        pathway = "diploma" if inputs.diploma else "SSC/HSC (non-diploma)"
        return RuleMatch(
            rule_id=rule.rule_id,
            name=rule.name,
            status=RuleStatus.PASS,
            message=f"The {pathway} pathway is a documented bachelor admission pathway.",
            references=rule.references,
        )

    @staticmethod
    def _numeric_range(rule: Rule, inputs: EligibilityInput) -> RuleMatch:
        """Evaluate a generic numeric bound (used by fixture/expansion rules).

        This evaluator is intentionally generic: the bound itself is defined in
        rule ``params`` (``field`` plus optional ``min``/``max``), never
        hard-coded here. The real v1 DIU ruleset does not use this type because
        the collected sources publish no GPA/group thresholds.
        """
        params = rule.params
        field = params.get("field")
        if not isinstance(field, str) or not field:
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.NOT_APPLICABLE,
                message="Rule params must define a 'field' to evaluate.",
                references=rule.references,
            )
        if not hasattr(inputs, field):
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.NOT_APPLICABLE,
                message=f"Field {field!r} is not a supported applicant input.",
                references=rule.references,
            )
        value = getattr(inputs, field)
        if value is None:
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.MISSING_INPUT,
                message=f"The input field {field!r} is required but was not provided.",
                references=rule.references,
            )
        minimum = params.get("min")
        maximum = params.get("max")
        if minimum is not None and value < minimum:
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.FAIL,
                message=f"{field} {value} is below the required minimum of {minimum}.",
                references=rule.references,
            )
        if maximum is not None and value > maximum:
            return RuleMatch(
                rule_id=rule.rule_id,
                name=rule.name,
                status=RuleStatus.FAIL,
                message=f"{field} {value} is above the required maximum of {maximum}.",
                references=rule.references,
            )
        return RuleMatch(
            rule_id=rule.rule_id,
            name=rule.name,
            status=RuleStatus.PASS,
            message=f"{field} {value} satisfies the configured range.",
            references=rule.references,
        )

    def _decide(self, matches: tuple[RuleMatch, ...]) -> Decision:
        if any(
            match.status == RuleStatus.FAIL and self._decisive_by_rule.get(match.rule_id, False)
            for match in matches
        ):
            return Decision.NOT_ELIGIBLE
        if any(match.status == RuleStatus.MISSING_INPUT for match in matches):
            return Decision.INSUFFICIENT_INFORMATION
        if any(match.status in (RuleStatus.FAIL, RuleStatus.NOT_APPLICABLE) for match in matches):
            return Decision.INSUFFICIENT_INFORMATION
        if not self._ruleset.decisive:
            return Decision.INSUFFICIENT_INFORMATION
        if matches and all(match.status == RuleStatus.PASS for match in matches):
            return Decision.ELIGIBLE
        return Decision.INSUFFICIENT_INFORMATION

    def _build_reason(self, decision: Decision, matches: tuple[RuleMatch, ...]) -> str:
        parts = [f"Decision: {decision.value}."]
        for match in matches:
            parts.append(
                f"{match.rule_id} ({match.name}): {match.status.value} - {match.message}"
            )
        if decision == Decision.INSUFFICIENT_INFORMATION:
            gaps = self._ruleset.evidence_gaps
            if gaps:
                parts.append("Evidence gaps in the collected official DIU sources:")
                parts.extend(f"- {gap}" for gap in gaps)
        return "\n".join(parts)

    def _primary_source(self, matches: tuple[RuleMatch, ...]) -> Optional[RuleReference]:
        """Pick the strongest honest source reference for the API response.

        A passing program-registry match's reference is preferred (the official
        programs page confirms the program is recognized). If no program is
        recognized, the first passing rule's reference is used so the API still
        cites a source that supports a verified structural finding (for example
        the documented diploma pathway). No reference is returned when nothing
        positive was established.
        """
        for rule in self._ruleset.rules:
            if rule.type != "program_registry":
                continue
            match = next((m for m in matches if m.rule_id == rule.rule_id), None)
            if match is not None and match.status == RuleStatus.PASS and match.references:
                return match.references[0]
        for match in matches:
            if match.status == RuleStatus.PASS and match.references:
                return match.references[0]
        return None


__all__ = ["EligibilityEngine"]
