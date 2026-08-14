"""Load and validate the versioned DIU eligibility ruleset and program registry.

The loader never silently repairs invalid rules. Any structural problem raises
``RulesetLoadError`` with a clear message. A canonical JSON content hash is
computed from the exact file content for provenance, so any later rule change
is detectable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from eligibility.models import (
    ProgramRecord,
    ProgramRegistry,
    Rule,
    RuleReference,
    Ruleset,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULESET_PATH = _PROJECT_ROOT / "rules" / "eligibility_rules.v1.json"
DEFAULT_PROGRAMS_PATH = _PROJECT_ROOT / "rules" / "programs.v1.json"

_SUPPORTED_RULE_TYPES = frozenset(
    {"program_registry", "diploma_pathway", "numeric_range"}
)


class RulesetLoadError(ValueError):
    """Raised when a ruleset or program registry is malformed or invalid."""


def _sha256_canonical(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _read_json_file(path: Path, *, label: str) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RulesetLoadError(f"{label}: cannot read file {path}: {error}") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RulesetLoadError(f"{label}: malformed JSON in {path}: {error}") from error
    if not isinstance(payload, dict):
        raise RulesetLoadError(f"{label}: {path} must contain a JSON object")
    return payload


def _required_string(payload: Mapping[str, Any], key: str, *, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RulesetLoadError(f"{label}: {key!r} must be a non-empty string")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], key: str) -> Any:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RulesetLoadError(f"{key!r} must be a string or null")
    return value.strip() or None


def _required_bool(payload: Mapping[str, Any], key: str, *, label: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise RulesetLoadError(f"{label}: {key!r} must be a boolean")
    return value


def _required_string_list(payload: Mapping[str, Any], key: str, *, label: str) -> Sequence[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise RulesetLoadError(f"{label}: {key!r} must be a list of non-empty strings")
    return value


def _required_object(payload: Mapping[str, Any], key: str, *, label: str) -> Dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RulesetLoadError(f"{label}: {key!r} must be an object")
    return value


def _required_list(payload: Mapping[str, Any], key: str, *, label: str) -> Sequence[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise RulesetLoadError(f"{label}: {key!r} must be a list")
    return value


def _reference(payload: Mapping[str, Any], *, label: str) -> RuleReference:
    title = _required_string(payload, "title", label=label)
    url = _required_string(payload, "url", label=label)
    if not url.startswith("https://"):
        raise RulesetLoadError(f"{label}: url must be an absolute https URL")
    return RuleReference(
        title=title,
        url=url,
        source_id=_optional_string(payload, "source_id"),
        document_id=_optional_string(payload, "document_id"),
    )


def _references(payload: Mapping[str, Any], *, label: str) -> tuple[RuleReference, ...]:
    raw = _required_list(payload, "references", label=label)
    return tuple(
        _reference(item, label=f"{label} reference {index}")
        for index, item in enumerate(raw, start=1)
    )


def _provenance(payload: Mapping[str, Any], *, label: str) -> Dict[str, Any]:
    provenance = _required_object(payload, "provenance", label=label)
    sources = provenance.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            raise RulesetLoadError(f"{label}: provenance.sources must be a list")
        for index, source in enumerate(sources, start=1):
            _required_string(source, "title", label=f"{label} provenance source {index}")
            _required_string(source, "url", label=f"{label} provenance source {index}")
            _optional_string(source, "source_id")
            _optional_string(source, "document_id")
    return dict(provenance)


def _evidence_gaps(payload: Mapping[str, Any], *, label: str) -> tuple[str, ...]:
    return tuple(_required_string_list(payload, "evidence_gaps", label=label))


def load_ruleset(path: Path | str) -> Ruleset:
    """Load and validate ``rules/eligibility_rules.v1.json``."""
    path_obj = Path(path)
    label = f"ruleset {path_obj.name}"
    payload = _read_json_file(path_obj, label=label)
    return _ruleset_from_payload(payload, content_hash=_sha256_canonical(payload), label=label)


def load_programs(path: Path | str) -> ProgramRegistry:
    """Load and validate ``rules/programs.v1.json``."""
    path_obj = Path(path)
    label = f"program registry {path_obj.name}"
    payload = _read_json_file(path_obj, label=label)
    return _programs_from_payload(payload, content_hash=_sha256_canonical(payload), label=label)


def load_default_ruleset() -> Ruleset:
    """Load the default project ruleset, failing clearly if missing/broken."""
    return load_ruleset(DEFAULT_RULESET_PATH)


def load_default_programs() -> ProgramRegistry:
    """Load the default project program registry, failing clearly if missing/broken."""
    return load_programs(DEFAULT_PROGRAMS_PATH)


def _ruleset_from_payload(
    payload: Mapping[str, Any], *, content_hash: str, label: str
) -> Ruleset:
    ruleset_id = _required_string(payload, "ruleset_id", label=label)
    version = _required_string(payload, "version", label=label)
    schema_version = _required_string(payload, "schema_version", label=label)
    status = _required_string(payload, "status", label=label)
    decisive = _required_bool(payload, "decisive", label=label)
    description = _required_string(payload, "description", label=label)
    provenance = _provenance(payload, label=label)
    evidence_gaps = _evidence_gaps(payload, label=label)

    raw_rules = _required_list(payload, "rules", label=label)
    if not raw_rules:
        raise RulesetLoadError(f"{label}: rules must not be empty")
    rules = tuple(
        _rule(item, index=index, label=label) for index, item in enumerate(raw_rules, start=1)
    )

    rule_ids = [rule.rule_id for rule in rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise RulesetLoadError(f"{label}: rule_ids must be unique")

    return Ruleset(
        ruleset_id=ruleset_id,
        version=version,
        schema_version=schema_version,
        status=status,
        decisive=decisive,
        description=description,
        provenance=provenance,
        evidence_gaps=evidence_gaps,
        rules=rules,
        content_hash=content_hash,
    )


def _rule(payload: Any, *, index: int, label: str) -> Rule:
    if not isinstance(payload, dict):
        raise RulesetLoadError(f"{label}: rule {index} must be an object")
    rule_label = f"{label} rule {index}"
    rule_id = _required_string(payload, "rule_id", label=rule_label)
    name = _required_string(payload, "name", label=rule_label)
    rule_type = _required_string(payload, "type", label=rule_label)
    if rule_type not in _SUPPORTED_RULE_TYPES:
        raise RulesetLoadError(
            f"{rule_label}: unsupported rule type {rule_type!r}; "
            f"supported: {', '.join(sorted(_SUPPORTED_RULE_TYPES))}"
        )
    description = _required_string(payload, "description", label=rule_label)
    decisive = _required_bool(payload, "decisive", label=rule_label)
    required_inputs = tuple(_required_string_list(payload, "required_inputs", label=rule_label))
    references = _references(payload, label=rule_label)

    params = payload.get("params")
    if params is not None and not isinstance(params, dict):
        raise RulesetLoadError(f"{rule_label}: params must be an object or absent")
    normalized_params = dict(params) if params else {}
    _validate_rule_params(rule_type, normalized_params, label=rule_label)

    return Rule(
        rule_id=rule_id,
        name=name,
        type=rule_type,
        required_inputs=required_inputs,
        decisive=decisive,
        description=description,
        references=references,
        params=normalized_params,
    )


def _validate_rule_params(rule_type: str, params: Dict[str, Any], *, label: str) -> None:
    """Validate type-specific params so malformed rules fail at load time."""
    if rule_type == "numeric_range":
        field = params.get("field")
        if not isinstance(field, str) or not field.strip():
            raise RulesetLoadError(f"{label}: numeric_range params must define a 'field'")
        has_bound = False
        for key in ("min", "max"):
            value = params.get(key)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise RulesetLoadError(f"{label}: numeric_range param {key!r} must be a number")
            has_bound = True
        if not has_bound:
            raise RulesetLoadError(f"{label}: numeric_range params require a 'min' or 'max'")


def _programs_from_payload(
    payload: Mapping[str, Any], *, content_hash: str, label: str
) -> ProgramRegistry:
    registry_id = _required_string(payload, "registry_id", label=label)
    version = _required_string(payload, "version", label=label)
    schema_version = _required_string(payload, "schema_version", label=label)
    status = _required_string(payload, "status", label=label)
    description = _required_string(payload, "description", label=label)
    provenance = _provenance(payload, label=label)
    evidence_gaps = _evidence_gaps(payload, label=label)

    raw_programs = _required_list(payload, "programs", label=label)
    if not raw_programs:
        raise RulesetLoadError(f"{label}: programs must not be empty")
    programs = tuple(
        _program(item, index=index, label=label) for index, item in enumerate(raw_programs, start=1)
    )

    program_ids = [program.id for program in programs]
    if len(set(program_ids)) != len(program_ids):
        raise RulesetLoadError(f"{label}: program ids must be unique")

    return ProgramRegistry(
        registry_id=registry_id,
        version=version,
        schema_version=schema_version,
        status=status,
        description=description,
        provenance=provenance,
        evidence_gaps=evidence_gaps,
        programs=programs,
        content_hash=content_hash,
    )


def _program(payload: Any, *, index: int, label: str) -> ProgramRecord:
    if not isinstance(payload, dict):
        raise RulesetLoadError(f"{label}: program {index} must be an object")
    program_label = f"{label} program {index}"
    program_id = _required_string(payload, "id", label=program_label)
    name = _required_string(payload, "name", label=program_label)
    tags = tuple(_required_string_list(payload, "tags", label=program_label))
    references = _references(payload, label=program_label)
    return ProgramRecord(
        id=program_id,
        name=name,
        tags=tags,
        degree=_optional_string(payload, "degree"),
        faculty=_optional_string(payload, "faculty"),
        references=references,
    )


__all__ = [
    "DEFAULT_PROGRAMS_PATH",
    "DEFAULT_RULESET_PATH",
    "RulesetLoadError",
    "load_default_programs",
    "load_default_ruleset",
    "load_programs",
    "load_ruleset",
]
