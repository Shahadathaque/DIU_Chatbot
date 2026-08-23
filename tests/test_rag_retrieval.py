from __future__ import annotations

from dataclasses import replace
import math
from typing import List, Sequence

import pytest

from rag.config import RagSettings
from rag.embeddings import EmbeddingUnavailableError
from rag.query_processing import QueryIntent, analyze_query
from rag.retriever import (
    Retriever,
    _chunk_program_matches,
    _matched_program_phrase,
    _named_program_markers,
    _program_level_matches,
    _single_named_program_acronym,
    create_retriever,
    normalize_query,
)
from rag.vector_store import InMemoryVectorStore
from tests.rag_helpers import knowledge_chunk


class FakeEmbedder:
    model_name = "fixture-embedding"
    model_revision = None
    dimension = 2

    def __init__(self) -> None:
        self.queries: List[str] = []

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return [[1.0, 0.0] for _text in texts]

    def embed_query(self, query: str) -> List[float]:
        self.queries.append(query)
        return [1.0, 0.0]


class _ScoringEmbedder:
    """Fixture embedder that maps document text to a fixed similarity vector."""

    model_name = "fixture-embedding"
    model_revision = None
    dimension = 2

    def __init__(self, vectors: dict) -> None:
        self._vectors = dict(vectors)

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._vectors[text] for text in texts]

    def embed_query(self, query: str) -> List[float]:
        return [1.0, 0.0]


class _AidFocusEmbedder:
    """Separate canonical intent and raw user-focus embedding lanes."""

    model_name = "fixture-embedding"
    model_revision = None
    dimension = 3

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        raise AssertionError("test supplies document vectors directly")

    def embed_query(self, query: str) -> List[float]:
        if query.casefold() == "female waiver":
            return [0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0]


class _UnavailableEmbedder(FakeEmbedder):
    """Hosted-provider fixture that is rate limited for every query."""

    def embed_query(self, query: str) -> List[float]:
        self.queries.append(query)
        raise EmbeddingUnavailableError("embedding provider returned HTTP 429")


def _store() -> InMemoryVectorStore:
    return InMemoryVectorStore(
        embedding_dimension=2,
        embedding_model_name="fixture-embedding",
    )


def test_default_authority_gate_and_current_beats_historical() -> None:
    chunks = [
        knowledge_chunk(
            "current",
            content="Current DIU admission requirements verified evidence",
        ),
        knowledge_chunk(
            "stable",
            content="Stable DIU document checklist reference",
            currency_status="stable_reference",
        ),
        knowledge_chunk(
            "historical",
            content="Historical DIU admission fees from 2021",
            currency_status="historical",
        ),
        knowledge_chunk(
            "uncertain",
            content="Uncertain DIU international admission policy",
            currency_status="uncertain",
        ),
        knowledge_chunk(
            "manual",
            content="Manual review DIU BBA admission shell",
            manual_review=True,
        ),
    ]
    store = _store()
    store.upsert_chunks(chunks, [[1.0, 0.0]] * len(chunks))
    retriever = Retriever(
        FakeEmbedder(),
        store,
        min_relevance_score=-1.0,
        max_results_per_source=10,
    )

    default = retriever.retrieve("DIU admission", top_k=10)
    assert {result.chunk.chunk_id for result in default} == {"current", "stable"}

    opted_in = retriever.retrieve(
        "DIU admission",
        top_k=10,
        include_historical=True,
        include_uncertain=True,
        include_manual_review=True,
    )
    by_id = {result.chunk.chunk_id: result for result in opted_in}
    assert set(by_id) == {"current", "stable", "historical", "uncertain", "manual"}
    assert by_id["current"].relevance_score > by_id["historical"].relevance_score
    assert by_id["current"].similarity_score == by_id["historical"].similarity_score


def test_authority_tiers_precede_similarity_for_opted_in_evidence() -> None:
    chunks = [
        knowledge_chunk("current", content="Current verified DIU admission evidence"),
        knowledge_chunk(
            "stable",
            content="Stable verified DIU admission reference",
            currency_status="stable_reference",
        ),
        knowledge_chunk(
            "uncertain",
            content="Uncertain DIU admission information",
            currency_status="uncertain",
        ),
        knowledge_chunk(
            "historical",
            content="Historical DIU admission information",
            currency_status="historical",
        ),
        knowledge_chunk(
            "manual",
            content="Manual review DIU admission information",
            manual_review=True,
        ),
        knowledge_chunk(
            "partial",
            content="Partially extracted DIU admission information",
            extraction_status="partial",
        ),
    ]
    similarities = [0.76, 0.82, 0.95, 1.0, 0.99, 0.98]
    embeddings = [
        [similarity, math.sqrt(1.0 - similarity * similarity)]
        for similarity in similarities
    ]
    store = _store()
    store.upsert_chunks(chunks, embeddings)
    retriever = Retriever(
        FakeEmbedder(),
        store,
        min_relevance_score=-1.0,
        candidate_multiplier=2,
        max_results_per_source=10,
    )

    results = retriever.retrieve(
        "DIU admission",
        top_k=6,
        include_historical=True,
        include_uncertain=True,
        include_manual_review=True,
        include_partial=True,
    )

    assert [result.chunk.chunk_id for result in results] == [
        "current",
        "stable",
        "uncertain",
        "historical",
        "partial",
        "manual",
    ]
    assert results[0].relevance_score < results[3].relevance_score


def test_lower_authority_candidates_cannot_evict_current_or_stable() -> None:
    chunks = [
        knowledge_chunk("current", content="Current DIU admission evidence"),
        knowledge_chunk(
            "stable",
            content="Stable DIU admission evidence",
            currency_status="stable_reference",
        ),
    ]
    embeddings = [[0.80, 0.60], [0.79, math.sqrt(1.0 - 0.79 * 0.79)]]
    for index in range(6):
        chunks.append(
            knowledge_chunk(
                "historical-{}".format(index),
                content="Distinct historical DIU admission evidence {}".format(index),
                currency_status="historical",
            )
        )
        embeddings.append([1.0, 0.0])
    store = _store()
    store.upsert_chunks(chunks, embeddings)
    retriever = Retriever(
        FakeEmbedder(),
        store,
        min_relevance_score=-1.0,
        candidate_multiplier=1,
        max_results_per_source=10,
    )

    results = retriever.retrieve(
        "DIU admission", top_k=2, include_historical=True
    )

    assert [result.chunk.chunk_id for result in results] == ["current", "stable"]


