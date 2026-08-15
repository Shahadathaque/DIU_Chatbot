"""Tests for the M5-B eligibility evaluation (real + synthetic tiers).

The real tier must report `insufficient_information` for every real profile
(the v1 ruleset is non-decisive). The synthetic tier reproduces the dataset's
expected outcomes except the one documented annotation inconsistency
(elig-syn-09), which is asserted explicitly rather than silently "fixed".
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

from eligibility.engine import EligibilityEngine
from eligibility.loader import load_default_programs, load_default_ruleset
from eligibility.models import EligibilityInput
from evaluation.eligibility_eval import (
    _eligibility_input,
    _synthetic_registry,
    _synthetic_ruleset,
    run_eligibility_eval,
)
from evaluation.schema import (
    DEFAULT_DATASET_PATH,
    DEFAULT_KB_PATH,
    DEFAULT_MANIFEST_PATH,
    load_eval_dataset,
)

# The one synthetic fixture whose machine-readable `fixture_rule` + input do
# not encode the second numeric rule its question text describes.
DOCUMENTED_MISMATCH_ID = "elig-syn-09"


@pytest.fixture(scope="module")
def dataset():
    return load_eval_dataset(DEFAULT_DATASET_PATH, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)


class TestRealTier:
    def test_all_real_profiles_are_insufficient_information(self, dataset):
        ruleset = load_default_ruleset()
        registry = load_default_programs()
        engine = EligibilityEngine(ruleset, registry=registry)
        real = [q for q in dataset.questions if q.is_eligibility_real]
        assert len(real) == 10
        for question in real:
            result = engine.evaluate(_eligibility_input(question.eligibility_input))
            assert result.decision.value == "insufficient_information", question.id
            assert result.decision.value == question.expected_outcome, question.id

    def test_non_decisive_ruleset_confirmed(self, dataset):
        ruleset = load_default_ruleset()
        assert ruleset.decisive is False


class TestSyntheticBuilder:
    def test_registry_find(self):
        registry = _synthetic_registry(["cse", "swe"])
        assert registry.find("cse") is not None
        assert registry.find("CSE") is not None
        assert registry.find("xyz") is None

    def test_numeric_rule_pass_is_eligible(self, dataset):
        question = dataset.by_id["elig-syn-01"]
        ruleset, registry = _synthetic_ruleset(question)
        engine = EligibilityEngine(ruleset, registry=registry)
        result = engine.evaluate(_eligibility_input(question.eligibility_input))
        assert result.decision.value == "eligible"

    def test_numeric_rule_fail_is_not_eligible(self, dataset):
        question = dataset.by_id["elig-syn-02"]
        ruleset, registry = _synthetic_ruleset(question)
        engine = EligibilityEngine(ruleset, registry=registry)
        result = engine.evaluate(_eligibility_input(question.eligibility_input))
        assert result.decision.value == "not_eligible"

    def test_program_registry_fixture(self, dataset):
        question = dataset.by_id["elig-syn-04"]
        ruleset, registry = _synthetic_ruleset(question)
        assert registry is not None
        engine = EligibilityEngine(ruleset, registry=registry)
        result = engine.evaluate(_eligibility_input(question.eligibility_input))
        assert result.decision.value == "eligible"

    def test_diploma_pathway_fixture(self, dataset):
        question = dataset.by_id["elig-syn-06"]
        ruleset, registry = _synthetic_ruleset(question)
        engine = EligibilityEngine(ruleset, registry=registry)
        result = engine.evaluate(_eligibility_input(question.eligibility_input))
        assert result.decision.value == "eligible"

    def test_multi_rule_fixture_detects_hsc_failure(self, dataset):
        question = dataset.by_id["elig-syn-08"]
        ruleset, _registry = _synthetic_ruleset(question)
        assert [rule.rule_id for rule in ruleset.rules] == ["F-001", "F-002"]
        engine = EligibilityEngine(ruleset)
        result = engine.evaluate(_eligibility_input(question.eligibility_input))
        assert result.decision.value == "not_eligible"

    def test_all_expected_outcomes_except_documented_mismatch(self, dataset):
        synthetic = [q for q in dataset.questions if q.is_eligibility_synthetic]
        assert len(synthetic) == 10
        for question in synthetic:
            ruleset, registry = _synthetic_ruleset(question)
            engine = EligibilityEngine(ruleset, registry=registry)
            actual = engine.evaluate(
                _eligibility_input(question.eligibility_input)
            ).decision.value
            if question.id == DOCUMENTED_MISMATCH_ID:
                assert actual == "eligible", (
                    f"{question.id}: dataset fixture_rule+input cannot express the "
                    "second numeric rule its question text describes, so the builder "
                    "produces 'eligible'; reported honestly, not silently fixed."
                )
            else:
                assert actual == question.expected_outcome, question.id


class TestRunEligibilityEval:
    def test_writes_json_and_tier_counts(self, dataset, tmp_path):
        payload = run_eligibility_eval(dataset, results_dir=tmp_path)
        assert payload["eligibility_real"]["count"] == 10
        assert payload["eligibility_real"]["exact_match_count"] == 10
        assert payload["eligibility_real"]["expected_insufficient_information_count"] == 10
        assert payload["eligibility_synthetic"]["count"] == 10
        assert payload["eligibility_synthetic"]["exact_match_count"] == 9
        assert (Path(tmp_path) / "eligibility.json").is_file()
