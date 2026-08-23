"""Evidence-grounding regressions for public chat question variants."""

from __future__ import annotations

from typing import List, Sequence

import pytest

from rag.retriever import Retriever
from rag.vector_store import InMemoryVectorStore
from tests.rag_helpers import knowledge_chunk


class _IntentLaneEmbedder:
    model_name = "fixture-embedding"
    model_revision = None
    dimension = 2

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, query: str) -> List[float]:
        return self._vector(query)

    @staticmethod
    def _vector(text: str) -> List[float]:
        folded = text.casefold()
        evidence_markers = (
            "admission application process",
            "required admission documents",
            "local bachelor program diploma",
            "official online admission form",
            "tuition fees",
            "financial aid scholarships",
            "official waiver policy",
            "tuition fee waiver",
            "waiver",
            "complete program catalog",
            "program eligibility verification",
            "admission test schedule",
            "admission test seat plan",
            "admission test result",
            "credit transfer guidelines",
            "guidelines for guardians",
            "payment guidelines",
            "scholarships for international students",
            "waiver and tuition fee calculator",
            "financial aid and scholarship programs",
            "life insurance",
            "application deadline",
        )
        return [1.0, 0.0] if any(marker in folded for marker in evidence_markers) else [0.0, 1.0]


def _retriever() -> Retriever:
    chunks = [
        knowledge_chunk(
            "application-flow",
            source_id="DIU-ADM-002",
            content="DIU admission application process flow and steps for a new applicant.",
            category="admission_process",
        ),
        knowledge_chunk(
            "documents",
            source_id="DIU-DOC-001",
            content="Required admission documents checklist certificate transcript.",
            category="required_admission_documents",
            program="For Bachelor Program Students",
        ),
        knowledge_chunk(
            "online-documents",
            source_id="DIU-DOC-001",
            content="Required admission documents checklist certificate transcript online application.",
            category="required_admission_documents",
            program="For online Application",
        ),
        knowledge_chunk(
            "diploma-application",
            source_id="DIU-APP-001",
            content="Online Admission Form Local Bachelor Program Diploma Apply Type.",
            category="admission_application_process",
        ),
        knowledge_chunk(
            "cse-fee",
            source_id="DIU-FEE-001",
            content="Computer Science and Engineering tuition fees total program fees.",
            category="tuition_and_fees",
            program="B. Sc. in Computer Science and Engineering",
        ),
        knowledge_chunk(
            "scholarship",
            source_id="DIU-SCH-001",
            content="DIU financial aid scholarships for local students.",
            category="scholarships",
        ),
        knowledge_chunk(
            "female-waiver",
            source_id="DIU-WAV-001",
            content="Official waiver policy: Female Quota tuition fee waiver categories.",
            category="waivers",
        ),
        knowledge_chunk(
            "program-catalog",
            source_id="DIU-PROG-001",
            content="DIU complete program catalog across all faculties.",
            category="undergraduate_programs",
        ),
        knowledge_chunk(
            "cse-program",
            source_id="DIU-PROG-001",
            content="Computer Science and Engineering program eligibility verification.",
            category="undergraduate_programs",
            program="B. Sc. in Computer Science and Engineering",
        ),
        knowledge_chunk(
            "irrelevant",
            source_id="DIU-CON-001",
            content="Admission office contact phone number.",
            category="admission_contact_information",
        ),
        knowledge_chunk(
            "admission-schedule",
            source_id="DIU-ADM-001",
            content="Current DIU admission test schedule date and time.",
            category="admission_overview",
        ),
        knowledge_chunk(
            "admission-result",
            source_id="DIU-TEST-001",
            content="Official DIU admission test result page and seat plan updates.",
            category="admission_test_result",
        ),
        knowledge_chunk(
            "credit-transfer",
            source_id="DIU-CRD-001",
            content="Official DIU credit transfer guidelines and process.",
            category="credit_transfer_guidelines",
        ),
        knowledge_chunk(
            "guardian-guidelines",
            source_id="DIU-GRD-001",
            content="Official DIU guidelines for guardians.",
            category="guardian_guidelines",
        ),
        knowledge_chunk(
            "payment-guidelines",
            source_id="DIU-PAY-001",
            content="Official DIU payment guidelines for all students.",
            category="payment_guidelines",
        ),
        knowledge_chunk(
            "international-scholarship",
            source_id="DIU-INT-004",
            content="Official DIU scholarships for international students.",
            category="international_scholarships",
        ),
        knowledge_chunk(
            "waiver-calculator",
            source_id="DIU-WAV-002",
            content="Official DIU waiver and tuition fee calculator.",
            category="waiver_calculator",
        ),
        knowledge_chunk(
            "financial-aid",
            source_id="DIU-FIN-001",
            content="Official DIU financial aid and scholarship programs.",
            category="financial_aid",
        ),
        knowledge_chunk(
            "life-insurance",
            source_id="DIU-INS-001",
            content="Official DIU student and guardian life insurance.",
            category="life_insurance",
        ),
        knowledge_chunk(
            "application-deadline",
            source_id="DIU-NOT-001",
            content="Current DIU admission application deadline and last date.",
            category="admission_notices",
        ),
    ]
    embedder = _IntentLaneEmbedder()
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(chunks, embedder.embed_documents([chunk.content for chunk in chunks]))
    return Retriever(embedder, store, candidate_multiplier=10, max_results_per_source=10)


