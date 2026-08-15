"""Tests for the M5 held-out evaluation dataset schema (TASK-05A)."""

import json
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

from evaluation.schema import (
    ALLOWED_LANGUAGES,
    ALLOWED_OUTCOMES,
    DATASET_USAGE_HELDOUT,
    DEFAULT_DATASET_PATH,
    DEFAULT_KB_PATH,
    DEFAULT_MANIFEST_PATH,
    SYNTHETIC_DOCUMENT_ID,
    SYNTHETIC_SOURCE_ID,
    EvalDatasetError,
    assert_no_overlap_with_finetuning,
    compute_content_hash,
    load_eval_dataset,
    load_knowledge_base,
    normalize_question_text,
    question_hashes,
)


@pytest.fixture(scope="module")
def dataset():
    return load_eval_dataset(
        DEFAULT_DATASET_PATH,
        DEFAULT_KB_PATH,
        DEFAULT_MANIFEST_PATH,
    )


@pytest.fixture(scope="module")
def kb_chunks():
    return load_knowledge_base(DEFAULT_KB_PATH)


class TestDatasetMetadata:
    def test_dataset_id_and_version(self, dataset):
        assert dataset.dataset_id == "diu-m5-eval-questions"
        assert dataset.version == "1.0.0"
        assert dataset.schema_version
        assert dataset.purpose == "held_out_evaluation"
        assert dataset.held_out is True

    def test_all_questions_mark_held_out(self, dataset):
        assert all(q.dataset_usage == DATASET_USAGE_HELDOUT for q in dataset.questions)
        assert all(q.dataset_version == dataset.version for q in dataset.questions)

    def test_content_hash_is_deterministic(self):
        raw = json.loads(DEFAULT_DATASET_PATH.read_text(encoding="utf-8"))
        payload = dict(raw)
        stored = payload.pop("content_hash")
        assert compute_content_hash(payload) == stored
        assert compute_content_hash(payload) == compute_content_hash(payload)


class TestQuestionIds:
    def test_ids_are_unique(self, dataset):
        ids = [q.id for q in dataset.questions]
        assert len(ids) == len(set(ids))


class TestLanguages:
    def test_all_languages_present(self, dataset):
        languages = {q.language for q in dataset.questions}
        assert ALLOWED_LANGUAGES <= languages

    def test_languages_are_valid(self, dataset):
        assert all(q.language in ALLOWED_LANGUAGES for q in dataset.questions)


class TestCategories:
    def test_categories_are_valid(self, dataset, kb_chunks):
        kb_categories = {c["category"] for c in kb_chunks.values()}
        allowed = kb_categories | {"out_of_domain", "eligibility_real", "eligibility_synthetic"}
        assert all(q.category in allowed for q in dataset.questions)


class TestGoldChunks:
    def test_gold_chunks_exist_in_kb(self, dataset, kb_chunks):
        for q in dataset.questions:
            for cid in q.gold_chunk_ids:
                assert cid in kb_chunks, f"{q.id}: gold chunk {cid} missing"

    def test_gold_chunk_provenance_matches_question(self, dataset, kb_chunks):
        for q in dataset.questions:
            for cid in q.gold_chunk_ids:
                chunk = kb_chunks[cid]
                assert chunk["source_id"] == q.source_id, f"{q.id}: source mismatch"
                assert chunk["document_id"] == q.document_id, f"{q.id}: doc mismatch"

    def test_gold_chunks_are_default_eligible(self, dataset, kb_chunks):
        eligible_statuses = {"current_date_sensitive", "stable_reference"}
        for q in dataset.questions:
            for cid in q.gold_chunk_ids:
                chunk = kb_chunks[cid]
                assert chunk["currency_status"] in eligible_statuses, f"{q.id}: {cid}"
                assert chunk["extraction_status"] == "success", f"{q.id}: {cid}"
                assert not chunk.get("manual_review"), f"{q.id}: {cid}"


class TestDuplicateQuestions:
    def test_no_duplicate_question_text_per_language(self, dataset):
        seen = {}
        for q in dataset.questions:
            normalized = normalize_question_text(q.question)
            bucket = seen.setdefault(q.language, set())
            assert normalized not in bucket, f"duplicate in {q.language}: {q.question[:60]}"
            bucket.add(normalized)


class TestExpectedOutcomes:
    def test_outcomes_are_valid(self, dataset):
        assert all(q.expected_outcome in ALLOWED_OUTCOMES for q in dataset.questions)

    def test_in_domain_questions_answer(self, dataset):
        in_domain = [q for q in dataset.questions if q.category not in {
            "out_of_domain", "eligibility_real", "eligibility_synthetic"}]
        assert in_domain
        assert all(q.expected_outcome == "answer" for q in in_domain)

    def test_out_of_domain_questions_refuse(self, dataset):
        ood = [q for q in dataset.questions if q.category == "out_of_domain"]
        assert len(ood) >= 10
        assert all(q.expected_outcome == "refuse" for q in ood)
        assert all(not q.gold_chunk_ids for q in ood)
        assert all(not q.source_id for q in ood)

    def test_real_eligibility_is_insufficient_information(self, dataset):
        real = [q for q in dataset.questions if q.category == "eligibility_real"]
        assert 8 <= len(real) <= 12
        assert all(q.expected_outcome == "insufficient_information" for q in real)
        assert all(q.eligibility_input is not None for q in real)
        assert all(not q.gold_chunk_ids for q in real)
        assert all(not q.is_synthetic for q in real)

    def test_synthetic_eligibility_is_marked(self, dataset):
        syn = [q for q in dataset.questions if q.category == "eligibility_synthetic"]
        assert len(syn) >= 10
        assert all(q.is_synthetic for q in syn)
        assert all(q.source_id == SYNTHETIC_SOURCE_ID for q in syn)
        assert all(q.document_id == SYNTHETIC_DOCUMENT_ID for q in syn)
        assert all(q.fixture_rule is not None for q in syn)
        assert all(
            q.expected_outcome in {"eligible", "not_eligible", "insufficient_information"}
            for q in syn
        )
        assert all(not q.gold_chunk_ids for q in syn)