def test_create_retriever_rejects_mutable_pgvector_revision_before_io() -> None:
    settings = RagSettings(
        _env_file=None,
        database_url="postgresql://example.invalid/diu",
        embedding_model_name="example/custom-model",
        embedding_model_revision="main",
        embedding_dimension=3,
    )

    with pytest.raises(RuntimeError, match="40-character"):
        create_retriever(settings)


def test_safe_reruns_do_not_duplicate_and_remove_only_stale_document_chunks() -> None:
    first = knowledge_chunk("old-a", document_id="document-a")
    other = knowledge_chunk("keep-b", document_id="document-b")
    store = _store()

    initial = store.upsert_chunks([first, other], [[1.0, 0.0], [0.0, 1.0]])
    rerun = store.upsert_chunks([first, other], [[1.0, 0.0], [0.0, 1.0]])
    replacement = knowledge_chunk(
        "new-a",
        document_id="document-a",
        content="Replacement evidence for document A",
    )
    refreshed = store.upsert_chunks(
        [replacement],
        [[1.0, 0.0]],
        processed_document_ids={"document-a"},
    )

    assert initial.inserted_chunks == 2
    assert rerun.inserted_chunks == 0
    assert rerun.updated_chunks == 0
    assert rerun.total_chunks == 2
    assert refreshed.inserted_chunks == 1
    assert refreshed.deleted_stale_chunks == 1
    assert refreshed.total_chunks == 2
    matches = store.search([1.0, 0.0], top_k=10)
    assert {match.chunk.chunk_id for match in matches} == {"new-a", "keep-b"}


def test_result_contract_filters_threshold_and_out_of_domain_short_circuit() -> None:
    cse = knowledge_chunk(
        "cse-fees",
        source_id="DIU-FEE-001",
        content="CSE tuition fees and total program cost",
        category="tuition_and_fees",
        program="B. Sc. in Computer Science and Engineering",
    )
    bba = knowledge_chunk(
        "bba-documents",
        source_id="DIU-DOC-001",
        content="BBA admission document checklist",
        category="required_admission_documents",
        program="BBA",
    )
    store = _store()
    store.upsert_chunks([cse, bba], [[0.8, 0.6], [0.0, 1.0]])
    embedder = FakeEmbedder()
    retriever = Retriever(embedder, store, min_relevance_score=0.72)

    results = retriever.retrieve(
        "Tell me about CSE tuition",
        category="TUITION_AND_FEES",
        program="cse",
    )
    assert len(results) == 1
    result = results[0]
    serialized = result.to_dict()
    assert serialized["chunk_id"] == "cse-fees"
    assert serialized["content"] == cse.content
    assert serialized["title"] == cse.title
    assert serialized["category"] == "tuition_and_fees"
    assert serialized["program"] == "B. Sc. in Computer Science and Engineering"
    assert serialized["source_url"] == cse.source_url
    assert serialized["currency_status"] == "current_date_sensitive"
    assert isinstance(serialized["similarity_score"], float)
    assert isinstance(serialized["relevance_score"], float)
    assert -1.0 <= serialized["relevance_score"] <= 1.0

    assert retriever.retrieve(
        "Tell me about CSE tuition",
        category="tuition_and_fees",
        program="CSE",
        min_relevance_score=0.99,
    ) == []
    calls_before = len(embedder.queries)
    assert retriever.retrieve("BRAC University tuition") == []
    assert len(embedder.queries) == calls_before
    assert retriever.retrieve("random unrelated question") == []
    assert retriever.retrieve("What insurance documents are required?") == []
    assert len(embedder.queries) == calls_before
    assert retriever.retrieve("What programs are available?") == []
    assert retriever.retrieve(
        "DIU BBA admission documents",
        category="required_admission_documents",
    ) == []
    with pytest.raises(ValueError, match="finite number"):
        retriever.retrieve("DIU tuition", min_relevance_score=math.nan)
    assert len(embedder.queries) == calls_before + 4


def test_query_normalization_preserves_bangla_and_normalizes_spacing() -> None:
    normalized = normalize_query(
        "  ড্যাফোডিলে   ভর্তি হতে কী কী ডকুমেন্ট লাগবে?  "
    )

    assert normalized.startswith("ড্যাফোডিলে ভর্তি হতে কী কী ডকুমেন্ট লাগবে?")
    assert "ড্যাফোডিলে" in normalized
    assert "ভর্তি" in normalized
    assert "  " not in normalized


def _similarity_embedding(similarity: float) -> List[float]:
    return [similarity, math.sqrt(1.0 - similarity * similarity)]


def test_waiver_query_ranks_clean_table_chunks_above_messy_text_fragments() -> None:
    """A waiver-rate question must surface clean table chunks, not jumbled text.

    Regression for the demo fix: the waiver policy PDF is chunked into both
    reliable ``table`` extracts and raw ``text`` page fragments that start
    mid-table. Feeding those jumbled fragments to the small local LLM makes it
    refuse or hallucinate, so structured-data queries must prefer ``table``
    evidence regardless of raw cosine similarity.
    """
    messy_text = knowledge_chunk(
        "waiver-messy-text",
        source_id="DIU-WAV-001",
        content=(
            "GPA-5 in HSC 3.00 10% A levels 20% How to apply collect a waiver "
            "form from the admission office with photocopy of SSC and HSC transcript"
        ),
        category="waivers",
    )
    clean_table_sit = replace(
        knowledge_chunk(
            "waiver-clean-table-sit",
            source_id="DIU-WAV-001",
            content=(
                "Section: For the Faculty of SIT, BE, AHS and Engineering "
                "Golden GPA-5 both in SSC and in HSC | 50% | 3.25 "
                "GPA-5 both in SSC and in HSC | 25% | 3.00"
            ),
            category="waivers",
        ),
        content_type="table",
    )
    clean_table_hss = replace(
        knowledge_chunk(
            "waiver-clean-table-hss",
            source_id="DIU-WAV-001",
            content=(
                "Section: For the Faculty of Humanities and Social Sciences "
                "Golden GPA-5 both in SSC and in HSC | 50% | 3.25 "
                "GPA-5 in HSC | 20% | 3.00"
            ),
            category="waivers",
        ),
        content_type="table",
    )
    clean_table_cse = replace(
        knowledge_chunk(
            "waiver-clean-table-cse",
            source_id="DIU-WAV-001",
            content=(
                "Section: Waiver schemes for CSE and SWE program "
                "Golden GPA-5 both in SSC and in HSC | 40% | 3.25 "
                "GPA-5 both in SSC and in HSC | 15% | 3.00"
            ),
            category="waivers",
        ),
        content_type="table",
    )
    chunks = [messy_text, clean_table_sit, clean_table_hss, clean_table_cse]
    vectors = {
        messy_text.content: _similarity_embedding(0.90),
        clean_table_sit.content: _similarity_embedding(0.88),
        clean_table_hss.content: _similarity_embedding(0.87),
        clean_table_cse.content: _similarity_embedding(0.86),
    }
    store = _store()
    store.upsert_chunks(
        chunks,
        [vectors[chunk.content] for chunk in chunks],
    )
    retriever = Retriever(
        _ScoringEmbedder(vectors),
        store,
        min_relevance_score=-1.0,
        candidate_multiplier=2,
        max_results_per_source=10,
    )

    results = retriever.retrieve(
        "I got SSC GPA 5 and HSC GPA 5, what waiver can I get?", top_k=3
    )

    returned_ids = [result.chunk.chunk_id for result in results]
    assert returned_ids == [
        "waiver-clean-table-sit",
        "waiver-clean-table-hss",
        "waiver-clean-table-cse",
    ]
    assert "waiver-messy-text" not in returned_ids