@pytest.mark.parametrize(
    ("query", "expected_source"),
    [
        ("How do I apply?", "DIU-ADM-002"),
        ("What steps does DIU's admission flowchart show?", "DIU-ADM-002"),
        ("vorti kivabe korbo?", "DIU-ADM-002"),
        ("What are the admission requirements?", "DIU-DOC-001"),
        ("What documents are required for bachelor admission?", "DIU-DOC-001"),
        ("What documents are required for an online application?", "DIU-DOC-001"),
        ("ভর্তির জন্য কী কী কাগজ লাগবে?", "DIU-DOC-001"),
        ("Can diploma students apply?", "DIU-APP-001"),
        ("Can I select the diploma pathway in the online application?", "DIU-APP-001"),
        ("Apply online", "DIU-APP-001"),
        ("What is the total fee for CSE?", "DIU-FEE-001"),
        ("এডমিশন ফি কত?", "DIU-FEE-001"),
        ("Tell me about scholarships", "DIU-SCH-001"),
        ("Which scholarship categories does DIU list?", "DIU-SCH-001"),
        ("waiver", "DIU-WAV-001"),
        ("female waiver", "DIU-WAV-001"),
        ("female waever", "DIU-WAV-001"),
        ("scholership", "DIU-SCH-001"),
        ("Show available programs", "DIU-PROG-001"),
        ("Show DIU's official program catalog", "DIU-PROG-001"),
        ("am i eligible for bsc in cse?", "DIU-PROG-001"),
        ("CSE ar admission condition", "DIU-PROG-001"),
        ("Admission test schedule", "DIU-ADM-001"),
        ("seat plan", "DIU-TEST-001"),
        ("Admission test result", "DIU-TEST-001"),
        ("credit transfer guidelines", "DIU-CRD-001"),
        ("guidelines for guardians", "DIU-GRD-001"),
        ("payment guidelines", "DIU-PAY-001"),
        ("scholarships for international students", "DIU-INT-004"),
        ("waiver and tuition fee calculator", "DIU-WAV-002"),
        ("financial aid", "DIU-FIN-001"),
        ("life insurance", "DIU-INS-001"),
        ("Last Date to Apply", "DIU-NOT-001"),
    ],
)
def test_common_questions_retrieve_expected_official_evidence(
    query: str, expected_source: str
) -> None:
    results = _retriever().retrieve(query, top_k=5)

    assert results
    assert results[0].chunk.source_id == expected_source
    assert results[0].chunk.source_url.startswith("https://daffodilvarsity.edu.bd/")


@pytest.mark.parametrize(
    "query",
    [
        "What is NSU's admission policy?",
        "What is the weather in Dhaka?",
        "Tell me my personal application status",
        "Guarantee that DIU will give me a secret scholarship",
    ],
)
def test_unsupported_questions_still_refuse_without_evidence(query: str) -> None:
    assert _retriever().retrieve(query) == []


def test_exact_topic_lane_returns_partial_official_page_as_link_evidence() -> None:
    embedder = _IntentLaneEmbedder()
    partial = knowledge_chunk(
        "partial-life-insurance",
        source_id="DIU-INS-001",
        content="Life Insurance for Student and Guardian",
        category="life_insurance",
        extraction_status="partial",
    )
    unrelated = knowledge_chunk(
        "generic-admission",
        source_id="DIU-ADM-001",
        content="General admission information and support for students.",
        category="admission_overview",
    )
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(
        [partial, unrelated],
        embedder.embed_documents([partial.content, unrelated.content]),
    )
    retriever = Retriever(embedder, store, candidate_multiplier=1)

    results = retriever.retrieve("Life insurance", top_k=1)

    assert [result.chunk.source_id for result in results] == ["DIU-INS-001"]
    assert results[0].chunk.extraction_status == "partial"


