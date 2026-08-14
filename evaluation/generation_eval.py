"""Generation evaluation for the DIU M5 baseline (M5-B).

Evaluates two conditions over the same held-out question set with the same
model and configuration:

- ``condition="base"``: the ``Generator`` is called directly with the question
  only (no retrieved evidence). ``prompt`` = ``build_plain_messages``.
- ``condition="rag"``: ``Retriever -> build_grounded_messages -> Generator``.
  ``prompt`` = the production ``ChatService.build_grounded_messages`` prompt.

Both conditions run at ``temperature=0.0`` so generation is greedy and
reproducible. In-domain (answer) questions are scored against their golden
answers with the deterministic ``evaluation.metrics``; out-of-domain questions
are scored for correct refusal. Eligibility questions are excluded here — they
are evaluated deterministically by ``eligibility_eval`` (the LLM never decides
eligibility).

This module does not modify ``ChatService`` production behavior: it only
reuses ``build_grounded_messages`` (and the production system prompt / refusal
templates) as the RAG-condition prompt builder.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.services.chat_service import (
    _INSUFFICIENT_ANSWER,
    _LANGUAGE_NAME,
    _SYSTEM_PROMPT,
    build_grounded_messages,
)
from evaluation.metrics import (
    Stopwatch,
    check_fabricated_citations,
    domain_adherence,
    format_latency_ms,
    groundedness,
    hallucination_ngram_rate,
    is_refusal,
    language_adherence,
    mean,
    normalized_exact_match,
    rouge_1,
    rouge_2,
    rouge_l,
    token_f1,
    verbatim_snippet_containment,
)
from evaluation.schema import EvalDataset, EvalQuestion, PROJECT_ROOT, load_eval_dataset

DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "evaluation" / "v1"
PROMPT_BASE_VERSION = "plain-messages-v1"
PROMPT_RAG_VERSION = "chat-service-build-grounded-messages-v1"

_IN_DOMAIN_CATEGORIES = frozenset(
    {
        "waivers",
        "tuition_and_fees",
        "international_admission",
        "undergraduate_programs",
        "scholarships",
        "required_admission_documents",
        "admission_overview",
        "admission_contact_information",
        "admission_process",
        "admission_application_process",
    }
)


class GenerationEvalError(RuntimeError):
    """Raised when generation evaluation cannot run or save results."""


def build_plain_messages(message: str, language: str) -> List[Dict[str, str]]:
    """Base-condition prompt: same system prompt as RAG, but NO evidence block.

    Keeps the system prompt and language instructions identical to the RAG
    condition so the only controlled variable is the supplied evidence.
    """
    user_content = (
        "Language: {language}\n\n"
        "Question: {question}\n\n"
        "Answer the question in the requested language. If you cannot answer "
        "from verified DIU information, say so explicitly."
    ).format(language=_LANGUAGE_NAME[language], question=message)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _refusal_text(language: str) -> str:
    return _INSUFFICIENT_ANSWER[language]


def _evidence_texts(results: Sequence[Any]) -> List[str]:
    return [result.chunk.content for result in results]


def _source_urls(results: Sequence[Any]) -> List[str]:
    return [result.chunk.source_url for result in results]


def _process_question(
    question: EvalQuestion,
    *,
    condition: str,
    retriever: Any,
    generator: Any,
    temperature: float,
    max_new_tokens: Optional[int],
    top_p: Optional[float],
    top_k: int,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": question.id,
        "language": question.language,
        "category": question.category,
        "expected_outcome": question.expected_outcome,
        "question": question.question,
    }

    if condition == "rag":
        with Stopwatch() as retrieval_timer:
            results = list(retriever.retrieve(question.question, top_k=top_k))
        record["retrieval_latency_ms"] = format_latency_ms(retrieval_timer.seconds)
        record["retrieved_chunk_ids"] = [result.chunk.chunk_id for result in results]
        if not results:
            prediction = _refusal_text(question.language)
            refused = True
            evidence_texts: List[str] = []
            allowed_urls: List[str] = []
            generation_latency = 0.0
        else:
            messages = build_grounded_messages(question.question, question.language, results)
            evidence_texts = _evidence_texts(results)
            allowed_urls = _source_urls(results)
            with Stopwatch() as generation_timer:
                prediction = generator.generate(
                    messages,
                    temperature=temperature,
                    max_new_tokens=max_new_tokens,
                    top_p=top_p,
                )
            generation_latency = generation_timer.seconds
            refused = is_refusal(prediction)
    elif condition == "base":
        messages = build_plain_messages(question.question, question.language)
        evidence_texts = []
        allowed_urls = []
        with Stopwatch() as generation_timer:
            prediction = generator.generate(
                messages,
                temperature=temperature,
                max_new_tokens=max_new_tokens,
                top_p=top_p,
            )
        generation_latency = generation_timer.seconds
        refused = is_refusal(prediction)
    else:
        raise GenerationEvalError(f"unknown generation condition {condition!r}")

    record["prediction"] = prediction
    record["refused"] = refused
    record["generation_latency_ms"] = format_latency_ms(generation_latency)
    record["total_latency_ms"] = round(
        record["generation_latency_ms"] + record.get("retrieval_latency_ms", 0.0), 3
    )
    record["prompt_version"] = (
        PROMPT_RAG_VERSION if condition == "rag" else PROMPT_BASE_VERSION
    )

    if question.category in _IN_DOMAIN_CATEGORIES:
        record.update(
            {
                "exact_match": normalized_exact_match(prediction, question.golden_answer),
                "token_f1": token_f1(prediction, question.golden_answer),
                "rouge_1": rouge_1(prediction, question.golden_answer),
                "rouge_2": rouge_2(prediction, question.golden_answer),
                "rouge_l": rouge_l(prediction, question.golden_answer),
                "verbatim_snippet_containment": verbatim_snippet_containment(
                    prediction, question.golden_answer
                ),
                "groundedness": groundedness(prediction, evidence_texts),
                "hallucination_ngram_rate": hallucination_ngram_rate(
                    prediction, evidence_texts
                ),
                "language_adherence": language_adherence(prediction, question.language),
                "domain_adherence": domain_adherence(expected_refuse=False, refused=refused),
            }
        )
        record["fabricated_citations"] = check_fabricated_citations(
            prediction, allowed_urls
        )
    else:
        record["domain_adherence"] = domain_adherence(expected_refuse=True, refused=refused)
        record["language_adherence"] = language_adherence(prediction, question.language)
        record["fabricated_citations"] = check_fabricated_citations(prediction, allowed_urls)

    return record


def _aggregate(
    in_domain: List[Dict[str, Any]], out_of_domain: List[Dict[str, Any]]
) -> Dict[str, Any]:
    metric_keys = (
        "exact_match",
        "token_f1",
        "rouge_1_f1",
        "rouge_2_f1",
        "rouge_l_f1",
        "verbatim_snippet_containment",
        "groundedness",
        "hallucination_ngram_rate",
        "language_adherence",
        "domain_adherence",
    )
    rouge_keys = {"rouge_1_f1": "rouge_1", "rouge_2_f1": "rouge_2", "rouge_l_f1": "rouge_l"}
    aggregates: Dict[str, float] = {}
    for key in metric_keys:
        values: List[float] = []
        for record in in_domain:
            if key in rouge_keys:
                value = record[rouge_keys[key]]["f1"]
            elif key in record:
                value = record[key]
            else:
                continue
            if isinstance(value, (int, float)):
                values.append(float(value))
        aggregates[key] = round(mean(values), 4)

    fabricated_questions = [
        record["id"]
        for record in in_domain
        if record.get("fabricated_citations", {}).get("fabricated_url_count", 0) > 0
    ]
    aggregates["fabricated_citation_question_count"] = len(fabricated_questions)

    aggregates["language_adherence_by_language"] = {
        language: round(
            mean(record["language_adherence"] for record in in_domain if record["language"] == language),
            4,
        )
        for language in ("en", "bn", "banglish")
        if any(record["language"] == language for record in in_domain)
    }
    aggregates["domain_adherence_by_language"] = {
        language: round(
            mean(record["domain_adherence"] for record in in_domain if record["language"] == language),
            4,
        )
        for language in ("en", "bn", "banglish")
        if any(record["language"] == language for record in in_domain)
    }

    refusal_count = sum(
        1 for record in out_of_domain if record["domain_adherence"] == 1.0
    )
    return {
        **aggregates,
        "in_domain_count": len(in_domain),
        "out_of_domain_count": len(out_of_domain),
        "out_of_domain_refusal_accuracy": round(
            refusal_count / len(out_of_domain), 4
        )
        if out_of_domain
        else 0.0,
        "fabricated_citation_question_ids": fabricated_questions,
    }


def run_generation_eval(
    dataset: Optional[EvalDataset] = None,
    retriever: Any = None,
    generator: Any = None,
    *,
    condition: str,
    temperature: float = 0.0,
    max_new_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: int = 5,
    max_questions: Optional[int] = None,
    results_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run one generation condition (base or rag) and save a JSON result.

    ``dataset`` defaults to the validated v1 dataset. ``retriever`` and
    ``generator`` must be provided (production objects from ``run_all``, or
    lightweight fakes for tests). ``temperature`` defaults to 0.0 so both
    conditions are greedy and reproducible.
    """
    if condition not in {"base", "rag"}:
        raise GenerationEvalError(
            f"unknown generation condition {condition!r}; expected 'base' or 'rag'"
        )
    if retriever is None and condition == "rag":
        raise GenerationEvalError("condition='rag' requires a retriever")
    if generator is None:
        raise GenerationEvalError("a generator is required")

    resolved_dataset = dataset or load_eval_dataset()
    in_domain_questions = [
        question
        for question in resolved_dataset.questions
        if question.category in _IN_DOMAIN_CATEGORIES
    ]
    out_of_domain_questions = [
        question
        for question in resolved_dataset.questions
        if question.is_out_of_domain
    ]

    if max_questions is not None:
        in_domain_questions = in_domain_questions[:max_questions]

    in_domain_records = [
        _process_question(
            question,
            condition=condition,
            retriever=retriever,
            generator=generator,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
            top_p=top_p,
            top_k=top_k,
        )
        for question in in_domain_questions
    ]
    out_of_domain_records = [
        _process_question(
            question,
            condition=condition,
            retriever=retriever,
            generator=generator,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
            top_p=top_p,
            top_k=top_k,
        )
        for question in out_of_domain_questions
    ]

    aggregates = _aggregate(in_domain_records, out_of_domain_records)
    payload: Dict[str, Any] = {
        "condition": condition,
        "dataset": {
            "dataset_id": resolved_dataset.dataset_id,
            "version": resolved_dataset.version,
            "content_hash": resolved_dataset.content_hash,
        },
        "generation": {
            "temperature": temperature,
            "max_new_tokens": max_new_tokens,
            "top_p": top_p,
            "top_k": top_k,
            "prompt_base_version": PROMPT_BASE_VERSION,
            "prompt_rag_version": PROMPT_RAG_VERSION,
            "prompt_used": PROMPT_RAG_VERSION if condition == "rag" else PROMPT_BASE_VERSION,
        },
        "model": {
            "name": getattr(generator, "model_name", None),
            "revision": getattr(generator, "model_revision", None),
        },
        "retriever": {
            "model_name": getattr(retriever, "embedder", None) and getattr(
                retriever.embedder, "model_name", None
            ),
            "model_revision": getattr(retriever, "embedder", None) and getattr(
                retriever.embedder, "model_revision", None
            ),
            "used": condition == "rag",
        },
        "aggregates": aggregates,
        "in_domain_records": in_domain_records,
        "out_of_domain_records": out_of_domain_records,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": "diu-m5-generation-eval-v1",
    }

    resolved_dir = Path(results_dir or DEFAULT_RESULTS_DIR)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    target = Path(
        out_path or (resolved_dir / ("condition_base.json" if condition == "base" else "condition_rag.json"))
    )
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


__all__ = [
    "DEFAULT_RESULTS_DIR",
    "GenerationEvalError",
    "PROMPT_BASE_VERSION",
    "PROMPT_RAG_VERSION",
    "build_plain_messages",
    "run_generation_eval",
]