def test_specific_waiver_focus_beats_generic_semantic_similarity() -> None:
    generic = knowledge_chunk(
        "generic-waiver",
        source_id="DIU-WAV-001",
        content="Official waiver policy and tuition fee waiver categories.",
        category="waivers",
    )
    female = replace(
        knowledge_chunk(
            "female-waiver",
            source_id="DIU-WAV-001",
            content="Female Quota tuition fee waiver for undergraduate programs.",
            category="waivers",
        ),
        content_type="table",
    )
    trailing_heading = knowledge_chunk(
        "trailing-aid-heading",
        source_id="DIU-WAV-001",
        content=(
            "General waiver application instructions and conditions that fill this "
            "overlapping chunk before the next section starts. c) Female Quota:"
        ),
        category="waivers",
    )
    store = InMemoryVectorStore(
        embedding_dimension=3,
        embedding_model_name="fixture-embedding",
    )
    store.upsert_chunks(
        [generic, female, trailing_heading],
        [
            [1.0, 0.0, 0.0],
            [0.0, 0.65, math.sqrt(1.0 - 0.65 * 0.65)],
            [0.0, 0.90, math.sqrt(1.0 - 0.90 * 0.90)],
        ],
    )
    retriever = Retriever(
        _AidFocusEmbedder(),
        store,
        candidate_multiplier=2,
        max_results_per_source=10,
    )

    results = retriever.retrieve("female waever", top_k=2)

    assert [result.chunk.chunk_id for result in results] == ["female-waiver"]
    assert results[0].similarity_score < retriever.min_similarity_score


def test_program_phrase_matcher_covers_existence_query_forms() -> None:
    from rag.retriever import _matched_program_phrase

    assert (
        _matched_program_phrase("Does DIU have BBA?")
        == "Bachelor of Business Administration"
    )
    assert _matched_program_phrase("Does DIU have a Bachelor of Business Administration?") == (
        "Bachelor of Business Administration"
    )
    assert _matched_program_phrase("Does DIU have Law?") == "LL.B."
    assert _matched_program_phrase("Does DIU have Pharmacy?") == "Bachelor of Pharmacy"
    assert _matched_program_phrase("Does DIU have Textile Engineering?") == (
        "Textile Engineering"
    )
    assert _matched_program_phrase("ডিআইইউতে বিবিএ আছে?") == "Bachelor of Business Administration"
    assert _matched_program_phrase("What documents are required?") is None
    assert _matched_program_phrase("How much is tuition?") is None


def test_short_existence_query_uses_program_phrase_lane() -> None:
    bba = knowledge_chunk(
        "bba-program",
        source_id="DIU-PROG-001",
        content=(
            "Full Program Name | Short Tag / Initials | Program Level | Faculty "
            "Bachelor of Business Administration (BBA) | BBA | Undergraduate | "
            "Business & Entrepreneurship"
        ),
        category="undergraduate_programs",
        program="Bachelor of Business Administration (BBA)",
    )
    waiver = knowledge_chunk(
        "waiver-general",
        source_id="DIU-WAV-001",
        content="Policy of Waiver and Scholarship general eligibility",
        category="waivers",
    )
    store = _store()
    store.upsert_chunks([bba, waiver], [[0.9, 0.1], [0.8, 0.2]])
    embedder = FakeEmbedder()
    retriever = Retriever(embedder, store, min_relevance_score=0.72)

    results = retriever.retrieve("Does DIU have BBA?", top_k=3)

    returned_ids = [result.chunk.chunk_id for result in results]
    assert "bba-program" in returned_ids
    assert "Bachelor of Business Administration" in embedder.queries


def test_unique_partial_program_subject_uses_canonical_program_lane() -> None:
    itm = knowledge_chunk(
        "itm-program",
        source_id="DIU-PROG-001",
        content=(
            "B.Sc. in Information Technology & Management (ITM) | ITM | "
            "Undergraduate | Science and Information Technology"
        ),
        category="undergraduate_programs",
        program="B.Sc. in Information Technology & Management (ITM)",
    )
    management = knowledge_chunk(
        "management-program",
        source_id="DIU-PROG-001",
        content="BBA in Management | Undergraduate | Business & Entrepreneurship",
        category="undergraduate_programs",
        program="BBA in Management",
    )
    store = _store()
    store.upsert_chunks([management, itm], [[1.0, 0.0], [1.0, 0.0]])
    embedder = FakeEmbedder()
    retriever = Retriever(embedder, store)

    results = retriever.retrieve("Information Technology", top_k=3)

    assert [result.chunk.chunk_id for result in results] == ["itm-program"]
    assert "Information Technology & Management" in embedder.queries


def test_domain_gate_accepts_program_phrase_and_gpa_apply_queries() -> None:
    """Program-naming and GPA/apply queries must pass the admission domain gate.

    Regression for the demo fix: ``what about bba?``, ``What about Law?`` and
    the LLB-GPA question used to be rejected (0 retrieval results) because the
    gate only recognized DIU names and a fixed term list.
    """

    from rag.retriever import is_likely_admission_query

    assert is_likely_admission_query("what about bba?")
    assert is_likely_admission_query("What about Law?")
    assert is_likely_admission_query("what is required gpa for applying for llb?")
    assert is_likely_admission_query("what GPA is needed to apply?")
    assert is_likely_admission_query("I am applying next month")
    assert not is_likely_admission_query("Tell me about the weather in Dhaka")
    assert not is_likely_admission_query("Best restaurants near Dhanmondi")


