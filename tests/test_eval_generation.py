"""Tests for the M5-B generation evaluation scaffolding.

Uses small deterministic fakes for the retriever and generator — no model is
downloaded and nothing touches the network.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import pytest

from evaluation.generation_eval import (
    PROMPT_BASE_VERSION,
    PROMPT_RAG_VERSION,
    build_plain_messages,
    run_generation_eval,
)
from evaluation.schema import EvalDataset, EvalQuestion
from tests.rag_helpers import knowledge_chunk


class FakeGenerator:
    model_name = "fake-generator"
    model_revision = "fake-rev"

    def __init__(self, response: str = "The CSE tuition fee is 100000 taka per semester.") -> None:
        self.response = response
        self.calls: List[Dict[str, Any]] = []
        self.kwargs: List[Dict[str, Any]] = []

    def generate(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        self.calls.append(list(messages))
        self.kwargs.append(
            {"max_new_tokens": max_new_tokens, "temperature": temperature, "top_p": top_p}
        )
        return self.response


class FakeRetriever:
    def __init__(self, chunk_id: Optional[str] = "gold-a") -> None:
        self.chunk_id = chunk_id
        self.chunk = None
        if chunk_id:
            self.chunk = knowledge_chunk(
                chunk_id,
                content="The CSE tuition fee is 100000 taka per semester.",
                category="tuition_and_fees",
            )

    def retrieve(self, query: str, top_k: int = 5) -> List[Any]:
        if self.chunk is None:
            return []
        return [type("Result", (), {"chunk": self.chunk})()]


def _question(
    question_id: str,
    *,
    category: str = "tuition_and_fees",
    expected_outcome: str = "answer",
    gold_chunk_ids: tuple = ("gold-a",),
    language: str = "en",
) -> EvalQuestion:
    return EvalQuestion(
        id=question_id,
        language=language,
        category=category,
        question="What is the CSE tuition fee?",
        golden_answer="The CSE tuition fee is 100000 taka per semester.",
        gold_chunk_ids=gold_chunk_ids,
        expected_outcome=expected_outcome,
        dataset_usage="held_out_eval",
        dataset_version="1.0.0",
    )


def _dataset(*questions: EvalQuestion) -> EvalDataset:
    return EvalDataset(
        dataset_id="test-eval",
        version="1.0.0",
        schema_version="1.0",
        purpose="held_out_evaluation",
        description="test",
        held_out=True,
        content_hash="test-hash",
        source_knowledge_base="data/chunks/local_knowledge_base.json",
        questions=tuple(questions),
    )


class TestBuildPlainMessages:
    def test_system_and_user_present(self):
        messages = build_plain_messages("What is the fee?", "en")
        assert [message["role"] for message in messages] == ["system", "user"]
        assert "Question: What is the fee?" in messages[1]["content"]
        assert "DIU evidence" not in messages[1]["content"]
        assert "Language: English" in messages[1]["content"]

    def test_no_evidence_block_any_language(self):
        for language in ("en", "bn", "banglish"):
            messages = build_plain_messages("কত?", language)
            assert "evidence" not in messages[1]["content"].casefold()


class TestRunGenerationEval:
    def test_base_condition_passes_temperature_and_prompt(self, tmp_path):
        dataset = _dataset(_question("q-in"))
        generator = FakeGenerator()
        payload = run_generation_eval(
            dataset,
            None,
            generator,
            condition="base",
            temperature=0.0,
            max_new_tokens=64,
            results_dir=tmp_path,
        )
        assert payload["condition"] == "base"
        assert payload["generation"]["temperature"] == 0.0
        assert payload["model"]["name"] == "fake-generator"
        assert generator.kwargs[0]["temperature"] == 0.0
        assert generator.kwargs[0]["max_new_tokens"] == 64
        assert payload["aggregates"]["in_domain_count"] == 1
        assert payload["aggregates"]["exact_match"] == 1.0
        assert payload["generation"]["prompt_used"] == PROMPT_BASE_VERSION
        assert (tmp_path / "condition_base.json").is_file()

    def test_rag_condition_uses_grounded_messages(self, tmp_path):
        dataset = _dataset(_question("q-in"))
        generator = FakeGenerator()
        retriever = FakeRetriever("gold-a")
        payload = run_generation_eval(
            dataset,
            retriever,
            generator,
            condition="rag",
            temperature=0.0,
            results_dir=tmp_path,
        )
        assert payload["condition"] == "rag"
        assert "DIU evidence" in generator.calls[0][1]["content"]
        assert payload["generation"]["prompt_used"] == PROMPT_RAG_VERSION
        assert payload["aggregates"]["groundedness"] == 1.0
        assert (tmp_path / "condition_rag.json").is_file()

    def test_rag_condition_refuses_when_no_evidence(self, tmp_path):
        dataset = _dataset(_question("q-ood", category="out_of_domain", expected_outcome="refuse"))
        generator = FakeGenerator()
        retriever = FakeRetriever(chunk_id=None)
        payload = run_generation_eval(
            dataset,
            retriever,
            generator,
            condition="rag",
            temperature=0.0,
            results_dir=tmp_path,
        )
        assert payload["aggregates"]["out_of_domain_refusal_accuracy"] == 1.0
        assert payload["out_of_domain_records"][0]["retrieved_chunk_ids"] == []

    def test_base_condition_requires_no_retriever(self, tmp_path):
        dataset = _dataset(_question("q-in"))
        payload = run_generation_eval(
            dataset, None, FakeGenerator(), condition="base", results_dir=tmp_path
        )
        assert payload["aggregates"]["groundedness"] == 0.0

    def test_unknown_condition_rejected(self, tmp_path):
        with pytest.raises(Exception, match="unknown generation condition"):
            run_generation_eval(
                _dataset(_question("q-in")),
                None,
                FakeGenerator(),
                condition="nope",
                results_dir=tmp_path,
            )

    def test_rag_condition_requires_retriever(self, tmp_path):
        with pytest.raises(Exception, match="requires a retriever"):
            run_generation_eval(
                _dataset(_question("q-in")), None, FakeGenerator(), condition="rag", results_dir=tmp_path
            )

    def test_language_adherence_recorded(self, tmp_path):
        dataset = _dataset(_question("q-in", language="bn"))
        payload = run_generation_eval(
            dataset,
            FakeRetriever("gold-a"),
            FakeGenerator(response="ভর্তি ফি ১০০০০০ টাকা।"),
            condition="rag",
            results_dir=tmp_path,
        )
        assert payload["aggregates"]["language_adherence"] == 1.0