"""Tests for the programs endpoint (GET /api/programs)."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from backend.api.programs import get_programs_service
from backend.main import app
from backend.services.programs_service import ProgramsService
from tests.rag_helpers import cleaned_record


def _client(service: ProgramsService) -> TestClient:
    app.dependency_overrides[get_programs_service] = lambda: service
    return TestClient(app)


def _reset_overrides() -> None:
    app.dependency_overrides.pop(get_programs_service, None)


def _programs_record() -> dict:
    return cleaned_record(
        source_id="DIU-PROG-001",
        document_id="diu-prog-001",
        category="undergraduate_programs",
        title="Programs",
        content="Undergraduate Program list.",
        tables=[
            {
                "headers": ["Full Program Name", "Short Tag / Initials"],
                "rows": [
                    ["B. Sc. in Computer Science and Engineering", "CSE"],
                    ["B. Sc. in Software Engineering (SWE)", "SWE"],
                ],
                "extraction_method": "beautifulsoup_dom_cleaning",
                "extraction_quality": "reliable",
            }
        ],
    )


def test_programs_returns_derived_programs() -> None:
    service = ProgramsService(records=[_programs_record()])
    client = _client(service)

    response = client.get("/api/programs")

    assert response.status_code == 200
    programs = response.json()["programs"]
    assert len(programs) == 2
    cse = next(item for item in programs if item["name"].casefold().startswith("b. sc."))
    assert cse["id"] == "cse"
    assert cse["degree"] == "B.Sc."
    _reset_overrides()


def test_programs_include_program_specific_record() -> None:
    bba = cleaned_record(
        source_id="DIU-PROG-002",
        document_id="diu-prog-002",
        category="program_specific_admission",
        program="BBA",
        faculty="Faculty of Business and Entrepreneurship",
        title="Admission Page",
    )
    service = ProgramsService(records=[_programs_record(), bba])
    client = _client(service)

    response = client.get("/api/programs")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["programs"]]
    assert "BBA" in names
    bba_item = next(item for item in response.json()["programs"] if item["name"] == "BBA")
    assert bba_item["faculty"] == "Faculty of Business and Entrepreneurship"
    assert bba_item["admission_url"] == "https://daffodilvarsity.edu.bd/admission/diu-prog-002"
    _reset_overrides()


def test_programs_empty_records_returns_empty_list() -> None:
    service = ProgramsService(records=[])
    client = _client(service)

    response = client.get("/api/programs")

    assert response.status_code == 200
    assert response.json() == {"programs": []}
    _reset_overrides()


def test_programs_database_backend_does_not_load_local_files(monkeypatch) -> None:
    class FakeRepository:
        def list_programs(self):
            return [
                {
                    "id": "cse",
                    "name": "B. Sc. in Computer Science and Engineering",
                    "degree": "B.Sc.",
                    "faculty": "Science and Information Technology",
                    "admission_url": "https://daffodilvarsity.edu.bd/programs",
                }
            ]

    service = ProgramsService(repository=FakeRepository())
    monkeypatch.setattr(
        service,
        "_load_records",
        lambda: (_ for _ in ()).throw(AssertionError("local files must not load")),
    )

    response = service.list_programs()

    assert [program.id for program in response.programs] == ["cse"]


def test_missing_cleaned_dataset_returns_recovery_error(tmp_path) -> None:
    service = ProgramsService(cleaned_root=str(tmp_path / "missing-cleaned"))
    client = _client(service)

    response = client.get("/api/programs")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "artifact_unavailable"
    assert "cleaned" in response.json()["error"]["message"]
    _reset_overrides()


def test_programs_deduplicates_by_name() -> None:
    a = _programs_record()
    b = _programs_record()
    service = ProgramsService(records=[a, b])
    client = _client(service)

    response = client.get("/api/programs")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["programs"]]
    assert len(names) == len(set(names))
    _reset_overrides()


def test_programs_merge_unambiguous_short_name_record_into_catalog_program() -> None:
    bba = cleaned_record(
        source_id="DIU-PROG-002",
        document_id="diu-prog-002",
        category="program_specific_admission",
        program="BBA",
        title="BBA Admission",
    )
    service = ProgramsService(records=[_official_catalog_record(), bba])

    programs = service.list_programs().programs

    assert not any(program.name == "BBA" for program in programs)
    full_bba = next(
        program
        for program in programs
        if program.name == "Bachelor of Business Administration (BBA)"
    )
    assert full_bba.id == "bba"
    assert full_bba.admission_url == (
        "https://daffodilvarsity.edu.bd/department/bba/program/"
        "bachelor-of-business-administration"
    )


def _swe_family_record() -> dict:
    return cleaned_record(
        source_id="DIU-PROG-001",
        document_id="diu-prog-001",
        category="undergraduate_programs",
        title="Programs",
        content="Undergraduate Program list.",
        tables=[
            {
                "headers": ["Full Program Name", "Short Tag / Initials"],
                "rows": [
                    ["B. Sc. in Software Engineering (SWE)", "SWE"],
                    ["B. Sc. in Software Engineering (Major in Cyber Security)", "SWE"],
                    ["B. Sc. in Software Engineering (Major in Robotics)", "SWE"],
                ],
                "extraction_method": "beautifulsoup_dom_cleaning",
                "extraction_quality": "reliable",
            }
        ],
    )


def test_programs_ids_are_unique_across_shared_tags() -> None:
    service = ProgramsService(records=[_swe_family_record()])
    client = _client(service)

    response = client.get("/api/programs")

    assert response.status_code == 200
    programs = response.json()["programs"]
    ids = [item["id"] for item in programs]
    assert len(programs) == 3
    assert len(ids) == len(set(ids))
    swe = next(item for item in programs if item["name"].startswith("B. Sc. in Software Engineering (SWE)"))
    assert swe["id"] == "swe"
    assert any(item["id"].startswith("swe-") for item in programs)
    _reset_overrides()


def test_programs_ids_stable_across_repeated_calls() -> None:
    first = ProgramsService(records=[_swe_family_record()]).list_programs()
    second = ProgramsService(records=[_swe_family_record()]).list_programs()

    first_ids = [(p.id, p.name) for p in first.programs]
    second_ids = [(p.id, p.name) for p in second.programs]
    assert first_ids == second_ids
    assert len({p.id for p in first.programs}) == len(first.programs)


def _official_catalog_record() -> dict:
    return cleaned_record(
        source_id="DIU-PROG-001",
        document_id="diu-prog-001",
        category="undergraduate_programs",
        title="Programs",
        content="Official program catalog.",
        tables=[
            {
                "headers": [
                    "Full Program Name",
                    "Short Tag / Initials",
                    "Program Level",
                    "Faculty",
                    "Department",
                    "Duration",
                    "Program Page",
                ],
                "rows": [
                    ["B. Sc. in Computer Science and Engineering", "CSE", "Undergraduate", "Science and Information Technology", "Computer Science and Engineering", "4 Years", "https://daffodilvarsity.edu.bd/department/cse/program/bse-in-cse"],
                    ["Bachelor of Business Administration (BBA)", "BBA", "Undergraduate", "Business & Entrepreneurship", "Business Administration", "4 Years", "https://daffodilvarsity.edu.bd/department/bba/program/bachelor-of-business-administration"],
                    ["LL.B. (Hons.)", "LAW", "Undergraduate", "Humanities & Social Sciences", "Law", "4 Years", "https://daffodilvarsity.edu.bd/department/law/program/bachelor-of-law"],
                    ["Bachelor of Pharmacy (B. Pharm)", "PHARMACY", "Undergraduate", "Health and Life Sciences", "Pharmacy", "4 Years", "https://daffodilvarsity.edu.bd/department/pharmacy/program/bachelor-of-pharmacy"],
                    ["B.Sc. in Textile Engineering (TE)", "TE", "Undergraduate", "Engineering", "Textile Engineering", "4 Years", "https://daffodilvarsity.edu.bd/department/te/program/bsc-in-te"],
                    ["M. Sc. in Computer Science and Engineering (CSE)", "CSE", "Postgraduate", "Science and Information Technology", "Computer Science and Engineering", "1.5 Years", "https://daffodilvarsity.edu.bd/department/cse/program/msc-in-cse"],
                ],
                "extraction_method": "official_programs_api",
                "extraction_quality": "reliable",
            }
        ],
    )


def test_official_catalog_includes_non_sit_programs_with_faculty() -> None:
    service = ProgramsService(records=[_official_catalog_record()])
    client = _client(service)

    response = client.get("/api/programs")

    assert response.status_code == 200
    programs = response.json()["programs"]
    by_name = {item["name"]: item for item in programs}
    assert "Bachelor of Business Administration (BBA)" in by_name
    assert "LL.B. (Hons.)" in by_name
    assert "Bachelor of Pharmacy (B. Pharm)" in by_name
    assert by_name["Bachelor of Business Administration (BBA)"]["faculty"] == (
        "Business & Entrepreneurship"
    )
    assert by_name["Bachelor of Business Administration (BBA)"]["admission_url"] == (
        "https://daffodilvarsity.edu.bd/department/bba/program/"
        "bachelor-of-business-administration"
    )
    assert by_name["LL.B. (Hons.)"]["faculty"] == "Humanities & Social Sciences"
    assert by_name["Bachelor of Pharmacy (B. Pharm)"]["degree"] == "B.Pharm"
    assert by_name["LL.B. (Hons.)"]["degree"] == "LL.B."
    ids = [item["id"] for item in programs]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    _reset_overrides()


@pytest.mark.integration
def test_real_cleaned_data_has_unique_and_stable_ids() -> None:
    first = ProgramsService().list_programs()
    second = ProgramsService().list_programs()

    assert first.programs, "expected real cleaned programs"
    ids = [p.id for p in first.programs]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    assert [(p.id, p.name) for p in first.programs] == [
        (p.id, p.name) for p in second.programs
    ]
    names = {p.name.casefold() for p in first.programs}
    assert "bba" not in names
    assert "bachelor of business administration (bba)" in names
    assert any("software engineering" in name for name in names)
