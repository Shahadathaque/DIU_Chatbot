"""M5 baseline evaluation package for the DIU Admission AI research.

TASK-05A delivered the held-out question-level evaluation dataset and its
schema/loader/validator. M5-B adds the evaluation harness: deterministic
metrics, retrieval evaluation, eligibility evaluation, generation evaluation
(base vs rag at temperature=0.0), and report aggregation.
"""

from evaluation.schema import (
    DEFAULT_DATASET_PATH,
    DEFAULT_KB_PATH,
    DEFAULT_MANIFEST_PATH,
    EvalDataset,
    EvalQuestion,
    EvalDatasetError,
    assert_no_overlap_with_finetuning,
    load_eval_dataset,
    question_hashes,
)

__all__ = [
    "DEFAULT_DATASET_PATH",
    "DEFAULT_KB_PATH",
    "DEFAULT_MANIFEST_PATH",
    "EvalDataset",
    "EvalQuestion",
    "EvalDatasetError",
    "assert_no_overlap_with_finetuning",
    "load_eval_dataset",
    "question_hashes",
]