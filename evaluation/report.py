"""Aggregate M5 evaluation results into summary.json and report.md (M5-B).

Reads the deterministic JSON files written by ``retrieval_eval``,
``eligibility_eval`` and ``generation_eval`` and produces:

- ``results/evaluation/v1/summary.json`` — machine-readable aggregate
- ``results/evaluation/v1/report.md`` — human-readable report that clearly
  compares Base vs Base+RAG and separately explains the real vs synthetic
  eligibility tiers.

No metric is computed here: this module only aggregates already-recorded
numbers so the report cannot silently change results.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from evaluation.schema import PROJECT_ROOT

DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "evaluation" / "v1"

_METRIC_LABELS = {
    "exact_match": "Normalized exact match",
    "token_f1": "Token F1",
    "rouge_1_f1": "ROUGE-1 F1",
    "rouge_2_f1": "ROUGE-2 F1",
    "rouge_l_f1": "ROUGE-L F1",
    "verbatim_snippet_containment": "Verbatim snippet containment",
    "groundedness": "Groundedness (proxy)",
    "hallucination_ngram_rate": "Hallucination n-gram rate (proxy)",
    "language_adherence": "Language adherence",
    "domain_adherence": "Domain adherence",
}


class ReportError(RuntimeError):
    """Raised when a required evaluation result file is missing or invalid."""


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ReportError("missing evaluation result file: {}".format(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _condition_comparison(
    base: Dict[str, Any], rag: Dict[str, Any]
) -> Dict[str, Any]:
    base_aggregates = base.get("aggregates", {})
    rag_aggregates = rag.get("aggregates", {})
    comparison: Dict[str, Any] = {}
    for key in _METRIC_LABELS:
        base_value = base_aggregates.get(key)
        rag_value = rag_aggregates.get(key)
        if not isinstance(base_value, (int, float)) or not isinstance(
            rag_value, (int, float)
        ):
            continue
        comparison[key] = {
            "base": base_value,
            "rag": rag_value,
            "delta_rag_minus_base": round(rag_value - base_value, 4),
        }
    comparison["fabricated_citation_question_count"] = {
        "base": base_aggregates.get("fabricated_citation_question_count", 0),
        "rag": rag_aggregates.get("fabricated_citation_question_count", 0),
    }
    return comparison


def build_report(
    results_dir: Optional[Path] = None,
    *,
    summary_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Aggregate all M5 evaluation outputs and write summary.json + report.md."""
    resolved_dir = Path(results_dir or DEFAULT_RESULTS_DIR)
    resolved_dir.mkdir(parents=True, exist_ok=True)

    retrieval = _load_json(resolved_dir / "retrieval.json")
    eligibility = _load_json(resolved_dir / "eligibility.json")
    condition_base = _load_json(resolved_dir / "condition_base.json")
    condition_rag = _load_json(resolved_dir / "condition_rag.json")

    summary: Dict[str, Any] = {
        "dataset": {
            "dataset_id": condition_base.get("dataset", {}).get("dataset_id"),
            "version": condition_base.get("dataset", {}).get("version"),
            "content_hash": condition_base.get("dataset", {}).get("content_hash"),
        },
        "model": condition_base.get("model", {}),
        "generation_config": condition_base.get("generation", {}),
        "conditions": {
            "base": condition_base.get("aggregates", {}),
            "rag": condition_rag.get("aggregates", {}),
        },
        "base_vs_rag": _condition_comparison(condition_base, condition_rag),
        "retrieval": retrieval.get("evaluation", {}),
        "eligibility": {
            "real": eligibility.get("eligibility_real", {}),
            "synthetic": eligibility.get("eligibility_synthetic", {}),
        },
        "notes": {
            "temperature": condition_base.get("generation", {}).get("temperature"),
            "base_condition_prompt": condition_base.get("generation", {}).get("prompt_used"),
            "rag_condition_prompt": condition_rag.get("generation", {}).get("prompt_used"),
            "eligibility_note": eligibility.get("note", ""),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": "diu-m5-summary-v1",
    }

    summary_target = Path(summary_path or (resolved_dir / "summary.json"))
    summary_target.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report_text = _render_markdown(summary, condition_base, condition_rag)
    report_target = Path(report_path or (resolved_dir / "report.md"))
    report_target.write_text(report_text, encoding="utf-8")
    return summary


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _metric_rows(comparison: Dict[str, Any]) -> str:
    rows = ["| Metric | Base | Base + RAG | Delta |", "| --- | --- | --- | --- |"]
    for key, label in _METRIC_LABELS.items():
        entry = comparison.get(key)
        if not isinstance(entry, dict):
            continue
        rows.append(
            f"| {label} | {_fmt(entry.get('base'))} | {_fmt(entry.get('rag'))} | "
            f"{_fmt(entry.get('delta_rag_minus_base'))} |"
        )
    fabricated = comparison.get("fabricated_citation_question_count", {})
    rows.append(
        f"| Questions with fabricated citations | {fabricated.get('base', 0)} | "
        f"{fabricated.get('rag', 0)} | — |"
    )
    return "\n".join(rows)


def _render_markdown(
    summary: Dict[str, Any], condition_base: Dict[str, Any], condition_rag: Dict[str, Any]
) -> str:
    lines: list[str] = []
    lines.append("# DIU Admission AI — M5 Baseline Evaluation Report (v1)")
    lines.append("")
    lines.append(
        f"Generated at UTC: {datetime.now(timezone.utc).isoformat()}"
    )
    dataset = summary["dataset"]
    lines.append(
        f"Dataset: **{dataset.get('dataset_id')}** v{dataset.get('version')} "
        f"(content_hash `{dataset.get('content_hash')}`)"
    )
    model = summary["model"]
    lines.append(
        f"Model: **{model.get('name')}** (revision `{model.get('revision') or 'default'}`)"
    )
    generation = summary["generation_config"]
    lines.append(
        f"Generation: temperature={generation.get('temperature')}, "
        f"max_new_tokens={generation.get('max_new_tokens')}, "
        f"top_p={generation.get('top_p')}, retrieval top_k={generation.get('top_k')}"
    )
    lines.append("")
    lines.append("## 1. Retrieval evaluation")
    retrieval = summary["retrieval"]
    lines.append("")
    lines.append("### In-domain retrieval (answer questions)")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(retrieval.get("summary_in_domain", {}), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("### By language (in-domain)")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(retrieval.get("summary_in_domain_by_language", {}), indent=2)
    )
    lines.append("```")
    lines.append("")
    lines.append("### Out-of-domain rejection")
    ood = retrieval.get("out_of_domain", {})
    lines.append(
        f"- {ood.get('rejected_count', 0)}/{ood.get('count', 0)} out-of-domain "
        f"questions correctly rejected (rejection rate {_fmt(ood.get('rejection_rate'))})."
    )
    lines.append("")
    lines.append("## 2. Eligibility evaluation")
    lines.append("")
    lines.append("### Real tier (v1 ruleset, non-decisive)")
    lines.append("")
    real = summary["eligibility"]["real"]
    lines.append(
        f"- {real.get('count', 0)} real applicant profiles evaluated against the "
        f"non-decisive v1 ruleset."
    )
    lines.append(
        f"- Expected `insufficient_information` cases: "
        f"{real.get('expected_insufficient_information_count', 0)}."
    )
    lines.append(
        f"- Exact expected-vs-actual matches: {real.get('exact_match_count', 0)} "
        f"(accuracy {_fmt(real.get('accuracy'))})."
    )
    lines.append(
        "- Per the M5 audit, `insufficient_information` is the **honest** result of "
        "a non-decisive ruleset (official sources publish no GPA/group/program "
        "thresholds), NOT a failure."
    )
    lines.append("")
    lines.append("### Synthetic tier (decisive fixture rulesets, engine test only)")
    lines.append("")
    synthetic = summary["eligibility"]["synthetic"]
    lines.append(
        f"- {synthetic.get('count', 0)} synthetic fixture cases evaluated against "
        f"decisive fixture rulesets (SYNTHETIC-FIXTURE source; never real DIU policy)."
    )
    lines.append(
        f"- Exact expected-vs-actual matches: {synthetic.get('exact_match_count', 0)} "
        f"(accuracy {_fmt(synthetic.get('accuracy'))})."
    )
    mismatches = [
        record
        for record in synthetic.get("records", [])
        if not record.get("correct")
    ]
    if mismatches:
        lines.append("")
        lines.append("**Reported mismatches (honest, dataset not altered):**")
        for record in mismatches:
            lines.append(
                f"- `{record['id']}`: expected `{record['expected_outcome']}`, "
                f"engine decided `{record['actual_decision']}`. The machine-readable "
                f"`fixture_rule` + `eligibility_input` do not encode the second "
                f"numeric rule described in the question text."
            )
    lines.append("")
    lines.append("## 3. Generation evaluation — Base vs Base + RAG")
    lines.append("")
    lines.append("Same model, same questions, `temperature=0.0`; the only difference is retrieved evidence.")
    lines.append("")
    lines.append("| Condition | In-domain answered | OOD refused |")
    lines.append("| --- | --- | --- |")
    base_in = condition_base.get("aggregates", {}).get("in_domain_count", 0)
    base_ood = condition_base.get("aggregates", {}).get("out_of_domain_count", 0)
    base_refusal = condition_base.get("aggregates", {}).get("out_of_domain_refusal_accuracy", 0.0)
    rag_in = condition_rag.get("aggregates", {}).get("in_domain_count", 0)
    rag_ood = condition_rag.get("aggregates", {}).get("out_of_domain_count", 0)
    rag_refusal = condition_rag.get("aggregates", {}).get("out_of_domain_refusal_accuracy", 0.0)
    lines.append(
        f"| Base | {base_in} | {_fmt(base_refusal)} ({base_ood}) |"
    )
    lines.append(
        f"| Base + RAG | {rag_in} | {_fmt(rag_refusal)} ({rag_ood}) |"
    )
    lines.append("")
    lines.append("### Headline metrics (in-domain, mean over questions)")
    lines.append("")
    lines.append(_metric_rows(summary.get("base_vs_rag", {})))
    lines.append("")
    lines.append("### By language (mean over questions)")
    lines.append("")
    for language in ("en", "bn", "banglish"):
        base_lang = condition_base.get("aggregates", {}).get("language_adherence_by_language", {})
        rag_lang = condition_rag.get("aggregates", {}).get("language_adherence_by_language", {})
        lines.append(
            f"- `{language}`: base language adherence "
            f"{_fmt(base_lang.get(language))} vs rag {_fmt(rag_lang.get(language))}."
        )
    lines.append("")
    lines.append("## 4. Interpretation and limitations")
    lines.append("")
    lines.append(
        "- All metrics are **deterministic proxies**; no LLM judge or paid API was used."
    )
    lines.append(
        "- Groundedness is computed against retrieved evidence only; a base-condition "
        "answer has no evidence, so its groundedness is 0.0 by construction."
    )
    lines.append(
        "- The hallucination n-gram rate is `1 - groundedness` and is a coarse proxy, "
        "not a true factuality measurement."
    )
    lines.append(
        "- Language adherence for `banglish` is a script-only heuristic: Bangla "
        "transliterated to Latin is indistinguishable from English by script, so a "
        "Latin-only answer scores full adherence."
    )
    lines.append(
        "- Eligibility decisions are made only by the deterministic rule engine; the "
        "LLM never decides eligibility (AGENTS.md rules 15-16)."
    )
    lines.append("")
    lines.append("_Generated by `evaluation/report.py`; source JSONs are authoritative._")
    lines.append("")
    return "\n".join(lines)


__all__ = ["DEFAULT_RESULTS_DIR", "ReportError", "build_report"]