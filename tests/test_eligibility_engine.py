"""Unit tests for the deterministic eligibility engine and rule loaders.

Eligible/not_eligible behavior is exercised with synthetic fixture rulesets
because the real DIU v1 rules intentionally cannot make those decisions: the
collected official DIU sources do not publish GPA/group/program thresholds.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from eligibility.engine import EligibilityEngine
from eligibility.loader import (
    DEFAULT_PROGRAMS_PATH,
    DEFAULT_RULESET_PATH,
    RulesetLoadError,
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Fixture construction helpers
# --------------------------------------------------------------------------

def _fixture_reference(title: str = "Fixture source") -> RuleReference:
    return RuleReference(
        title=title,
        url="https://daffodilvarsity.edu.bd/fixture-rule-source",
        source_id="FIXTURE-001",
        document_id="fixture-001",
    )


def _fixture_rule(
    rule_id: str = "F-001",
    *,
    field: str = "ssc_gpa",
    minimum: float = 3.0,
    maximum: float | None = None,
    decisive: bool = True,
    name: str = "Fixture numeric rule",
) -> Rule:
    params: dict = {"field": field, "min": minimum}
    if maximum is not None:
        params["max"] = maximum
    return Rule(
        rule_id=rule_id,
        name=name,
        type="numeric_range",
        required_inputs=(field,),
        decisive=decisive,
        description="Synthetic rule for engine tests.",
        references=(_fixture_reference(),),
        params=params,
    )


def _fixture_ruleset(*rules: Rule, decisive: bool = True) -> Ruleset:
    payload = json.dumps(
        [
            {"rule_id": rule.rule_id, "params": rule.params, "decisive": rule.decisive}
            for rule in rules
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return Ruleset(
        ruleset_id="fixture-rules-v1",
        version="1.0.0",
        schema_version="1.0",
        status="test",
        decisive=decisive,
        description="Synthetic decisive ruleset.",
        provenance={"sources": []},
        evidence_gaps=(),
        rules=rules,
        content_hash=content_hash,
    )


def _fixture_registry() -> ProgramRegistry:
    record = ProgramRecord(
        id="cse",
        name="B. Sc. in Computer Science and Engineering",
        tags=("CSE",),
        degree="B.Sc.",
        references=(_fixture_reference("Programs"),),
    )
    return ProgramRegistry(
        registry_id="programs-fixture",
        version="1.0.0",
        schema_version="1.0",
        status="test",
        description="Fixture registry.",
        provenance={"sources": []},
        evidence_gaps=(),
        programs=(record,),
        content_hash=hashlib.sha256(b"fixture-registry").hexdigest(),
    )


# --------------------------------------------------------------------------
# A.1 + A.2: synthetic decisive pass/fail
# --------------------------------------------------------------------------

def test_decisive_rule_pass_is_eligible() -> None:
    engine = EligibilityEngine(_fixture_ruleset(_fixture_rule(minimum=3.0)))
    result = engine.evaluate(EligibilityInput(ssc_gpa=4.0, diploma=False))
    assert result.decision == Decision.ELIGIBLE
    assert result.matches[0].status == RuleStatus.PASS


def test_decisive_rule_fail_is_not_eligible() -> None:
    engine = EligibilityEngine(_fixture_ruleset(_fixture_rule(minimum=3.0)))
    result = engine.evaluate(EligibilityInput(ssc_gpa=2.5, diploma=False))
    assert result.decision == Decision.NOT_ELIGIBLE
    assert result.matches[0].status == RuleStatus.FAIL


def test_non_decisive_failure_is_insufficient_information() -> None:
    engine = EligibilityEngine(
        _fixture_ruleset(_fixture_rule(minimum=3.0, decisive=False))
    )
    result = engine.evaluate(EligibilityInput(ssc_gpa=2.5, diploma=False))
    assert result.decision == Decision.INSUFFICIENT_INFORMATION


# --------------------------------------------------------------------------
# A.3: missing required input
# --------------------------------------------------------------------------

def test_missing_required_field_is_insufficient_information() -> None:
    engine = EligibilityEngine(_fixture_ruleset(_fixture_rule(minimum=3.0)))
    result = engine.evaluate(EligibilityInput(ssc_gpa=None, diploma=False))
    assert result.decision == Decision.INSUFFICIENT_INFORMATION
    assert result.matches[0].status == RuleStatus.MISSING_INPUT


# --------------------------------------------------------------------------
# A.4: real DIU v1 rules + complete applicant
# --------------------------------------------------------------------------

def test_real_v1_rules_complete_applicant_is_insufficient_information() -> None:
    ruleset = load_default_ruleset()
    registry = load_default_programs()
    engine = EligibilityEngine(ruleset, registry=registry)

    result = engine.evaluate(
        EligibilityInput(
            program="CSE",
            ssc_gpa=5.0,
            hsc_gpa=5.0,
            group="Science",
            diploma=False,
        )
    )

    assert result.decision == Decision.INSUFFICIENT_INFORMATION
    statuses = {match.rule_id: match.status for match in result.matches}
    assert statuses["R-001"] == RuleStatus.PASS
    assert statuses["R-002"] == RuleStatus.PASS
    assert result.primary_source is not None
    assert result.primary_source.url.startswith("https://")


# --------------------------------------------------------------------------
# A.5: unknown program
# --------------------------------------------------------------------------

def test_unknown_program_is_insufficient_information() -> None:
    ruleset = load_default_ruleset()
    registry = load_default_programs()
    engine = EligibilityEngine(ruleset, registry=registry)

    result = engine.evaluate(EligibilityInput(program="SomeOtherProgram", diploma=False))

    assert result.decision == Decision.INSUFFICIENT_INFORMATION
    r001 = next(match for match in result.matches if match.rule_id == "R-001")
    assert r001.status == RuleStatus.NOT_APPLICABLE


# --------------------------------------------------------------------------
# A.6 + A.7: diploma pathways
# --------------------------------------------------------------------------

def test_diploma_true_pathway_is_recognized() -> None:
    ruleset = load_default_ruleset()
    registry = load_default_programs()
    engine = EligibilityEngine(ruleset, registry=registry)

    result = engine.evaluate(EligibilityInput(program="CSE", diploma=True))

    assert result.decision == Decision.INSUFFICIENT_INFORMATION
    r002 = next(match for match in result.matches if match.rule_id == "R-002")
    assert r002.status == RuleStatus.PASS
    assert "diploma pathway" in r002.message.casefold()


def test_diploma_false_pathway_is_recognized() -> None:
    ruleset = load_default_ruleset()
    registry = load_default_programs()
    engine = EligibilityEngine(ruleset, registry=registry)

    result = engine.evaluate(EligibilityInput(program="CSE", diploma=False))

    assert result.decision == Decision.INSUFFICIENT_INFORMATION
    r002 = next(match for match in result.matches if match.rule_id == "R-002")
    assert r002.status == RuleStatus.PASS


# --------------------------------------------------------------------------
# A.8: boundary GPA values
# --------------------------------------------------------------------------

def test_boundary_gpa_values_are_inclusive() -> None:
    rule = _fixture_rule(minimum=0.0, maximum=5.0)
    engine = EligibilityEngine(_fixture_ruleset(rule))

    low = engine.evaluate(EligibilityInput(ssc_gpa=0.0, diploma=False))
    high = engine.evaluate(EligibilityInput(ssc_gpa=5.0, diploma=False))
    above = engine.evaluate(EligibilityInput(ssc_gpa=5.1, diploma=False))

    assert low.decision == Decision.ELIGIBLE
    assert high.decision == Decision.ELIGIBLE
    assert above.decision == Decision.NOT_ELIGIBLE


# --------------------------------------------------------------------------
# A.9: conflicting-rule behavior
# --------------------------------------------------------------------------

def test_conflicting_rules_decisive_failure_wins() -> None:
    pass_rule = _fixture_rule("F-PASS", field="ssc_gpa", minimum=3.0)
    fail_rule = _fixture_rule("F-FAIL", field="hsc_gpa", minimum=4.5)
    engine = EligibilityEngine(_fixture_ruleset(pass_rule, fail_rule))

    result = engine.evaluate(EligibilityInput(ssc_gpa=4.0, hsc_gpa=3.0, diploma=False))

    assert result.decision == Decision.NOT_ELIGIBLE
    statuses = {match.rule_id: match.status for match in result.matches}
    assert statuses["F-PASS"] == RuleStatus.PASS
    assert statuses["F-FAIL"] == RuleStatus.FAIL


def test_missing_input_wins_over_passing_rules() -> None:
    pass_rule = _fixture_rule("F-PASS", field="ssc_gpa", minimum=3.0)
    missing_rule = _fixture_rule("F-MISSING", field="hsc_gpa", minimum=3.0)
    engine = EligibilityEngine(_fixture_ruleset(pass_rule, missing_rule))

    result = engine.evaluate(EligibilityInput(ssc_gpa=4.0, hsc_gpa=None, diploma=False))

    assert result.decision == Decision.INSUFFICIENT_INFORMATION
    assert result.matches[1].status == RuleStatus.MISSING_INPUT


# --------------------------------------------------------------------------
# A.10: source linkage
# --------------------------------------------------------------------------

def test_rules_carry_source_linkage() -> None:
    ruleset = load_default_ruleset()
    registry = load_default_programs()
    engine = EligibilityEngine(ruleset, registry=registry)

    result = engine.evaluate(EligibilityInput(program="CSE", diploma=False))

    r001 = next(match for match in result.matches if match.rule_id == "R-001")
    assert r001.references
    assert r001.references[0].url == "https://daffodilvarsity.edu.bd/programs"
    assert r001.references[0].title
    assert result.primary_source == r001.references[0]


def test_rule_reference_requires_https_url() -> None:
    with pytest.raises(RulesetLoadError):
        load_fixture_ruleset_with_reference("http://insecure.example.com/rule")


# --------------------------------------------------------------------------
# A.11: malformed rulesets fail clearly
# --------------------------------------------------------------------------

def load_fixture_ruleset_with_reference(url: str) -> None:
    """Shared helper: build a ruleset JSON with a custom reference URL."""
    from eligibility.loader import load_ruleset

    path = _write_temp_ruleset({"rule_id": "X", "url": url})
    load_ruleset(path)


def _write_temp_ruleset(overrides: dict) -> Path:
    payload = {
        "ruleset_id": "fixture-malformed",
        "version": "1.0.0",
        "schema_version": "1.0",
        "status": "test",
        "decisive": False,
        "description": "Malformed fixture.",
        "provenance": {"sources": []},
        "evidence_gaps": [],
        "rules": [
            {
                "rule_id": "R-001",
                "name": "Test rule",
                "type": "diploma_pathway",
                "required_inputs": ["diploma"],
                "decisive": False,
                "description": "Test rule.",
                "references": [
                    {
                        "title": "A reference",
                        "url": overrides.get("url", "https://daffodilvarsity.edu.bd/source"),
                    }
                ],
            }
        ],
    }
    if "rule_id" in overrides:
        payload["rules"][0]["rule_id"] = overrides["rule_id"]
    path = Path("/tmp") / "fixture-malformed-ruleset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_malformed_ruleset_missing_ruleset_id() -> None:
    payload = {
        "version": "1.0.0",
        "schema_version": "1.0",
        "status": "test",
        "decisive": False,
        "description": "Missing ruleset_id.",
        "provenance": {"sources": []},
        "evidence_gaps": [],
        "rules": [],
    }
    path = Path("/tmp") / "fixture-missing-id.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    from eligibility.loader import load_ruleset

    with pytest.raises(RulesetLoadError):
        load_ruleset(path)


def test_malformed_ruleset_bad_json() -> None:
    path = Path("/tmp") / "fixture-bad-json.json"
    path.write_text("{not valid json", encoding="utf-8")
    from eligibility.loader import load_ruleset

    with pytest.raises(RulesetLoadError):
        load_ruleset(path)


def test_malformed_ruleset_unsupported_rule_type() -> None:
    payload = {
        "ruleset_id": "fixture",
        "version": "1.0.0",
        "schema_version": "1.0",
        "status": "test",
        "decisive": False,
        "description": "Unsupported rule type.",
        "provenance": {"sources": []},
        "evidence_gaps": [],
        "rules": [
            {
                "rule_id": "R-001",
                "name": "Unknown type",
                "type": "mystery_rule",
                "required_inputs": [],
                "decisive": False,
                "description": "Nope.",
                "references": [],
            }
        ],
    }
    path = Path("/tmp") / "fixture-bad-type.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    from eligibility.loader import load_ruleset

    with pytest.raises(RulesetLoadError):
        load_ruleset(path)


def test_malformed_ruleset_duplicate_rule_ids() -> None:
    payload = {
        "ruleset_id": "fixture",
        "version": "1.0.0",
        "schema_version": "1.0",
        "status": "test",
        "decisive": False,
        "description": "Duplicate rule ids.",
        "provenance": {"sources": []},
        "evidence_gaps": [],
        "rules": [
            {
                "rule_id": "R-001",
                "name": "First",
                "type": "diploma_pathway",
                "required_inputs": ["diploma"],
                "decisive": False,
                "description": "First.",
                "references": [],
            },
            {
                "rule_id": "R-001",
                "name": "Second",
                "type": "diploma_pathway",
                "required_inputs": ["diploma"],
                "decisive": False,
                "description": "Second.",
                "references": [],
            },
        ],
    }
    path = Path("/tmp") / "fixture-duplicate-rule.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    from eligibility.loader import load_ruleset

    with pytest.raises(RulesetLoadError):
        load_ruleset(path)


def test_malformed_program_registry() -> None:
    payload = {
        "registry_id": "programs",
        "version": "1.0.0",
        "schema_version": "1.0",
        "status": "test",
        "description": "Duplicate program ids.",
        "provenance": {"sources": []},
        "evidence_gaps": [],
        "programs": [
            {
                "id": "cse",
                "name": "CSE",
                "tags": ["CSE"],
                "references": [],
            },
            {
                "id": "cse",
                "name": "CSE dup",
                "tags": ["CSE"],
                "references": [],
            },
        ],
    }
    path = Path("/tmp") / "fixture-bad-programs.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    from eligibility.loader import load_programs

    with pytest.raises(RulesetLoadError):
        load_programs(path)


# --------------------------------------------------------------------------
# A.12: content hash / provenance
# --------------------------------------------------------------------------

def test_ruleset_content_hash_is_stable_sha256() -> None:
    ruleset = load_default_ruleset()
    assert len(ruleset.content_hash) == 64
    int(ruleset.content_hash, 16)  # raises if not hex
    again = load_default_ruleset()
    assert ruleset.content_hash == again.content_hash


def test_content_hash_changes_when_rules_change() -> None:
    one = _fixture_ruleset(_fixture_rule(minimum=3.0))
    two = _fixture_ruleset(_fixture_rule(minimum=3.5))
    assert one.content_hash != two.content_hash


def test_provenance_and_evidence_gaps_are_preserved() -> None:
    ruleset = load_default_ruleset()
    assert ruleset.provenance
    assert ruleset.provenance.get("sources")
    assert ruleset.evidence_gaps
    first = ruleset.provenance["sources"][0]
    assert first["url"].startswith("https://")
    assert first["source_id"]
    assert first["document_id"]
    assert first["retrieved_at"]
