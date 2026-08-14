"""One-command driver for the complete M5 baseline evaluation (M5-B).

Execution order (per the M5 audit):

1. Load and validate the held-out v1 dataset (schema validation runs inside
   ``load_eval_dataset``).
2. ``retrieval_eval`` — offline retrieval Recall@K / Precision@K / MRR.
3. ``eligibility_eval`` — real (v1 ruleset) and synthetic (fixture) tiers.
4. ``generation_eval`` condition=base then condition=rag — same model, same
   questions, ``temperature=0.0``.
5. ``report`` — aggregate into ``summary.json`` and ``report.md``.

Run from the project root with the venv active:

    python -m evaluation.run_all [--max-questions N] [--max-new-tokens N]

Generation evaluation is the slow part (local Qwen on MPS). Use
``--max-questions`` to smoke-test a subset first.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from evaluation.schema import PROJECT_ROOT, load_eval_dataset

DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "evaluation" / "v1"


def _build_retriever():
    from rag.retriever import create_retriever

    return create_retriever()


def _build_generator():
    from rag.generator import create_generator

    return create_generator()


def _run_retrieval(dataset, *, max_questions: Optional[int], results_dir: Path) -> None:
    from evaluation.retrieval_eval import run_retrieval_eval

    retriever = _build_retriever()
    run_retrieval_eval(
        dataset,
        retriever,
        top_k=10,
        max_questions=max_questions,
        results_dir=results_dir,
    )


def _run_eligibility(dataset, *, max_questions: Optional[int], results_dir: Path) -> None:
    from evaluation.eligibility_eval import run_eligibility_eval

    run_eligibility_eval(dataset, results_dir=results_dir)


def _run_generation(
    dataset,
    *,
    condition: str,
    temperature: float,
    max_new_tokens: Optional[int],
    top_p: Optional[float],
    top_k: int,
    max_questions: Optional[int],
    results_dir: Path,
) -> None:
    from evaluation.generation_eval import run_generation_eval

    retriever = None
    if condition == "rag":
        retriever = _build_retriever()
    generator = _build_generator()
    run_generation_eval(
        dataset,
        retriever,
        generator,
        condition=condition,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
        top_p=top_p,
        top_k=top_k,
        max_questions=max_questions,
        results_dir=results_dir,
    )


def _run_report(results_dir: Path) -> None:
    from evaluation.report import build_report

    build_report(results_dir)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete M5 baseline evaluation for DIU Admission AI."
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Limit generation + retrieval to the first N in-domain questions (smoke test).",
    )
    parser.add_argument("--temperature", type=float, default=0.0, help="Generation temperature.")
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=None,
        help="Generation max_new_tokens (default: generator settings).",
    )
    parser.add_argument("--top-p", type=float, default=None, help="Generation top_p.")
    parser.add_argument("--top-k", type=int, default=5, help="Retrieval top_k for RAG generation.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory for evaluation output JSONs and report.",
    )
    args = parser.parse_args(argv)

    if args.temperature != 0.0:
        print(
            "WARNING: temperature is not 0.0; generation will not be greedy/reproducible."
        )

    results_dir = args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    dataset = load_eval_dataset()
    print(
        f"[1/5] dataset validated: {dataset.dataset_id} v{dataset.version}, "
        f"{len(dataset.questions)} questions (hash {dataset.content_hash[:12]}…)"
    )

    print("[2/5] retrieval evaluation (offline, local KB)…")
    _run_retrieval(dataset, max_questions=args.max_questions, results_dir=results_dir)

    print("[3/5] eligibility evaluation (real + synthetic tiers)…")
    _run_eligibility(dataset, max_questions=args.max_questions, results_dir=results_dir)

    print("[4/5] generation evaluation condition=base (temperature=0.0)…")
    _run_generation(
        dataset,
        condition="base",
        temperature=args.temperature,
        max_new_tokens=args.max_new_tokens,
        top_p=args.top_p,
        top_k=args.top_k,
        max_questions=args.max_questions,
        results_dir=results_dir,
    )

    print("[4/5] generation evaluation condition=rag (temperature=0.0)…")
    _run_generation(
        dataset,
        condition="rag",
        temperature=args.temperature,
        max_new_tokens=args.max_new_tokens,
        top_p=args.top_p,
        top_k=args.top_k,
        max_questions=args.max_questions,
        results_dir=results_dir,
    )

    print("[5/5] aggregating summary.json + report.md…")
    _run_report(results_dir)

    print(f"Done. Results written to {results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())