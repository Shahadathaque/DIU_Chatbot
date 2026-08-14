"""Eligibility evaluation for the DIU M5 baseline (M5-B).

Two independent tiers are evaluated and reported separately:

- **Real tier** (``eligibility_real``): the shipped v1 ruleset + program registry
  is run against each real applicant profile. The v1 ruleset is deliberately
  non-decisive because the collected official DIU sources publish no
  GPA/group/program thresholds, so the only correct decision is
  ``insufficient_information``. Per the M5 audit, a real-tier
  ``insufficient_information`` result is NOT a failure; it is the honest answer.
- **Synthetic tier** (``eligibility_synthetic``): a decisive fixture ruleset is
  built from each question's ``fixture_rule`` (never presented as real DIU
  policy) to exercise ``eligible`` / ``not_eligible`` / ``insufficient_information``
  engine behavior, then compared to the expected outcome.

Decisions come exclusively from the deterministic ``EligibilityEngine``; the LLM
is never consulted for eligibility (AGENTS.md rule 15-16).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eligibility.engine import EligibilityEngine
from eligibility.loader import (
    DEFAULT_PROGRAMS_PATH,
    DEFAULT_RULESET_PATH,
    load_default_programs,
    load_default_ruleset,
)
from eligibility.models import (
    Decision,
    EligibilityInput,
    ProgramRecord,
    ProgramRegistry,
    Rule,
    RuleReference,
    RuleStatus,
    Ruleset,
)
from evaluation.schema import EvalDataset, EvalQuestion, PROJECT_ROOT, load_eval_dataset

DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "evaluation" / "v1"

_FIXTURE_URL = "https://daffodilvarsity.edu.bd/fixture-rule-source"
_SUPPORTED_FIELDS = {"program", "ssc_gpa", "hsc_gpa", "group", "diploma"}
_GPA_COUNTERPARTS = {"ssc_gpa": "hsc_gpa", "hsc_gpa": "ssc_gpa"}


class EligibilityEvalError(RuntimeError):
    """Raised when eligibility evaluation cannot run or save results."""


def _fixture_reference() -> RuleReference:
    return RuleReference(
        title="Synthetic fixture rule (engine test only)",
        url=_FIXTURE_URL,
        source_id="SYNTHETIC-FIXTURE",
        document_id="synthetic-fixture-001",
    )


def _eligibility_input(payload: Optional[Dict[str, Any]]) -> EligibilityInput:
    return EligibilityInput(
        **{key: value for key, value in (payload or {}).items() if key in _SUPPORTED_FIELDS}
    )


def _rule(
    rule_id: str, rule_type: str, *, field: str, params: Optional[Dict[str, Any]] = None
) -> Rule:
    resolved_params = dict(params or {})
    resolved_params.setdefault("field", field)
    required = (field,)
    return Rule(
        rule_id=rule_id,
        name="Fixture rule {}".format(rule_id),
        type=rule_type,
        required_inputs=required,
        decisive=True,
        description="Decisive synthetic fixture rule (engine test only).",
        references=(_fixture_reference(),),
        params=resolved_params,
    )


def _synthetic_registry(known_programs: List[str]) -> ProgramRegistry:
    programs = tuple(
        ProgramRecord(id=program_id, name=program_id, tags=(program_id,))
        for program_id in known_programs
    )
    return ProgramRegistry(
        registry_id="synthetic-fixture-registry-v1",
        version="1.0.0",
        schema_version="1.0",
        status="synthetic",
        description="Synthetic program registry built from fixture rules.",
        provenance={"sources": [{"title": "Synthetic fixture", "url": _FIXTURE_URL}]},
        evidence_gaps=(),
        programs=programs,
        content_hash=hashlib.sha256(
            json.dumps(known_programs, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    )


def _synthetic_ruleset(question: EvalQuestion) -> Tuple[Ruleset, Optional[ProgramRegistry]]:
    """Build a decisive synthetic ruleset from one question's ``fixture_rule``.

    For ``numeric_range`` fixtures whose input also supplies the counterpart GPA
    field (ssc_gpa <-> hsc_gpa), a second decisive rule on that counterpart is
    added so multi-rule fixtures (e.g. elig-syn-07/08) evaluate both bounds.
    """
    fixture = question.fixture_rule or {}
    rule_type = fixture.get("type")
    field = fixture.get("field", "")
    registry: Optional[ProgramRegistry] = None

    if rule_type == "numeric_range":
        params: Dict[str, Any] = {"min": fixture["min"]} if "min" in fixture else {}
        if "max" in fixture:
            params["max"] = fixture["max"]
        rules = [_rule("F-001", "numeric_range", field=field, params=params)]
        counterpart = _GPA_COUNTERPARTS.get(field)
        if counterpart and counterpart in (question.eligibility_input or {}):
            rules.append(
                _rule("F-002", "numeric_range", field=counterpart, params=dict(params))
            )
    elif rule_type == "program_registry":
        known = list(fixture.get("known", []))
        rules = [
            _rule(
                "F-001",
                "program_registry",
                field=field or "program",
                params={"known": known},
            )
        ]
        registry = _synthetic_registry(known)
    elif rule_type == "diploma_pathway":
        rules = [_rule("F-001", "diploma_pathway", field=field or "diploma")]
    else:
        raise EligibilityEvalError(
            f"{question.id}: unsupported synthetic fixture rule type {rule_type!r}"
        )

    content_hash = hashlib.sha256(
        json.dumps(
            {"fixture_rule": fixture, "input": question.eligibility_input},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    ruleset = Ruleset(
        ruleset_id="synthetic-fixture-rules-v1",
        version="1.0.0",
        schema_version="1.0",
        status="synthetic",
        decisive=True,
        description="Decisive synthetic fixture ruleset for engine evaluation only.",
        provenance={"sources": [{"title": "Synthetic fixture", "url": _FIXTURE_URL}]},
        evidence_gaps=(),
        rules=tuple(rules),
        content_hash=content_hash,
    )
    return ruleset, registry


def _tier_payload(
    tier: str, records: List[Dict[str, Any]], *, strict_count: int
) -> Dict[str, Any]:
    exact_matches = sum(1 for record in records if record["correct"])
    return {
        "count": len(records),
        "expected_insufficient_information_count": sum(
            1 for record in records if record["expected_outcome"] == Decision.INSUFFICIENT_INFORMATION.value
        ),
        "exact_match_count": exact_matches,
        "accuracy": round(exact_matches / len(records), 4) if records else 0.0,
        "strict_expected_vs_actual_matches": strict_count,
        "records": records,
    }


def run_eligibility_eval(
    dataset: Optional[EvalDataset] = None,
    *,
    ruleset_path: Optional[str] = None,
    programs_path: Optional[str] = None,
    results_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Evaluate the real and synthetic eligibility tiers against the rule engine."""
    resolved_dataset = dataset or load_eval_dataset()
    ruleset = (
        load_default_ruleset()
        if ruleset_path is None
        else _load_ruleset_path(ruleset_path)
    )
    programs = (
        load_default_programs()
        if programs_path is None
        else _load_programs_path(programs_path)
    )
    real_engine = EligibilityEngine(ruleset, registry=programs)

    real_records: List[Dict[str, Any]] = []
    synthetic_records: List[Dict[str, Any]] = []
    strict_matches = 0
    real_strict = 0
    synthetic_strict = 0

    for question in resolved_dataset.questions:
        if question.category not in {"eligibility_real", "eligibility_synthetic"}:
            continue
        if question.is_eligibility_real:
            result = real_engine.evaluate(_eligibility_input(question.eligibility_input))
            expected = question.expected_outcome
            actual = result.decision.value
            # Per the M5 audit, real-tier insufficient_information is the honest
            # result of a non-decisive ruleset, not a failure.
            strict = expected == actual
            real_strict += 1 if strict else 0
            real_records.append(
                {
                    "id": question.id,
                    "question": question.question,
                    "expected_outcome": expected,
                    "actual_decision": actual,
                    "correct": strict,
                    "reason": result.reason,
                    "ruleset_id": result.ruleset_id,
                    "ruleset_version": result.ruleset_version,
                    "ruleset_hash": result.ruleset_hash,
                }
            )
        else:
            fixture_ruleset, fixture_registry = _synthetic_ruleset(question)
            engine = EligibilityEngine(fixture_ruleset, registry=fixture_registry)
            result = engine.evaluate(_eligibility_input(question.eligibility_input))
            expected = question.expected_outcome
            actual = result.decision.value
            strict = expected == actual
            synthetic_strict += 1 if strict else 0
            synthetic_records.append(
                {
                    "id": question.id,
                    "question": question.question,
                    "expected_outcome": expected,
                    "actual_decision": actual,
                    "correct": strict,
                    "reason": result.reason,
                    "ruleset_id": fixture_ruleset.ruleset_id,
                    "ruleset_hash": fixture_ruleset.content_hash,
                }
            )

    payload: Dict[str, Any] = {
        "dataset": {
            "dataset_id": resolved_dataset.dataset_id,
            "version": resolved_dataset.version,
            "content_hash": resolved_dataset.content_hash,
        },
        "ruleset": {
            "ruleset_id": ruleset.ruleset_id,
            "version": ruleset.version,
            "decisive": ruleset.decisive,
            "content_hash": ruleset.content_hash,
        },
        "program_registry": {
            "registry_id": programs.registry_id,
            "version": programs.version,
            "content_hash": programs.content_hash,
        },
        "eligibility_real": _tier_payload("real", real_records, strict_count=real_strict),
        "eligibility_synthetic": _tier_payload(
            "synthetic", synthetic_records, strict_count=synthetic_strict
        ),
        "note": (
            "Real tier uses the non-decisive v1 ruleset; insufficient_information "
            "is the honest outcome and is not counted as a failure. Synthetic tier "
            "uses decisive fixture rulesets marked SYNTHETIC-FIXTURE (engine test "
            "only, never real DIU policy)."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": "diu-m5-eligibility-eval-v1",
    }

    resolved_dir = Path(results_dir or DEFAULT_RESULTS_DIR)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    target = Path(out_path or (resolved_dir / "eligibility.json"))
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _load_ruleset_path(path: str) -> Ruleset:
    from eligibility.loader import load_ruleset

    return load_ruleset(path)


def _load_programs_path(path: str) -> ProgramRegistry:
    from eligibility.loader import load_programs

    return load_programs(path)


__all__ = [
    "DEFAULT_RESULTS_DIR",
    "EligibilityEvalError",
    "_synthetic_registry",
    "_synthetic_ruleset",
    "run_eligibility_eval",
]