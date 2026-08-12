from __future__ import annotations

from dataclasses import replace
import math
from typing import List, Sequence

import pytest

from rag.config import RagSettings
from rag.retriever import Retriever, create_retriever, normalize_query
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
    assert retriever.retrieve("What insurance documents are required?")
    assert retriever.retrieve("What programs are available?")
    assert retriever.retrieve(
        "DIU BBA admission documents",
        category="required_admission_documents",
    ) == []
    with pytest.raises(ValueError, match="finite number"):
        retriever.retrieve("DIU tuition", min_relevance_score=math.nan)
    assert len(embedder.queries) == calls_before + 3


def test_query_normalization_preserves_bangla_and_normalizes_spacing() -> None:
    normalized = normalize_query(
        "  ড্যাফোডিলে   ভর্তি হতে কী কী ডকুমেন্ট লাগবে?  "
    )

    assert normalized.startswith("ড্যাফোডিলে ভর্তি হতে কী কী ডকুমেন্ট লাগবে?")
    assert "ড্যাফোডিলে" in normalized
    assert "ভর্তি" in normalized
    assert "  " not in normalized