def test_program_phrase_queries_retrieve_after_gate_fix() -> None:
    """BBA and Law/LLB existence queries must now surface evidence.

    These queries previously short-circuited to empty results at the domain
    gate; the program-phrase lane must now be reachable for them. Admission-GPA
    questions are tested separately because a catalog row is not GPA evidence.
    """

    bba = knowledge_chunk(
        "bba-program",
        source_id="DIU-PROG-001",
        content=(
            "Full Program Name | Short Tag / Initials | Program Level | Faculty "
            "Bachelor of Business Administration (BBA) | BBA | Undergraduate | "
            "Business & Entrepreneurship"
        ),
        category="undergraduate_programs",
        program="Bachelor of Business Administration (BBA)",
    )
    llb = knowledge_chunk(
        "llb-program",
        source_id="DIU-PROG-001",
        content=(
            "Full Program Name | Short Tag / Initials | Program Level | Faculty "
            "LL.B. (Hons.) | LL.B. | Undergraduate | Humanities & Social Science"
        ),
        category="undergraduate_programs",
        program="LL.B. (Hons.)",
    )
    admission = knowledge_chunk(
        "admission-form",
        source_id="DIU-APP-001",
        content=(
            "Online Admission Form: minimum SSC and HSC GPA requirements "
            "for applying to DIU programs."
        ),
        category="admission_application_process",
    )
    waiver = knowledge_chunk(
        "waiver-general",
        source_id="DIU-WAV-001",
        content="Policy of Waiver and Scholarship general eligibility",
        category="waivers",
    )
    store = _store()
    store.upsert_chunks(
        [bba, llb, admission, waiver],
        [[1.0, 0.0]] * 4,
    )
    embedder = FakeEmbedder()
    retriever = Retriever(embedder, store)

    cases = {
        "what about bba?": "bba-program",
        "What about Law?": "llb-program",
    }
    for query, expected_chunk_id in cases.items():
        results = retriever.retrieve(query, top_k=4)
        returned_ids = [result.chunk.chunk_id for result in results]
        assert returned_ids, "expected non-empty retrieval for {!r}".format(query)
        assert expected_chunk_id in returned_ids, (
            "expected {!r} for {!r}, got {}".format(
                expected_chunk_id, query, returned_ids
            )
        )


def test_program_catalog_query_is_neutral_and_balanced() -> None:
    """The program-list lane must not bias toward postgraduate programs.

    Regression for the demo fix: the old catalog query contained the words
    ``undergraduate and postgraduate``, which made the embedding surface only
    PGD/Master chunks for ``Show available programs``.
    """

    from rag.retriever import _PROGRAM_CATALOG_QUERY

    lowered = _PROGRAM_CATALOG_QUERY.casefold()
    assert "postgraduate" not in lowered
    assert "undergraduate" not in lowered
    assert "graduate" not in lowered

    overview = knowledge_chunk(
        "programs-overview",
        source_id="DIU-PROG-001",
        content=(
            "Programs: DIU offers 51 undergraduate and graduate programs "
            "across its six faculties. Browse the full program catalog."
        ),
        category="undergraduate_programs",
    )
    cse = knowledge_chunk(
        "cse-program",
        source_id="DIU-PROG-001",
        content=(
            "Full Program Name | Short Tag / Initials | Program Level | Faculty "
            "B. Sc. in Computer Science and Engineering | CSE | Undergraduate | "
            "Science and Information Technology"
        ),
        category="undergraduate_programs",
        program="B. Sc. in Computer Science and Engineering",
    )
    mds = knowledge_chunk(
        "mds-program",
        source_id="DIU-PROG-001",
        content=(
            "Full Program Name | Short Tag / Initials | Program Level | Faculty "
            "Master of Development Studies (MDS) | MDS | Postgraduate | "
            "Business & Entrepreneurship"
        ),
        category="undergraduate_programs",
        program="Master of Development Studies (MDS)",
    )
    waiver = knowledge_chunk(
        "waiver-general",
        source_id="DIU-WAV-001",
        content="Policy of Waiver and Scholarship general eligibility",
        category="waivers",
    )
    vectors = {
        overview.content: _similarity_embedding(0.95),
        cse.content: _similarity_embedding(0.85),
        mds.content: _similarity_embedding(0.80),
        waiver.content: _similarity_embedding(0.60),
    }
    store = _store()
    store.upsert_chunks(
        [overview, cse, mds, waiver],
        [vectors[chunk.content] for chunk in [overview, cse, mds, waiver]],
    )
    retriever = Retriever(_ScoringEmbedder(vectors), store, max_results_per_source=5)

    results = retriever.retrieve("Show available programs", top_k=3)

    returned_ids = [result.chunk.chunk_id for result in results]
    assert returned_ids[0] == "programs-overview"
    assert "cse-program" in returned_ids
    assert "mds-program" in returned_ids
    assert "waiver-general" not in returned_ids


def test_specific_catalog_phrase_wins_over_broader_program_marker() -> None:
    assert _matched_program_phrase("Tell me about BBA in Finance & Banking") == (
        "BBA in Finance & Banking"
    )
    assert _matched_program_phrase("Does DIU offer Civil Engineering?") == (
        "Civil Engineering"
    )
    assert _matched_program_phrase("Compare CSE or SWE") is None
    assert _chunk_program_matches("Bachelor of Business Administration (BBA)", "bba")
    assert not _chunk_program_matches("BBA in Accounting", "bba")
    assert not _program_level_matches(
        "Does DIU offer Civil Engineering?",
        "B.Sc. in Civil Engineering (Diploma Holder)",
        "ce",
    )
    analysis = analyze_query(
        "Which faculty is it under. Program: Bachelor of Business Administration."
    )
    assert analysis.intent is QueryIntent.PROGRAM_INFO


def test_program_list_with_named_faculty_returns_only_that_faculty_rows() -> None:
    business_rows = [
        replace(
            replace(
                knowledge_chunk(
                    "bba-program",
                    source_id="DIU-PROG-001",
                    content="Bachelor of Business Administration (BBA) | Business & Entrepreneurship",
                    category="undergraduate_programs",
                    program="Bachelor of Business Administration (BBA)",
                ),
                faculty="Business & Entrepreneurship",
            ),
            content_type="table",
        ),
        replace(
            replace(
                knowledge_chunk(
                    "finance-program",
                    source_id="DIU-PROG-001",
                    content="BBA in Finance & Banking | Business & Entrepreneurship",
                    category="undergraduate_programs",
                    program="BBA in Finance & Banking",
                ),
                faculty="Business & Entrepreneurship",
            ),
            content_type="table",
        ),
    ]
    engineering = replace(
        replace(
            knowledge_chunk(
                "civil-program",
                source_id="DIU-PROG-001",
                content="B.Sc. in Civil Engineering (CE) | Engineering",
                category="undergraduate_programs",
                program="B.Sc. in Civil Engineering (CE)",
            ),
            faculty="Engineering",
        ),
        content_type="table",
    )
    overview = knowledge_chunk(
        "program-overview",
        source_id="DIU-PROG-001",
        content="Browse the complete DIU program catalog across all faculties",
        category="undergraduate_programs",
    )
    chunks = [*business_rows, engineering, overview]
    store = _store()
    store.upsert_chunks(
        chunks,
        [
            [1.0, 0.0],
            [0.70, math.sqrt(1.0 - 0.70**2)],
            [1.0, 0.0],
            [1.0, 0.0],
        ],
    )
    retriever = Retriever(FakeEmbedder(), store, max_results_per_source=5)

    results = retriever.retrieve("Which business programs does DIU offer?", top_k=5)

    assert {result.chunk.chunk_id for result in results} == {
        "bba-program",
        "finance-program",
    }