def test_unsupported_program_claim_cannot_fall_back_to_program_catalog() -> None:
    query = "All Students of Undergraduate Program Will Get a Laptop Free."

    assert _retriever().retrieve(query, top_k=5) == []


def test_universal_scholarship_claim_cannot_fall_back_to_scholarship_list() -> None:
    assert _retriever().retrieve(
        "Does every undergraduate student receive a scholarship?", top_k=5
    ) == []


def test_multiple_named_programs_cannot_admit_unrelated_tuition_rows() -> None:
    embedder = _IntentLaneEmbedder()
    chunks = [
        knowledge_chunk(
            "cse-fee-row",
            source_id="DIU-FEE-001",
            category="tuition_and_fees",
            program="B. Sc. in Computer Science and Engineering",
            content="Computer Science and Engineering tuition fees.",
        ),
        knowledge_chunk(
            "swe-fee-row",
            source_id="DIU-FEE-001",
            category="tuition_and_fees",
            program="B. Sc. in Software Engineering",
            content="Software Engineering tuition fees.",
        ),
        knowledge_chunk(
            "bba-fee-row",
            source_id="DIU-FEE-001",
            category="tuition_and_fees",
            program="Bachelor of Business Administration",
            content="Bachelor of Business Administration tuition fees.",
        ),
    ]
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(
        chunks, embedder.embed_documents([chunk.content for chunk in chunks])
    )
    retriever = Retriever(embedder, store, candidate_multiplier=5)

    results = retriever.retrieve("CSE and SWE tuition fees", top_k=5)

    assert {result.chunk.chunk_id for result in results} == {
        "cse-fee-row",
        "swe-fee-row",
    }


def test_international_documents_do_not_fall_back_to_local_checklist() -> None:
    assert _retriever().retrieve("international student documents", top_k=5) == []


def test_generic_fact_check_accepts_only_evidence_containing_the_claim_focus() -> None:
    embedder = _IntentLaneEmbedder()
    laptop = knowledge_chunk(
        "verified-laptop-policy",
        source_id="DIU-ADM-001",
        content="Official DIU policy states that eligible students receive a free laptop.",
        category="admission_overview",
    )
    catalog = knowledge_chunk(
        "program-catalog-only",
        source_id="DIU-PROG-001",
        content="Official undergraduate program catalog for all students.",
        category="undergraduate_programs",
    )
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(
        [laptop, catalog],
        embedder.embed_documents([laptop.content, catalog.content]),
    )
    retriever = Retriever(embedder, store, candidate_multiplier=5)

    results = retriever.retrieve(
        "Does DIU give every undergraduate student a free laptop?", top_k=5
    )

    assert [result.chunk.chunk_id for result in results] == [
        "verified-laptop-policy"
    ]


def test_scoped_schedule_query_cannot_fall_back_to_generic_catalog_evidence() -> None:
    embedder = _IntentLaneEmbedder()
    fsit_schedule = knowledge_chunk(
        "fsit-admission-schedule",
        source_id="DIU-NOT-001",
        content=(
            "Faculty of Science and Information Technology admission test "
            "schedule, date, and time."
        ),
        category="admission_notices",
        faculty="Faculty of Science and Information Technology",
    )
    generic_schedule = knowledge_chunk(
        "generic-admission-schedule",
        source_id="DIU-ADM-001",
        content="Current DIU admission test schedule date and time.",
        category="admission_overview",
    )
    program_catalog = knowledge_chunk(
        "fsit-program-catalog",
        source_id="DIU-PROG-001",
        content="Science and Information Technology programs and degrees.",
        category="undergraduate_programs",
        faculty="Faculty of Science and Information Technology",
    )
    store = InMemoryVectorStore(
        embedding_dimension=embedder.dimension,
        embedding_model_name=embedder.model_name,
    )
    store.upsert_chunks(
        [fsit_schedule, generic_schedule, program_catalog],
        embedder.embed_documents(
            [fsit_schedule.content, generic_schedule.content, program_catalog.content]
        ),
    )
    retriever = Retriever(embedder, store, candidate_multiplier=5)

    results = retriever.retrieve(
        "Faculty of Science and Information Technology admission test time and date",
        top_k=5,
    )

    assert [result.chunk.chunk_id for result in results] == [
        "fsit-admission-schedule"
    ]
