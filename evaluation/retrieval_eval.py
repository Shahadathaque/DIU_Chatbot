"""Offline retrieval evaluation for the DIU M5 baseline (M5-B).

Runs the production ``Retriever`` against the local knowledge base over the
held-out v1 question set, then computes deterministic ranking metrics
(Recall@K, Precision@K, MRR) against each question's ``gold_chunk_ids``.

In-domain (answer) questions are scored for ranking quality. Out-of-domain
(``expected_outcome == "refuse"``) questions are scored for correct rejection:
the domain gate should return no evidence. The two groups are reported
separately, per the M5 audit.

The output JSON is deterministic given the same dataset, index, and retriever.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from evaluation.metrics import (
    average_precision,
    mean,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.schema import EvalDataset, EvalQuestion, PROJECT_ROOT, load_eval_dataset
from rag.retriever import Retriever

RETRIEVAL_KS = (1, 3, 5, 10)
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "evaluation" / "v1"


class RetrievalEvalError(RuntimeError):
    """Raised when retrieval evaluation cannot run or save results."""


def _question_records(
    dataset: EvalDataset, retriever: Retriever, *, top_k: int, max_questions: Optional[int]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    in_domain: List[Dict[str, Any]] = []
    out_of_domain: List[Dict[str, Any]] = []
    budget = len(dataset.questions) if max_questions is None else max_questions
    for question in dataset.questions[:budget]:
        retrieved = retriever.retrieve(question.question, top_k=top_k)
        retrieved_ids = [result.chunk.chunk_id for result in retrieved]
        record: Dict[str, Any] = {
            "id": question.id,
            "language": question.language,
            "category": question.category,
            "expected_outcome": question.expected_outcome,
            "question": question.question,
            "gold_chunk_ids": list(question.gold_chunk_ids),
            "retrieved_chunk_ids": retrieved_ids,
            "retrieved_count": len(retrieved_ids),
        }
        if question.is_out_of_domain:
            record["rejected"] = len(retrieved_ids) == 0
            record["domain_adherence"] = 1.0 if record["rejected"] else 0.0
            out_of_domain.append(record)
        else:
            for k in RETRIEVAL_KS:
                record[f"recall@{k}"] = recall_at_k(retrieved_ids, question.gold_chunk_ids, k)
                record[f"precision@{k}"] = precision_at_k(
                    retrieved_ids, question.gold_chunk_ids, k
                )
            record["reciprocal_rank"] = reciprocal_rank(
                retrieved_ids, question.gold_chunk_ids
            )
            record["average_precision"] = average_precision(
                retrieved_ids, question.gold_chunk_ids
            )
            in_domain.append(record)
    return in_domain, out_of_domain


def _summarize_metrics(records: List[Dict[str, Any]]) -> Dict[str, float]:
    if not records:
        return {}
    summary: Dict[str, float] = {}
    for key in (
        "recall@1",
        "recall@3",
        "recall@5",
        "recall@10",
        "precision@1",
        "precision@3",
        "precision@5",
        "precision@10",
        "reciprocal_rank",
        "average_precision",
    ):
        summary[key] = round(mean(record[key] for record in records), 4)
    summary["mrr"] = summary["reciprocal_rank"]
    return summary


def _grouped_summaries(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    by_language: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        by_language.setdefault(record["language"], []).append(record)
    return {
        language: _summarize_metrics(group) for language, group in sorted(by_language.items())
    }


def _category_summaries(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        by_category.setdefault(record["category"], []).append(record)
    return {
        category: _summarize_metrics(group)
        for category, group in sorted(by_category.items())
    }


def run_retrieval_eval(
    dataset: Optional[EvalDataset] = None,
    retriever: Optional[Retriever] = None,
    *,
    top_k: int = 10,
    max_questions: Optional[int] = None,
    results_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run offline retrieval evaluation and write a deterministic JSON result.

    ``dataset`` defaults to the validated v1 dataset; ``retriever`` defaults to
    the environment-configured production retriever (local index). Both can be
    injected for tests so no model or index is required.
    """
    resolved_dataset = dataset or load_eval_dataset()
    resolved_retriever = retriever

    if resolved_retriever is None:
        from rag.retriever import create_retriever

        resolved_retriever = create_retriever()

    in_domain, out_of_domain = _question_records(
        resolved_dataset, resolved_retriever, top_k=top_k, max_questions=max_questions
    )

    store = getattr(resolved_retriever, "vector_store", None)
    chunk_count = None
    if store is not None and hasattr(store, "count"):
        try:
            chunk_count = store.count()
        except Exception:
            chunk_count = None

    payload: Dict[str, Any] = {
        "dataset": {
            "dataset_id": resolved_dataset.dataset_id,
            "version": resolved_dataset.version,
            "content_hash": resolved_dataset.content_hash,
        },
        "retriever": {
            "model_name": getattr(resolved_retriever.embedder, "model_name", None),
            "model_revision": getattr(resolved_retriever.embedder, "model_revision", None),
            "min_similarity_score": resolved_retriever.min_similarity_score,
            "min_relevance_score": resolved_retriever.min_relevance_score,
            "candidate_multiplier": resolved_retriever.candidate_multiplier,
            "max_results_per_source": resolved_retriever.max_results_per_source,
            "chunk_count": chunk_count,
        },
        "evaluation": {
            "top_k": top_k,
            "in_domain_count": len(in_domain),
            "out_of_domain_count": len(out_of_domain),
            "summary_in_domain": _summarize_metrics(in_domain),
            "summary_in_domain_by_language": _grouped_summaries(in_domain),
            "summary_in_domain_by_category": _category_summaries(in_domain),
            "out_of_domain": {
                "count": len(out_of_domain),
                "rejected_count": sum(1 for record in out_of_domain if record["rejected"]),
                "rejection_rate": round(
                    mean(record["domain_adherence"] for record in out_of_domain), 4
                ),
                "domain_adherence": round(
                    mean(record["domain_adherence"] for record in out_of_domain), 4
                ),
                "records": out_of_domain,
            },
        },
        "questions": in_domain,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": "diu-m5-retrieval-eval-v1",
    }

    resolved_dir = Path(results_dir or DEFAULT_RESULTS_DIR)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    target = Path(out_path or (resolved_dir / "retrieval.json"))
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


__all__ = ["DEFAULT_RESULTS_DIR", "RETRIEVAL_KS", "RetrievalEvalError", "run_retrieval_eval"]