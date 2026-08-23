"""Tests for generated chat responses (POST /api/chat) with a FakeGenerator."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from fastapi.testclient import TestClient

from backend.api.chat import get_chat_service
from backend.main import app
from backend.services.chat_service import ChatService, build_grounded_messages
from rag.generator import GeneratorUnavailableError
from tests.rag_helpers import knowledge_chunk


class _FakeRetriever:
    """Retriever-shaped fake returning configured results per query."""

    def __init__(self, results_by_query: Optional[dict] = None) -> None:
        self._results_by_query = results_by_query or {}
        self.calls: List[str] = []
        self.top_ks: List[int] = []

    def retrieve(self, query: str, top_k: int = 5) -> List:
        self.calls.append(query)
        self.top_ks.append(top_k)
        return self._results_by_query.get(query, [])


class _FakeGenerator:
    def __init__(self, answer: str = "Grounded generated answer.") -> None:
        self.answer = answer
        self.calls: List[List[Dict[str, str]]] = []

    @property
    def model_name(self) -> str:
        return "fake-generator"

    @property
    def model_revision(self) -> None:
        return None

    def generate(self, messages, **kwargs) -> str:
        self.calls.append(list(messages))
        return self.answer


class _BrokenGenerator:
    def generate(self, messages, **kwargs) -> str:
        raise GeneratorUnavailableError("boom")


class _Result:
    def __init__(self, chunk, relevance: float) -> None:
        self.chunk = chunk
        self.similarity_score = relevance
        self.relevance_score = relevance


def _evidence_result(chunk_id: str, *, content: str, relevance: float) -> _Result:
    return _Result(
        knowledge_chunk(chunk_id, content=content),
        relevance,
    )


def _program_result(chunk_id: str, name: str, faculty: str) -> _Result:
    chunk = replace(
        knowledge_chunk(
            chunk_id,
            source_id="DIU-PROG-001",
            content=f"{name} | {faculty}",
            category="undergraduate_programs",
            program=name,
        ),
        faculty=faculty,
        content_type="table",
    )
    return _Result(chunk, 0.95)


def _client(retriever: _FakeRetriever, generator) -> TestClient:
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        retriever, generator=generator
    )
    return TestClient(app)


def _reset_overrides() -> None:
    app.dependency_overrides.pop(get_chat_service, None)


def test_generated_chat_returns_grounded_answer_and_sources() -> None:
    retriever = _FakeRetriever(
        {
            "What documents are required?": [
                _evidence_result(
                    "doc1",
                    content="Verified DIU document requirements evidence.",
                    relevance=0.93,
                )
            ]
        }
    )
    generator = _FakeGenerator()
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat",
        json={"message": "What documents are required?", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Grounded generated answer."
    assert body["confidence"] == "high"
    assert body["language"] == "en"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["url"].startswith("https://")
    assert len(generator.calls) == 1
    _reset_overrides()


def test_grounding_prompt_preserves_explicit_scope_constraints() -> None:
    result = _evidence_result(
        "general-schedule",
        content="General DIU admission test date: August 28, 2026.",
        relevance=0.93,
    )

    messages = build_grounded_messages(
        "When is the FSIT admission test?", "en", [result]
    )

    system_prompt = messages[0]["content"]
    assert "explicit faculty" in system_prompt
    assert "Do not attach a general date" in system_prompt


def test_eligibility_question_uses_deterministic_checker_guidance() -> None:
    query = "Am I eligible for BSc in CSE?"
    resolved_query = (
        "Am I eligible for BSc in CSE. "
        "Program: Computer Science and Engineering."
    )
    retriever = _FakeRetriever(
        {
            resolved_query: [
                _program_result(
                    "cse-program",
                    "B. Sc. in Computer Science and Engineering",
                    "Science and Information Technology",
                )
            ]
        }
    )
    generator = _FakeGenerator("This must not decide eligibility.")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "cannot determine your eligibility" in body["answer"]
    assert "Eligibility Checker" in body["answer"]
    assert body["sources"][0]["url"].startswith("https://")
    assert generator.calls == []
    _reset_overrides()


def test_program_list_uses_complete_structured_rows_without_generator_omission() -> None:
    query = "Which business programs does DIU offer?"
    names = [
        "Bachelor of Business Administration (BBA)",
        "BBA in Finance & Banking",
        "Master of Business Administration (MBA)",
    ]
    retriever = _FakeRetriever(
        {
            query: [
                _program_result(f"program-{index}", name, "Business & Entrepreneurship")
                for index, name in enumerate(names)
            ]
        }
    )
    generator = _FakeGenerator()
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    assert retriever.top_ks == [60]
    assert generator.calls == []
    answer = response.json()["answer"]
    assert all(name in answer for name in names)
    _reset_overrides()


def test_bare_faculty_name_returns_its_structured_program_catalog() -> None:
    query = "Graduate Studies"
    names = ["Master of Development Studies (MDS)", "Master of Law (LL.M.)"]
    retriever = _FakeRetriever(
        {
            query: [
                _program_result(f"graduate-{index}", name, "Graduate Studies")
                for index, name in enumerate(names)
            ]
        }
    )
    generator = _FakeGenerator("The generator must not rewrite catalog rows.")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    assert retriever.top_ks == [60]
    assert generator.calls == []
    body = response.json()
    assert "Graduate Studies programs" in body["answer"]
    assert all(name in body["answer"] for name in names)
    assert body["sources"]
    _reset_overrides()


def test_generator_receives_grounded_evidence() -> None:
    retriever = _FakeRetriever(
        {
            "What documents are required?": [
                _evidence_result(
                    "doc1",
                    content="Verified DIU document requirements evidence.",
                    relevance=0.93,
                )
            ]
        }
    )
    generator = _FakeGenerator()
    client = _client(retriever, generator)

    client.post(
        "/api/chat",
        json={"message": "What documents are required?", "language": "en"},
    )

    messages = generator.calls[0]
    assert len(messages) == 2
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]
    assert "ONLY the DIU evidence" in system_prompt
    assert "insufficient" in system_prompt
    assert "Do not invent citations or URLs" in system_prompt
    assert "at most six bullets" in system_prompt
    assert "What documents are required?" in user_prompt
    assert "Verified DIU document requirements evidence." in user_prompt
    assert "daffodilvarsity.edu.bd" in user_prompt
    assert "English" in user_prompt
    _reset_overrides()


def test_generated_waiver_chat_uses_concise_extraction_prompt() -> None:
    """Waiver chat must pass clean table evidence and a concise extraction prompt.

    Regression for the demo fix: the grounded prompt now asks the model to state
    the exact waiver value from the evidence and answer briefly, which prevents
    refusals and long rambling (the cause of frontend timeouts) on waiver-rate
    questions.
    """
    waiver_table_content = (
        "Section: Waiver schemes for CSE and SWE program "
        "GPA-5 both in SSC and in HSC | 25% | 3.00"
    )
    query = "I am applying for CSE with SSC GPA 5 and HSC GPA 5. What waiver can I get?"
    retriever = _FakeRetriever(
        {
            query: [
                _evidence_result(
                    "waiver-table",
                    content=waiver_table_content,
                    relevance=0.95,
                )
            ]
        }
    )
    generator = _FakeGenerator()
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat",
        json={
            "message": query,
            "language": "en",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "high"
    assert body["sources"][0]["url"].startswith("https://")
    system_prompt = generator.calls[0][0]["content"]
    user_prompt = generator.calls[0][1]["content"]
    assert "concise" in system_prompt
    assert "exact values in the evidence" in system_prompt
    assert waiver_table_content in user_prompt
    assert "exact value" in user_prompt
    assert "Be concise" in user_prompt
    _reset_overrides()


def test_generator_not_called_for_out_of_domain_question() -> None:
    retriever = _FakeRetriever({})
    generator = _FakeGenerator()
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat",
        json={"message": "What are the requirements at NSU?", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "low"
    assert body["sources"] == []
    assert generator.calls == []
    _reset_overrides()


def test_generator_not_called_for_insufficient_evidence() -> None:
    retriever = _FakeRetriever({})
    generator = _FakeGenerator()
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat",
        json={"message": "Unknown obscure question", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "low"
    assert body["sources"] == []
    assert generator.calls == []
    assert body["answer"].strip()
    _reset_overrides()


def test_unsupported_program_claim_returns_insufficient_without_catalog_answer() -> None:
    query = "All Students of Undergraduate Program Will Get a Laptop Free."
    retriever = _FakeRetriever({})
    generator = _FakeGenerator("Invented laptop policy")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "enough verified information" in body["answer"]
    assert body["sources"] == []
    assert generator.calls == []
    _reset_overrides()


def test_universal_scholarship_claim_is_not_rewritten_as_a_scholarship_list() -> None:
    query = "Is every student guaranteed a scholarship?"
    retriever = _FakeRetriever(
        {
            query: [
                _evidence_result(
                    "scholarship-list",
                    content="Browse by Section\nDIU Scholarship\nSee More",
                    relevance=0.93,
                )
            ]
        }
    )
    generator = _FakeGenerator(
        "The supplied evidence does not establish that guarantee."
    )
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "The supplied evidence does not establish that guarantee."
    )
    assert len(generator.calls) == 1
    _reset_overrides()


def test_financial_aid_does_not_use_local_scholarship_list_formatter() -> None:
    query = "Financial Aid & Scholarships"
    result = _evidence_result(
        "financial-aid",
        content=(
            "Browse by Section\nDIU Scholarship\nSee More\n"
            "Verified financial-aid guidance."
        ),
        relevance=0.93,
    )
    result.chunk = replace(result.chunk, category="financial_aid")
    retriever = _FakeRetriever({query: [result]})
    generator = _FakeGenerator("Grounded financial-aid answer.")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Grounded financial-aid answer."
    assert len(generator.calls) == 1
    _reset_overrides()


def test_partial_only_official_page_returns_link_without_generation() -> None:
    query = "Life insurance"
    partial = _Result(
        knowledge_chunk(
            "life-insurance-page",
            source_id="DIU-INS-001",
            content="Life Insurance for Student and Guardian",
            category="life_insurance",
            extraction_status="partial",
        ),
        0.8,
    )
    retriever = _FakeRetriever({query: [partial]})
    generator = _FakeGenerator(answer="Invented insurance details")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "low"
    assert "enough verified information" in body["answer"]
    assert [source["title"] for source in body["sources"]] == [
        "DIU source life-insurance-page"
    ]
    assert generator.calls == []
    _reset_overrides()


def test_generator_bangla_query_uses_bangla_language_prompt() -> None:
    retriever = _FakeRetriever(
        {
            "ভর্তির জন্য কী লাগে": [
                _evidence_result(
                    "doc2", content="Bengali admission evidence text.", relevance=0.9
                )
            ]
        }
    )
    generator = _FakeGenerator()
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat",
        json={"message": "ভর্তির জন্য কী লাগে", "language": "bn"},
    )

    assert response.status_code == 200
    assert response.json()["language"] == "bn"
    assert "Bengali (Bangla)" in generator.calls[0][1]["content"]
    _reset_overrides()


def test_generated_empty_answer_falls_back_to_evidence_summary() -> None:
    retriever = _FakeRetriever(
        {
            "What documents are required?": [
                _evidence_result(
                    "doc1",
                    content="Verified DIU document requirements evidence.",
                    relevance=0.93,
                )
            ]
        }
    )
    generator = _FakeGenerator(answer="   ")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat",
        json={"message": "What documents are required?", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "not an AI-generated answer" in body["answer"]
    assert body["confidence"] == "high"
    assert len(generator.calls) == 1
    _reset_overrides()


def test_generator_unavailable_maps_to_503() -> None:
    retriever = _FakeRetriever(
        {
            "What documents are required?": [
                _evidence_result(
                    "doc1",
                    content="Verified DIU document requirements evidence.",
                    relevance=0.93,
                )
            ]
        }
    )
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        retriever, generator=_BrokenGenerator()
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": "What documents are required?", "language": "en"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert "temporarily unavailable" in body["error"]["message"]
    _reset_overrides()


def test_evidence_summary_fallback_without_generator() -> None:
    retriever = _FakeRetriever(
        {
            "What documents are required?": [
                _evidence_result(
                    "doc1",
                    content="Verified DIU document requirements evidence.",
                    relevance=0.93,
                )
            ]
        }
    )
    app.dependency_overrides[get_chat_service] = lambda: ChatService(retriever)
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": "What documents are required?", "language": "en"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "not an AI-generated answer" in body["answer"]
    assert body["confidence"] == "high"
    assert len(body["sources"]) == 1
    _reset_overrides()


def test_structured_tuition_answer_preserves_table_labels_and_units() -> None:
    content = (
        "Tuition Fees for Local Students\n"
        "Full Program Name | Majors | Credit Hours | Duration | "
        "Payable During Admission | Average Semester Fees | Total Tuition Fees | "
        "Total Program Fees\n"
        "B. Sc. in Computer Science and Engineering | Artificial Intelligence | "
        "154.5 | 4 Years | 61,750 | 85,000 | 782,250 | 1,020,450"
    )
    result = _evidence_result("cse-local-fee", content=content, relevance=0.95)
    result.chunk = replace(
        result.chunk,
        category="tuition_and_fees",
        content_type="table",
        program="B. Sc. in Computer Science and Engineering",
    )
    retriever = _FakeRetriever({"What is the tuition fee of CSE?": [result]})
    generator = _FakeGenerator(answer="Incorrectly says 85,000 per year.")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat",
        json={"message": "What is the tuition fee of CSE?", "language": "en"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "BDT 782,250" in answer
    assert "BDT 1,020,450" in answer
    assert "average semester fees" in answer.casefold()
    assert "per year" not in answer.casefold()
    assert "$" not in answer
    assert generator.calls == []
    _reset_overrides()


def test_structured_tuition_comparison_renders_local_and_international_rows() -> None:
    query = "Compare local and international CSE tuition fees"
    program = "B. Sc. in Computer Science and Engineering"
    local = _evidence_result(
        "cse-local-comparison",
        content=(
            "Tuition Fees for Local Students\n"
            "Full Program Name | Payable During Admission | Total Tuition Fees | "
            "Total Program Fees\n"
            f"{program} | 61,750 | 782,250 | 1,020,450"
        ),
        relevance=0.96,
    )
    local.chunk = replace(
        local.chunk,
        category="tuition_and_fees",
        content_type="table",
        program=program,
    )
    international = _evidence_result(
        "cse-international-comparison",
        content=(
            "Tuition Fees for International Students\n"
            "Full Program Name | 1st Yr During Admission | Total Tuition Fees | "
            "Total Program Fees\n"
            f"{program} | $ 2476 | $ 7,847 | $ 10,250"
        ),
        relevance=0.95,
    )
    international.chunk = replace(
        international.chunk,
        category="international_admission",
        content_type="table",
        program=program,
    )
    retriever = _FakeRetriever({query: [local, international]})
    generator = _FakeGenerator(answer="Incorrectly merges the currencies.")
    client = _client(retriever, generator)

    response = client.post("/api/chat", json={"message": query, "language": "en"})

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "local students" in answer
    assert "international students" in answer
    assert "BDT 782,250" in answer
    assert "USD 7,847" in answer
    assert "USD 10,250" in answer
    assert "BDT 7,847" not in answer
    assert generator.calls == []
    _reset_overrides()


def test_structured_tuition_selects_canonical_row_among_secondary_results() -> None:
    query = "Development Studies tuition fees"
    fee_headers = (
        "Full Program Name | Credit Hours | Duration | Payable During Admission | "
        "Average Semester Fees | Total Tuition Fees | Total Program Fees"
    )
    unrelated = _evidence_result(
        "other-fee",
        content=(
            "Tuition Fees for Local Students\n"
            f"{fee_headers}\n"
            "Bachelor of Development Studies | 120 | 4 Years | 10 | 20 | 30 | 40"
        ),
        relevance=0.97,
    )
    unrelated.chunk = replace(
        unrelated.chunk,
        category="tuition_and_fees",
        content_type="table",
        program="Bachelor of Development Studies",
    )
    expected = _evidence_result(
        "mds-fee",
        content=(
            "Tuition Fees for Local Students\n"
            f"{fee_headers}\n"
            "Master of Development Studies (MDS) | 39 | 1 Year | 11 | 22 | 33 | 44"
        ),
        relevance=0.94,
    )
    expected.chunk = replace(
        expected.chunk,
        category="tuition_and_fees",
        content_type="table",
        program="Master of Development Studies (MDS)",
    )
    retriever = _FakeRetriever({query: [unrelated, expected]})
    generator = _FakeGenerator(answer="The available information is insufficient.")
    client = _client(retriever, generator)

    response = client.post("/api/chat", json={"message": query, "language": "en"})

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "Master of Development Studies (MDS)" in answer
    assert "BDT 33" in answer
    assert "Bachelor of Development Studies" not in answer
    assert generator.calls == []
    _reset_overrides()


def test_explicit_postgraduate_tuition_never_uses_undergraduate_row() -> None:
    query = "MA in English tuition fees"
    headers = "Full Program Name | Total Tuition Fees | Total Program Fees"
    undergraduate = _evidence_result(
        "ba-english-fee",
        content=(
            "Tuition Fees for Local Students\n"
            f"{headers}\nB.A. (Hons) in English | 111 | 222"
        ),
        relevance=0.99,
    )
    undergraduate.chunk = replace(
        undergraduate.chunk,
        category="tuition_and_fees",
        content_type="table",
        program="B.A. (Hons) in English",
    )
    postgraduate = _evidence_result(
        "ma-english-fee",
        content=(
            "Tuition Fees for Local Students\n"
            f"{headers}\nM. A in English | 333 | 444"
        ),
        relevance=0.93,
    )
    postgraduate.chunk = replace(
        postgraduate.chunk,
        category="tuition_and_fees",
        content_type="table",
        program="M. A in English",
    )
    retriever = _FakeRetriever({query: [undergraduate, postgraduate]})
    generator = _FakeGenerator(answer="Incorrect undergraduate answer.")
    client = _client(retriever, generator)

    response = client.post("/api/chat", json={"message": query, "language": "en"})

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "M. A in English" in answer
    assert "BDT 333" in answer
    assert "B.A. (Hons)" not in answer
    assert generator.calls == []
    _reset_overrides()


def test_multiple_program_tuition_rows_are_rendered_without_model_omission() -> None:
    query = "CSE and Master of Pharmacy tuition fees"
    headers = "Full Program Name | Total Tuition Fees | Total Program Fees"
    cse = _evidence_result(
        "cse-fee",
        content=(
            "Tuition Fees for Local Students\n"
            f"{headers}\nB. Sc. in Computer Science and Engineering | 111 | 222"
        ),
        relevance=0.96,
    )
    cse.chunk = replace(
        cse.chunk,
        category="tuition_and_fees",
        content_type="table",
        program="B. Sc. in Computer Science and Engineering",
    )
    mpharm = _evidence_result(
        "mpharm-fee",
        content=(
            "Tuition Fees for Local Students\n"
            f"{headers}\nMaster of Pharmacy | 333 | 444"
        ),
        relevance=0.94,
    )
    mpharm.chunk = replace(
        mpharm.chunk,
        category="tuition_and_fees",
        content_type="table",
        program="Master of Pharmacy",
    )
    retriever = _FakeRetriever({query: [cse, mpharm]})
    generator = _FakeGenerator(answer="Only one program was described.")
    client = _client(retriever, generator)

    response = client.post("/api/chat", json={"message": query, "language": "en"})

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "B. Sc. in Computer Science and Engineering" in answer
    assert "BDT 111" in answer
    assert "Master of Pharmacy" in answer
    assert "BDT 333" in answer
    assert generator.calls == []
    _reset_overrides()


def test_grade_based_waiver_without_program_asks_for_program() -> None:
    result = _evidence_result(
        "waiver-table",
        content=(
            "Faculty-specific waiver tables: CSE and SWE; B.Pharm and LLB; "
            "Humanities and Social Sciences."
        ),
        relevance=0.95,
    )
    result.chunk = replace(
        result.chunk,
        category="waivers",
        content_type="table",
    )
    query = "I got SSC GPA 5 and HSC GPA 5. What waiver can I get?"
    retriever = _FakeRetriever({query: [result]})
    generator = _FakeGenerator(answer="Invented 50% waiver.")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    assert "program" in response.json()["answer"].casefold()
    assert "50%" not in response.json()["answer"]
    assert generator.calls == []
    _reset_overrides()


def test_program_waiver_uses_matching_ssc_hsc_table_row() -> None:
    content = (
        "Policy of Waiver and Scholarship — Spring 2026\n"
        "Section: Waiver schemes for CSE and SWE program\n"
        "Result of SSC, HSC & Equivalence | Waiver Rate | SGPA to be obtained | "
        "Results of English Medium background | Waiver Rate\n"
        "Golden GPA-5 both in SSC and in HSC | 40% | 3.25 | "
        "5 As in O levels and 2 As in A levels | 50%\n"
        "Golden GPA-5 in HSC | 20% | 3.00 | 01 A and 01 B | 30%\n"
        "GPA-5 both in SSC and in HSC | 15% | 3.00 | 02 Bs | 25%"
    )
    result = _evidence_result("cse-waiver", content=content, relevance=0.95)
    result.chunk = replace(
        result.chunk,
        category="waivers",
        content_type="table",
    )
    query = "I am applying for CSE with SSC GPA 5 and HSC GPA 5. What waiver can I get?"
    retriever = _FakeRetriever({query: [result]})
    generator = _FakeGenerator(answer="Incorrect English-medium rate: 30%.")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "15%" in answer
    assert "SGPA to be obtained — 3.00" in answer
    assert "30%" not in answer
    assert generator.calls == []
    _reset_overrides()


def test_scholarship_answer_lists_only_explicit_browse_section_names() -> None:
    content = (
        "DIU Scholarships for Local Students\n"
        "Local Scholarship\n"
        "Explore various scholarship opportunities at DIU\n"
        "Browse by Section\n"
        "DIU Scholarship\n"
        "Chairman Endowment Fund Scholarship\n"
        "Lutfar Rahman Scholarship\n"
        "See More\n"
        "Waiver and Tuition Fee Calculator"
    )
    result = _evidence_result("scholarship-list", content=content, relevance=0.95)
    result.chunk = replace(result.chunk, category="scholarships")
    query = "What scholarships are available at DIU?"
    retriever = _FakeRetriever({query: [result]})
    generator = _FakeGenerator(answer="Invented scholarship name.")
    client = _client(retriever, generator)

    response = client.post(
        "/api/chat", json={"message": query, "language": "en"}
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "DIU Scholarship" in answer
    assert "Chairman Endowment Fund Scholarship" in answer
    assert "Lutfar Rahman Scholarship" in answer
    assert "not exhaustive" in answer
    assert "Invented" not in answer
    assert generator.calls == []
    _reset_overrides()