class TestAntiReuseMechanism:
    def test_question_hashes_are_stable(self, dataset):
        first = question_hashes(dataset)
        second = question_hashes(dataset)
        assert first == second
        assert len(first) == len(dataset.questions)

    def test_assert_no_overlap_passes_for_clean_questions(self, dataset):
        assert_no_overlap_with_finetuning(dataset, [
            "What is the deadline for Summer 2027 admission?",
            "তোমার নাম কী?",
        ])

    def test_assert_no_overlap_detects_collision(self, dataset):
        sample = dataset.by_id["en-01"]
        with pytest.raises(EvalDatasetError):
            assert_no_overlap_with_finetuning(dataset, [sample.question, "another"])


class TestFailureModes:
    def _write_minimal_dataset(self, tmp_path, questions, **overrides):
        payload = {
            "dataset_id": "test",
            "version": "1.0.0",
            "schema_version": "1.0",
            "purpose": "held_out_evaluation",
            "description": "test",
            "held_out": True,
            "dataset_usage": DATASET_USAGE_HELDOUT,
            "source_knowledge_base": "data/chunks/local_knowledge_base.json",
            "questions": questions,
        }
        payload.update(overrides)
        payload["content_hash"] = compute_content_hash(payload)
        path = tmp_path / "test.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _valid_question(self, **overrides):
        q = {
            "id": "en-xx", "language": "en", "category": "waivers",
            "source_id": "DIU-WAV-001",
            "document_id": "diu-wav-001-a10884cbbc986cc0",
            "source_url": "https://webbackend.daffodilvarsity.edu.bd/images/download/waiver-policy2025.pdf",
            "title": "Policy",
            "question": "What waiver do siblings get?",
            "golden_answer": "20% tuition fee waiver.",
            "gold_chunk_ids": ["diu-chunk-17aefe9555a940d32de9656c"],
            "expected_outcome": "answer",
            "dataset_usage": DATASET_USAGE_HELDOUT,
            "dataset_version": "1.0.0",
            "is_synthetic": False,
        }
        q.update(overrides)
        return q

    def test_rejects_unknown_language(self, tmp_path):
        path = self._write_minimal_dataset(
            tmp_path, [self._valid_question(language="fr")])
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_missing_gold_chunk(self, tmp_path):
        path = self._write_minimal_dataset(
            tmp_path, [self._valid_question(
                gold_chunk_ids=["diu-chunk-does-not-exist"])])
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_unknown_category(self, tmp_path):
        path = self._write_minimal_dataset(
            tmp_path, [self._valid_question(category="not_a_category")])
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_wrong_outcome_for_in_domain(self, tmp_path):
        path = self._write_minimal_dataset(
            tmp_path, [self._valid_question(expected_outcome="refuse")])
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_duplicate_ids(self, tmp_path):
        path = self._write_minimal_dataset(
            tmp_path, [self._valid_question(), self._valid_question()])
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_duplicate_question_text(self, tmp_path):
        q1 = self._valid_question()
        q2 = self._valid_question(id="en-yy", question="What waiver do siblings get?")
        path = self._write_minimal_dataset(tmp_path, [q1, q2])
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_tampered_hash(self, tmp_path):
        q = self._valid_question()
        path = self._write_minimal_dataset(tmp_path, [q])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["content_hash"] = "0" * 64
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_held_out_usage_not_marked(self, tmp_path):
        path = self._write_minimal_dataset(
            tmp_path, [self._valid_question()], held_out=False)
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)

    def test_rejects_synthetic_not_marked(self, tmp_path):
        q = self._valid_question(
            category="eligibility_synthetic",
            source_id=SYNTHETIC_SOURCE_ID,
            document_id=SYNTHETIC_DOCUMENT_ID,
            gold_chunk_ids=[],
            expected_outcome="eligible",
            fixture_rule={"type": "numeric_range", "field": "ssc_gpa", "min": 3.0},
            is_synthetic=False,
        )
        path = self._write_minimal_dataset(tmp_path, [q])
        with pytest.raises(EvalDatasetError):
            load_eval_dataset(path, DEFAULT_KB_PATH, DEFAULT_MANIFEST_PATH)


class TestDatasetFileIntegrity:
    def test_question_count_and_language_balance(self, dataset):
        in_domain = [q for q in dataset.questions if q.category not in {
            "out_of_domain", "eligibility_real", "eligibility_synthetic"}]
        per_lang = {}
        for q in in_domain:
            per_lang[q.language] = per_lang.get(q.language, 0) + 1
        # ~40 per language across the in-domain pool
        assert all(35 <= v <= 45 for v in per_lang.values())

    def test_file_is_valid_json(self):
        raw = json.loads(DEFAULT_DATASET_PATH.read_text(encoding="utf-8"))
        assert isinstance(raw["questions"], list)
        assert len(raw["questions"]) == 150
