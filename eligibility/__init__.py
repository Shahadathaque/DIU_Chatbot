"""Deterministic DIU eligibility rule engine.

This package contains the pure, data-driven eligibility evaluator plus the
versioned rule data loaders. It has no LLM, HTTP, database, or network
dependency so eligibility decisions remain fully deterministic and auditable.
"""

from eligibility.engine import EligibilityEngine
from eligibility.loader import (
    DEFAULT_PROGRAMS_PATH,
    DEFAULT_RULESET_PATH,
    RulesetLoadError,
    load_default_programs,
    load_default_ruleset,
    load_programs,
    load_ruleset,
)
from eligibility.models import (
    Decision,
    EligibilityInput,
    EligibilityResult,
    ProgramRecord,
    ProgramRegistry,
    Rule,
    RuleMatch,
    RuleReference,
    RuleStatus,
    Ruleset,
)

__all__ = [
    "DEFAULT_PROGRAMS_PATH",
    "DEFAULT_RULESET_PATH",
    "Decision",
    "EligibilityEngine",
    "EligibilityInput",
    "EligibilityResult",
    "ProgramRecord",
    "ProgramRegistry",
    "Rule",
    "RuleMatch",
    "RuleReference",
    "RuleStatus",
    "Ruleset",
    "RulesetLoadError",
    "load_default_programs",
    "load_default_ruleset",
    "load_programs",
    "load_ruleset",
]
