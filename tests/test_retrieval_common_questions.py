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
            "tuition fees",
            "financial aid scholarships",
            "official waiver policy",
            "tuition fee waiver",
            "waiver",
            "complete program catalog",
            "program eligibility verification",
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