def test_faculty_acronym_department_query_filters_catalog_rows() -> None:
    fsit = replace(
        replace(
            knowledge_chunk(
                "cse-program",
                source_id="DIU-PROG-001",
                content="B. Sc. in Computer Science and Engineering | Science and Information Technology",
                category="undergraduate_programs",
                program="B. Sc. in Computer Science and Engineering",
            ),
            faculty="Science and Information Technology",
        ),
        content_type="table",
    )
    business = replace(
        replace(
            knowledge_chunk(
                "bba-program",
                source_id="DIU-PROG-001",
                content="Bachelor of Business Administration | Business & Entrepreneurship",
                category="undergraduate_programs",
                program="Bachelor of Business Administration",
            ),
            faculty="Business & Entrepreneurship",
        ),
        content_type="table",
    )
    store = _store()
    store.upsert_chunks([fsit, business], [[1.0, 0.0], [1.0, 0.0]])
    retriever = Retriever(FakeEmbedder(), store, max_results_per_source=5)

    results = retriever.retrieve("fsit department", top_k=5)

    assert [result.chunk.chunk_id for result in results] == ["cse-program"]


@pytest.mark.parametrize(
    ("query", "expected_ids"),
    [
        ("Agriculture Sciences", {"agriculture-program"}),
        ("Business & Entrepreneurship", {"business-program"}),
        ("Engineering", {"engineering-program"}),
        (
            "Graduate Studies",
            {"development-studies-program", "graduate-law-program"},
        ),
        ("Health and Life Sciences", {"health-program"}),
        ("Humanities & Social Sciences", {"humanities-program"}),
        ("Science and Information Technology", {"fsit-program"}),
        (
            "Which programs are in Graduate Studies?",
            {"development-studies-program", "graduate-law-program"},
        ),
    ],
)
def test_bare_and_natural_faculty_queries_filter_every_catalog_faculty(
    query: str, expected_ids: set[str]
) -> None:
    rows = [
        ("agriculture-program", "B.Sc. in Agricultural Science", "Agriculture Sciences"),
        (
            "business-program",
            "Bachelor of Business Administration",
            "Business & Entrepreneurship",
        ),
        ("engineering-program", "B.Sc. in Civil Engineering", "Engineering"),
        (
            "development-studies-program",
            "Master of Development Studies",
            "Graduate Studies",
        ),
        ("graduate-law-program", "Master of Law", "Graduate Studies"),
        ("health-program", "Bachelor of Pharmacy", "Health and Life Sciences"),
        (
            "humanities-program",
            "B.A. in English",
            "Humanities & Social Sciences",
        ),
        (
            "fsit-program",
            "B.Sc. in Computer Science and Engineering",
            "Science and Information Technology",
        ),
    ]
    chunks = [
        replace(
            replace(
                knowledge_chunk(
                    chunk_id,
                    source_id="DIU-PROG-001",
                    content=f"{program} | {faculty}",
                    category="undergraduate_programs",
                    program=program,
                ),
                faculty=faculty,
            ),
            content_type="table",
        )
        for chunk_id, program, faculty in rows
    ]
    store = _store()
    store.upsert_chunks(chunks, [[1.0, 0.0] for _chunk in chunks])
    retriever = Retriever(FakeEmbedder(), store, max_results_per_source=10)

    results = retriever.retrieve(query, top_k=10)

    assert {result.chunk.chunk_id for result in results} == expected_ids


def test_embedding_outage_uses_authoritative_lexical_faculty_catalog_fallback() -> None:
    rows = [
        (
            "graduate-digital-education",
            "Master of Teaching in Digital Education",
            "Graduate Studies",
        ),
        (
            "graduate-postgraduate-diploma",
            "Postgraduate Diploma of Teaching in Digital Education",
            "Graduate Studies",
        ),
        (
            "engineering-civil",
            "B.Sc. in Civil Engineering",
            "Engineering",
        ),
    ]
    chunks = [
        replace(
            replace(
                knowledge_chunk(
                    chunk_id,
                    source_id="DIU-PROG-001",
                    content=f"{program} | {faculty}",
                    category="undergraduate_programs",
                    program=program,
                ),
                faculty=faculty,
            ),
            content_type="table",
        )
        for chunk_id, program, faculty in rows
    ]
    store = _store()
    store.upsert_chunks(chunks, [[1.0, 0.0] for _chunk in chunks])
    retriever = Retriever(
        _UnavailableEmbedder(),
        store,
        max_results_per_source=10,
    )

    results = retriever.retrieve("Graduate Studies", top_k=10)

    assert {result.chunk.chunk_id for result in results} == {
        "graduate-digital-education",
        "graduate-postgraduate-diploma",
    }
    assert all(result.similarity_score == 1.0 for result in results)


def test_embedding_outage_preserves_exact_program_and_topic_compatibility() -> None:
    itm = replace(
        knowledge_chunk(
            "itm-program",
            source_id="DIU-PROG-001",
            content=(
                "B.Sc. in Information Technology & Management (ITM) | "
                "Science and Information Technology"
            ),
            category="undergraduate_programs",
            program="B.Sc. in Information Technology & Management (ITM)",
        ),
        faculty="Science and Information Technology",
        content_type="table",
    )
    civil = replace(
        knowledge_chunk(
            "civil-program",
            source_id="DIU-PROG-001",
            content="B.Sc. in Civil Engineering | Engineering",
            category="undergraduate_programs",
            program="B.Sc. in Civil Engineering",
        ),
        faculty="Engineering",
        content_type="table",
    )
    insurance = replace(
        knowledge_chunk(
            "life-insurance",
            source_id="DIU-LIFE-001",
            content="Verified DIU student life insurance information.",
            category="life_insurance",
        ),
        title="Life Insurance",
    )
    store = _store()
    store.upsert_chunks([itm, civil, insurance], [[1.0, 0.0]] * 3)
    retriever = Retriever(
        _UnavailableEmbedder(),
        store,
        max_results_per_source=10,
    )

    itm_results = retriever.retrieve("Information Technology", top_k=5)
    insurance_results = retriever.retrieve("life insurance", top_k=5)

    assert [result.chunk.chunk_id for result in itm_results] == ["itm-program"]
    assert [result.chunk.chunk_id for result in insurance_results] == [
        "life-insurance"
    ]
    assert retriever.retrieve("random unrelated question", top_k=5) == []


