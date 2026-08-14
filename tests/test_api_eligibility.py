"""API tests for POST /api/eligibility.

Mirrors the TestClient + dependency-override patterns in test_api_programs.py.
Eligible/not_eligible are exercised via an injected decisive fixture service so
the API wiring is covered without relying on the intentionally non-decisive v1
ruleset.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from backend.api.eligibility import get_eligibility_service
from backend.main import app
from backend.services.eligibility_service import EligibilityService
from eligibility.engine import EligibilityEngine
from eligibility.models import (
    ProgramRecord,
    ProgramRegistry,
    Rule,
    RuleReference,
    Ruleset,
)

client = TestClient(app)


# --------------------------------------------------------------------------
# Fixture: decisive service (engine with a numeric_range rule)
# --------------------------------------------------------------------------

def _reference(title: str) -> RuleReference:
    return RuleReference(
        title=title,
        url="https://daffodilvarsity.edu.bd/programs",
        source_id="DIU-PROG-001",
        document_id="diu-prog-001-fixture",
    )


def _decisive_service(rule_type: str = "min_gpa") -> EligibilityService:
    if rule_type == "min_gpa":
        rule = Rule(
            rule_id="F-GPA",
            name="Minimum GPA",
            type="numeric_range",
            required_inputs=("ssc_gpa",),
            decisive=True,
            description="Fixture.",
            references=(_reference("Programs"),),
            params={"field": "ssc_gpa", "min": 3.0},
        )
    else:
        rule = Rule(
            rule_id="F-DIPLOMA",
            name="Diploma required",
            type="diploma_pathway",
            required_inputs=("diploma",),
            decisive=True,
            description="Fixture.",
            references=(_reference("Programs"),),
            params={},
        )
    ruleset = Ruleset(
        ruleset_id="fixture-decisive",
        version="1.0.0",
        schema_version="1.0",
        status="test",
        decisive=True,
        description="Fixture.",
        provenance={"sources": []},
        evidence_gaps=(),
        rules=(rule,),
        content_hash=hashlib.sha256(b"fixture").hexdigest(),
    )
    record = ProgramRecord(
        id="cse",
        name="B.Sc. in CSE",
        tags=("CSE",),
        degree="B.Sc.",
        references=(_reference("Programs"),),
    )
    registry = ProgramRegistry(
        registry_id="programs-fixture",
        version="1.0.0",
        schema_version="1.0",
        status="test",
        description="Fixture.",
        provenance={"sources": []},
        evidence_gaps=(),
        programs=(record,),
        content_hash=hashlib.sha256(b"fixture-registry").hexdigest(),
    )
    engine = EligibilityEngine(ruleset, registry=registry)
    return EligibilityService(engine=engine)


# --------------------------------------------------------------------------
# Helper to swap in the fixture service for the duration of a test.
# --------------------------------------------------------------------------

@pytest.fixture()
def with_decisive_service():
    app.dependency_overrides[get_eligibility_service] = lambda: _decisive_service()
    yield
    app.dependency_overrides.pop(get_eligibility_service, None)


@pytest.fixture()
def with_diploma_service():
    app.dependency_overrides[get_eligibility_service] = lambda: _decisive_service(
        rule_type="diploma"
    )
    yield
    app.dependency_overrides.pop(get_eligibility_service, None)


# --------------------------------------------------------------------------
# A.1: valid request -> eligible
# --------------------------------------------------------------------------

def test_valid_request_returns_eligible(with_decisive_service) -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "ssc_gpa": 4.0, "hsc_gpa": 4.0, "group": "Science", "diploma": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "eligible"
    assert body["reason"]
    assert body["source"] is not None
    assert body["source"]["url"] == "https://daffodilvarsity.edu.bd/programs"


# --------------------------------------------------------------------------
# A.2: insufficient-information response (v1 rules, real service)
# --------------------------------------------------------------------------

def test_v1_rules_return_insufficient_information() -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "ssc_gpa": 5.0, "hsc_gpa": 5.0, "group": "Science", "diploma": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "insufficient_information"
    assert body["reason"]
    assert body["source"] is not None
    assert body["evidence_gaps"]
    assert len(body["rule_matches"]) == 2
    ids = {m["rule_id"] for m in body["rule_matches"]}
    assert ids == {"R-001", "R-002"}


# --------------------------------------------------------------------------
# A.3: unknown program
# --------------------------------------------------------------------------

def test_unknown_program_returns_insufficient_information() -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "NoSuchProgram", "diploma": False},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "insufficient_information"


# --------------------------------------------------------------------------
# A.4: diploma applicant
# --------------------------------------------------------------------------

def test_diploma_applicant_is_accepted(with_diploma_service) -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "diploma": True},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "eligible"


# --------------------------------------------------------------------------
# A.5: missing required fields -> 422
# --------------------------------------------------------------------------

def test_missing_required_fields_returns_422() -> None:
    resp = client.post("/api/eligibility", json={"program": "CSE"})
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# A.6: invalid GPA -> 422
# --------------------------------------------------------------------------

def test_invalid_gpa_out_of_range_returns_422() -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "ssc_gpa": 6.5, "hsc_gpa": 4.0, "diploma": False},
    )
    assert resp.status_code == 422


def test_negative_gpa_returns_422() -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "ssc_gpa": -1.0, "diploma": False},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# A.7: blank program -> 422
# --------------------------------------------------------------------------

def test_blank_program_returns_422() -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "   ", "diploma": False},
    )
    assert resp.status_code == 422


def test_blank_group_returns_422() -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "group": " ", "diploma": False},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# A.8: source references
# --------------------------------------------------------------------------

def test_source_reference_is_cited() -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "diploma": False},
    )
    body = resp.json()
    assert body["source"] is not None
    assert body["source"]["title"]
    assert body["source"]["url"].startswith("https://")


# --------------------------------------------------------------------------
# A.9: error shape (OpenAPI not-found / validation envelope)
# --------------------------------------------------------------------------

def test_validation_error_uses_error_envelope() -> None:
    resp = client.post("/api/eligibility", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body


def test_missing_field_error_envelope() -> None:
    resp = client.post("/api/eligibility", json={"program": "CSE", "ssc_gpa": 4.0})
    assert resp.status_code == 422
    assert "error" in resp.json()


# --------------------------------------------------------------------------
# A.10: dependency override compatibility
# --------------------------------------------------------------------------

def test_dependency_override_is_respected(with_decisive_service) -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "ssc_gpa": 2.0, "diploma": False},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_eligible"


def test_fixture_service_confirms_eligible_threshold(with_decisive_service) -> None:
    resp = client.post(
        "/api/eligibility",
        json={"program": "CSE", "ssc_gpa": 3.5, "diploma": False},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "eligible"