def test_bdt_tuition_query_excludes_usd_and_program_catalog_evidence() -> None:
    """Explicit BDT requests must return only matching local fee evidence."""

    cse_program = replace(
        knowledge_chunk(
            "cse-program",
            source_id="DIU-PROG-001",
            content="B. Sc. in Computer Science and Engineering | CSE | Undergraduate",
            category="undergraduate_programs",
            program="B. Sc. in Computer Science and Engineering",
        ),
        content_type="table",
    )
    cse_usd = replace(
        knowledge_chunk(
            "cse-usd",
            source_id="DIU-FEE-002",
            content=(
                "Tuition Fees for International Students | B. Sc. in Computer "
                "Science and Engineering | Total Tuition Fees | $ 7,847"
            ),
            category="international_admission",
            program="B. Sc. in Computer Science and Engineering",
        ),
        content_type="table",
    )
    cse_bdt = replace(
        knowledge_chunk(
            "cse-bdt",
            source_id="DIU-FEE-001",
            content=(
                "Tuition Fees for Local Students | B. Sc. in Computer Science "
                "and Engineering | Total Tuition Fees | 782,250"
            ),
            category="tuition_and_fees",
            program="B. Sc. in Computer Science and Engineering",
        ),
        content_type="table",
    )
    store = _store()
    store.upsert_chunks(
        [cse_program, cse_usd, cse_bdt],
        [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
    )
    retriever = Retriever(FakeEmbedder(), store, min_relevance_score=0.72)

    results = retriever.retrieve("What is the tuition fee of CSE in BDT?", top_k=5)

    assert [result.chunk.chunk_id for result in results] == ["cse-bdt"]
    assert "$" not in results[0].chunk.content


def test_mixed_local_and_international_tuition_returns_both_exact_rows() -> None:
    """A comparison request must retain both currencies and one exact program."""

    program = "B. Sc. in Computer Science and Engineering"
    local = replace(
        knowledge_chunk(
            "cse-local-mixed",
            source_id="DIU-FEE-001",
            content=(
                "Full Program Name | Total Tuition Fees | Total Program Fees\n"
                f"{program} | 782,250 | 1,020,450"
            ),
            category="tuition_and_fees",
            program=program,
        ),
        content_type="table",
    )
    international = replace(
        knowledge_chunk(
            "cse-international-mixed",
            source_id="DIU-FEE-002",
            content=(
                "Full Program Name | Total Tuition Fees | Total Program Fees\n"
                f"{program} | $ 7,847 | $ 10,250"
            ),
            category="international_admission",
            program=program,
        ),
        content_type="table",
    )
    store = _store()
    store.upsert_chunks([local, international], [[1.0, 0.0], [1.0, 0.0]])
    retriever = Retriever(FakeEmbedder(), store, min_relevance_score=0.72)

    results = retriever.retrieve(
        "Compare local and international CSE tuition fees", top_k=5
    )

    assert {result.chunk.chunk_id for result in results} == {
        "cse-local-mixed",
        "cse-international-mixed",
    }


def test_explicit_international_tuition_in_bdt_does_not_leak_local_row() -> None:
    program = "B. Sc. in Computer Science and Engineering"
    local = replace(
        knowledge_chunk(
            "cse-local-currency-conflict",
            content="CSE | Total Tuition Fees | 782,250",
            category="tuition_and_fees",
            program=program,
        ),
        content_type="table",
    )
    international = replace(
        knowledge_chunk(
            "cse-international-currency-conflict",
            content="CSE | Total Tuition Fees | $ 7,847",
            category="international_admission",
            program=program,
        ),
        content_type="table",
    )
    store = _store()
    store.upsert_chunks([local, international], [[1.0, 0.0], [1.0, 0.0]])
    retriever = Retriever(FakeEmbedder(), store, min_relevance_score=0.72)

    results = retriever.retrieve(
        "International CSE tuition fees in BDT", top_k=5
    )

    assert [result.chunk.chunk_id for result in results] == [
        "cse-international-currency-conflict"
    ]


def test_program_specific_tuition_does_not_fall_back_to_another_program() -> None:
    bba_program = replace(
        knowledge_chunk(
            "bba-program",
            source_id="DIU-PROG-001",
            content="Bachelor of Business Administration (BBA) | Undergraduate",
            category="undergraduate_programs",
            program="Bachelor of Business Administration (BBA)",
        ),
        content_type="table",
    )
    cse_fee = replace(
        knowledge_chunk(
            "cse-fee",
            source_id="DIU-FEE-001",
            content="CSE | Total Tuition Fees | 782,250",
            category="tuition_and_fees",
            program="B. Sc. in Computer Science and Engineering",
        ),
        content_type="table",
    )
    store = _store()
    store.upsert_chunks([bba_program, cse_fee], [[1.0, 0.0], [1.0, 0.0]])
    retriever = Retriever(FakeEmbedder(), store, min_relevance_score=0.72)

    results = retriever.retrieve("What about BBA? Topic: tuition fee.", top_k=5)

    assert results == []


@pytest.mark.parametrize(
    ("query", "expected_phrase"),
    [
        (
            "Information Technology and Management tuition fees",
            "Information Technology & Management",
        ),
        (
            "BBA in Finance and Banking tuition fees",
            "BBA in Finance & Banking",
        ),
        ("Development Studies tuition fees", "Master of Development Studies"),
        ("MA in English tuition fees", "M. A in English"),
        (
            "MSS in Journalism Media and Communication tuition fees",
            "MSS in Journalism, Media and Communication",
        ),
        ("M.A. in English tuition fees", "M. A in English"),
        ("M. A. in English tuition fees", "M. A in English"),
        ("M Pharm tuition fees", "Master of Pharmacy"),
        ("M. Pharm. tuition fees", "Master of Pharmacy"),
        ("Master of Pharmacy tuition fees", "Master of Pharmacy"),
    ],
)
def test_specific_program_resolution_normalizes_variants_and_beats_broad_markers(
    query: str, expected_phrase: str
) -> None:
    assert _matched_program_phrase(query) == expected_phrase
    assert len(_named_program_markers(query)) == 1
    assert _single_named_program_acronym(query) is not None


@pytest.mark.parametrize(
    ("query", "expected_program", "distractor_program"),
    [
        (
            "Information Technology and Management tuition fees",
            "B.Sc. in Information Technology & Management (ITM)",
            "BBA in Management",
        ),
        (
            "BBA in Finance and Banking tuition fees",
            "BBA in Finance & Banking",
            "Bachelor of Business Administration (BBA)",
        ),
        (
            "Development Studies tuition fees",
            "Master of Development Studies (MDS)",
            "Bachelor of Business Administration (BBA)",
        ),
        (
            "MA in English tuition fees",
            "M. A in English",
            "B.A. (Hons) in English",
        ),
        (
            "MSS in Journalism Media and Communication tuition fees",
            "MSS in Journalism, Media and Communication (JMC)",
            "BSS in Journalism, Media and Communication (JMC)",
        ),
    ],
)
def test_program_specific_tuition_compatibility_beats_semantic_similarity(
    query: str, expected_program: str, distractor_program: str
) -> None:
    target = replace(
        knowledge_chunk(
            "target-fee",
            source_id="DIU-FEE-001",
            content="{} | local tuition table row".format(expected_program),
            category="tuition_and_fees",
            program=expected_program,
        ),
        content_type="table",
    )
    distractor = replace(
        knowledge_chunk(
            "distractor-fee",
            source_id="DIU-FEE-001",
            content="{} | semantically stronger local tuition row".format(
                distractor_program
            ),
            category="tuition_and_fees",
            program=distractor_program,
        ),
        content_type="table",
    )
    vectors = {
        target.content: _similarity_embedding(0.80),
        distractor.content: _similarity_embedding(0.99),
    }
    store = _store()
    store.upsert_chunks(
        [target, distractor],
        [vectors[target.content], vectors[distractor.content]],
    )
    retriever = Retriever(
        _ScoringEmbedder(vectors),
        store,
        candidate_multiplier=10,
        max_results_per_source=10,
    )

    results = retriever.retrieve(query, top_k=5)

    assert [result.chunk.program for result in results] == [expected_program]


def test_program_name_lane_searches_tuition_category_before_small_top_k_cutoff() -> None:
    distractors = [
        knowledge_chunk(
            f"distractor-{index}",
            content=f"Software Engineering general document {index}",
            category="admission_overview",
        )
        for index in range(5)
    ]
    fee = replace(
        knowledge_chunk(
            "swe-fee",
            source_id="DIU-FEE-001",
            content="B. Sc. in Software Engineering (SWE) | local tuition table row",
            category="tuition_and_fees",
            program="B. Sc. in Software Engineering (SWE)",
        ),
        content_type="table",
    )
    store = _store()
    store.upsert_chunks([*distractors, fee], [[1.0, 0.0]] * 6)
    retriever = Retriever(
        FakeEmbedder(),
        store,
        candidate_multiplier=1,
        max_results_per_source=10,
    )

    results = retriever.retrieve("SWE tuition fees", top_k=1)

    assert [result.chunk.chunk_id for result in results] == ["swe-fee"]


def test_specific_full_name_gets_raw_lane_even_when_broad_alias_matches() -> None:
    target_program = "B.Sc. in Software Engineering (Major in Data Science)"
    target = replace(
        knowledge_chunk(
            "swe-data-science-fee",
            source_id="DIU-FEE-001",
            content=f"{target_program} | local tuition row",
            category="tuition_and_fees",
            program=target_program,
        ),
        content_type="table",
    )
    base = replace(
        knowledge_chunk(
            "swe-base-fee",
            source_id="DIU-FEE-001",
            content="B. Sc. in Software Engineering (SWE) | local tuition row",
            category="tuition_and_fees",
            program="B. Sc. in Software Engineering (SWE)",
        ),
        content_type="table",
    )

    class QueryAwareEmbedder(FakeEmbedder):
        def embed_query(self, query: str) -> List[float]:
            self.queries.append(query)
            if "major in data science" in normalize_query(query):
                return [0.0, 1.0]
            return [1.0, 0.0]

    store = _store()
    store.upsert_chunks([target, base], [[0.0, 1.0], [1.0, 0.0]])
    embedder = QueryAwareEmbedder()
    retriever = Retriever(
        embedder,
        store,
        candidate_multiplier=1,
        max_results_per_source=10,
    )

    results = retriever.retrieve(
        "B.Sc. in Software Engineering (Major in Data Science) tuition fees",
        top_k=1,
    )

    assert [result.chunk.program for result in results] == [target_program]
    assert any("major in data science" in query for query in embedder.queries)


def test_multiple_program_markers_keep_independent_mentions_of_different_lengths() -> None:
    assert _named_program_markers(
        "Compare CSE and Master of Pharmacy tuition fees"
    ) == ["cse", "mpharm"]


def test_broad_alias_inside_specific_program_is_not_returned_as_second_program() -> None:
    assert _named_program_markers(
        "Information Technology and Management tuition fees"
    ) == ["itm"]


def test_exact_catalog_compatibility_can_select_base_program_below_semantic_threshold() -> None:
    base = replace(
        knowledge_chunk(
            "swe-base-fee",
            source_id="DIU-FEE-001",
            content="B. Sc. in Software Engineering (SWE) | local tuition table row",
            category="tuition_and_fees",
            program="B. Sc. in Software Engineering (SWE)",
        ),
        content_type="table",
    )
    specialization = replace(
        knowledge_chunk(
            "swe-data-fee",
            source_id="DIU-FEE-001",
            content="B.Sc. in Software Engineering (Major in Data Science) | local tuition row",
            category="tuition_and_fees",
            program="B.Sc. in Software Engineering (Major in Data Science)",
        ),
        content_type="table",
    )
    vectors = {
        base.content: _similarity_embedding(0.70),
        specialization.content: _similarity_embedding(0.99),
    }
    store = _store()
    store.upsert_chunks(
        [base, specialization],
        [vectors[base.content], vectors[specialization.content]],
    )
    retriever = Retriever(
        _ScoringEmbedder(vectors),
        store,
        candidate_multiplier=10,
        max_results_per_source=10,
    )

    results = retriever.retrieve("SWE tuition fees", top_k=1)

    assert [result.chunk.chunk_id for result in results] == ["swe-base-fee"]


@pytest.mark.parametrize(
    ("query", "target_program", "alias_distractor"),
    [
        (
            "DIU-BCU Dual Award (MPH), UK admission program details",
            "DIU-BCU Dual Award (MPH), UK",
            "Master of Public Health (MPH)",
        ),
        (
            "Postgraduate Diploma of Teaching in Digital Education admission program details",
            "Postgraduate Diploma of Teaching in Digital Education",
            "Master of Teaching in Digital Education",
        ),
    ],
)
def test_exact_catalog_name_beats_alias_embedded_inside_official_name(
    query: str,
    target_program: str,
    alias_distractor: str,
) -> None:
    target = replace(
        knowledge_chunk(
            "exact-catalog-target",
            source_id="DIU-PROG-001",
            content=f"{target_program} | Graduate Studies",
            category="undergraduate_programs",
            program=target_program,
        ),
        content_type="table",
        faculty="Graduate Studies",
    )
    distractor = replace(
        knowledge_chunk(
            "embedded-alias-distractor",
            source_id="DIU-PROG-001",
            content=f"{alias_distractor} | Health and Life Sciences",
            category="undergraduate_programs",
            program=alias_distractor,
        ),
        content_type="table",
        faculty="Health and Life Sciences",
    )
    vectors = {
        target.content: _similarity_embedding(0.70),
        distractor.content: _similarity_embedding(0.99),
    }
    store = _store()
    store.upsert_chunks(
        [target, distractor],
        [vectors[target.content], vectors[distractor.content]],
    )
    retriever = Retriever(
        _ScoringEmbedder(vectors),
        store,
        candidate_multiplier=10,
        max_results_per_source=10,
    )

    results = retriever.retrieve(query, top_k=1)

    assert [result.chunk.program for result in results] == [target_program]


@pytest.mark.parametrize(
    ("query", "expected_program", "rejected_program"),
    [
        ("English tuition fees", "B.A. (Hons) in English", "M. A in English"),
        ("MA in English tuition fees", "M. A in English", "B.A. (Hons) in English"),
        (
            "JMC tuition fees",
            "BSS in Journalism, Media and Communication (JMC)",
            "MSS in Journalism, Media and Communication (JMC)",
        ),
        (
            "MSS in Journalism Media and Communication tuition fees",
            "MSS in Journalism, Media and Communication (JMC)",
            "BSS in Journalism, Media and Communication (JMC)",
        ),
        (
            "Public Health tuition fees",
            "Bachelor of Public Health (BPH)",
            "Master of Public Health (MPH)",
        ),
        (
            "Master of Public Health tuition fees",
            "Master of Public Health (MPH)",
            "Bachelor of Public Health (BPH)",
        ),
        (
            "Pharmacy tuition fees",
            "Bachelor of Pharmacy (B. Pharm)",
            "Master of Pharmacy (M. Pharm.)",
        ),
        (
            "M. Pharm. tuition fees",
            "Master of Pharmacy (M. Pharm.)",
            "Bachelor of Pharmacy (B. Pharm)",
        ),
    ],
)
def test_explicit_degree_level_never_falls_back_across_undergraduate_and_postgraduate(
    query: str, expected_program: str, rejected_program: str
) -> None:
    marker = _single_named_program_acronym(query)
    assert marker is not None
    assert _chunk_program_matches(expected_program, marker)
    assert _program_level_matches(query, expected_program, marker)
    assert not (
        _chunk_program_matches(rejected_program, marker)
        and _program_level_matches(query, rejected_program, marker)
    )


def test_llb_admission_gpa_does_not_use_waiver_maintenance_gpa() -> None:
    llb_program = replace(
        knowledge_chunk(
            "llb-program",
            source_id="DIU-PROG-001",
            content="LL.B. (Hons.) | LAW | Undergraduate",
            category="undergraduate_programs",
            program="LL.B. (Hons.)",
        ),
        content_type="table",
    )
    llb_waiver = replace(
        knowledge_chunk(
            "llb-waiver",
            source_id="DIU-WAV-001",
            content=(
                "Waiver schemes for B.Pharm and LLB | Golden GPA-5 | "
                "20% waiver | SGPA 3.00"
            ),
            category="waivers",
        ),
        content_type="table",
    )
    store = _store()
    store.upsert_chunks([llb_program, llb_waiver], [[1.0, 0.0], [1.0, 0.0]])
    retriever = Retriever(FakeEmbedder(), store, min_relevance_score=0.72)

    results = retriever.retrieve("What GPA is required for LL.B.?", top_k=5)

    assert results == []


def test_admission_process_query_excludes_waiver_and_document_fragments() -> None:
    process = knowledge_chunk(
        "admission-process",
        source_id="DIU-APP-001",
        content="Apply online, complete the admission form, and submit it.",
        category="admission_process",
    )
    waiver = knowledge_chunk(
        "waiver-application",
        source_id="DIU-WAV-001",
        content="How to apply for a waiver at the admission office.",
        category="waivers",
    )
    documents = knowledge_chunk(
        "admission-documents",
        source_id="DIU-DOC-001",
        content="Documents to submit during admission.",
        category="required_admission_documents",
    )
    store = _store()
    store.upsert_chunks(
        [process, waiver, documents],
        [[0.8, 0.6], [1.0, 0.0], [0.9, math.sqrt(0.19)]],
    )
    retriever = Retriever(FakeEmbedder(), store, min_relevance_score=0.72)

    results = retriever.retrieve("What is the admission process?", top_k=5)

    assert [result.chunk.chunk_id for result in results] == ["admission-process"]


def test_undergraduate_document_query_excludes_master_and_diploma_checklists() -> None:
    bachelor = knowledge_chunk(
        "bachelor-documents",
        source_id="DIU-DOC-001",
        content="SSC and HSC documents for bachelor admission.",
        category="required_admission_documents",
        program="For Bachelor Program Students",
    )
    master = knowledge_chunk(
        "master-documents",
        source_id="DIU-DOC-001",
        content="SSC, HSC, and graduation documents for master admission.",
        category="required_admission_documents",
        program="For Master Program",
    )
    diploma = knowledge_chunk(
        "diploma-documents",
        source_id="DIU-DOC-001",
        content="SSC and diploma transcripts for bachelor admission.",
        category="required_admission_documents",
        program="For Bachelor Program (Diploma Holder) Students",
    )
    store = _store()
    store.upsert_chunks(
        [bachelor, master, diploma],
        [[0.8, 0.6], [1.0, 0.0], [0.9, math.sqrt(0.19)]],
    )
    retriever = Retriever(FakeEmbedder(), store, min_relevance_score=0.72)

    results = retriever.retrieve(
        "What documents are required for undergraduate admission?", top_k=5
    )

    assert [result.chunk.chunk_id for result in results] == ["bachelor-documents"]
