"""Schema, loader and validator for the M5 held-out evaluation dataset.

TASK-05A scope only: dataset authoring/validation infrastructure. Metrics,
retrieval evaluation, generation evaluation, eligibility evaluation, and
report generation are implemented in M5-B, never here.

The dataset is the single held-out question-level evaluation dataset that all
four research arms (Base LLM, Fine-tuned LLM, Base LLM + RAG, Fine-tuned LLM +
RAG) will be scored on. It is therefore off-limits to M6 fine-tuning. The
anti-reuse mechanism (`question_hashes`, `assert_no_overlap_with_finetuning`)
lets M6 prove its training questions do not collide with this held-out set.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "evaluation" / "questions.v1.json"
DEFAULT_KB_PATH = PROJECT_ROOT / "data" / "chunks" / "local_knowledge_base.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "cleaned" / "v2" / "manifest.json"

ALLOWED_LANGUAGES = frozenset({"en", "bn", "banglish"})
ALLOWED_OUTCOMES = frozenset(
    {"answer", "refuse", "insufficient_information", "eligible", "not_eligible"}
)
SPECIAL_CATEGORIES = frozenset({"out_of_domain", "eligibility_real", "eligibility_synthetic"})
DATASET_USAGE_HELDOUT = "held_out_eval"
SYNTHETIC_SOURCE_ID = "SYNTHETIC-FIXTURE"
SYNTHETIC_DOCUMENT_ID = "synthetic-fixture-001"

ELIGIBLE_CURRENCY_STATUSES = frozenset({"current_date_sensitive", "stable_reference"})
VALID_EXTRACTION_STATUS = "success"

REQUIRED_QUESTION_FIELDS = frozenset(
    {
        "id",
        "language",
        "category",
        "question",
        "golden_answer",
        "gold_chunk_ids",
        "expected_outcome",
        "dataset_usage",
        "dataset_version",
    }
)

_WS_RE = re.compile(r"\s+")


class EvalDatasetError(ValueError):
    """Raised when the evaluation dataset fails schema validation."""


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    language: str
    category: str
    question: str
    golden_answer: str
    gold_chunk_ids: tuple[str, ...]
    expected_outcome: str
    dataset_usage: str
    dataset_version: str
    source_id: str = ""
    document_id: str = ""
    source_url: str = ""
    title: str = ""
    is_synthetic: bool = False
    eligibility_input: dict[str, Any] | None = None
    fixture_rule: dict[str, Any] | None = None
    notes: str = ""

    @property
    def is_out_of_domain(self) -> bool:
        return self.category == "out_of_domain"

    @property
    def is_eligibility_real(self) -> bool:
        return self.category == "eligibility_real"

    @property
    def is_eligibility_synthetic(self) -> bool:
        return self.category == "eligibility_synthetic"


@dataclass(frozen=True)
class EvalDataset:
    dataset_id: str
    version: str
    schema_version: str
    purpose: str
    description: str
    held_out: bool
    content_hash: str
    source_knowledge_base: str
    questions: tuple[EvalQuestion, ...] = field(default_factory=tuple)

    @property
    def by_id(self) -> dict[str, EvalQuestion]:
        return {q.id: q for q in self.questions}


def load_knowledge_base(kb_path: Path) -> dict[str, dict[str, Any]]:
    with open(kb_path, encoding="utf-8") as fh:
        kb = json.load(fh)
    chunks: dict[str, dict[str, Any]] = {}
    for entry in kb.get("entries", []):
        chunk = entry.get("chunk", {})
        chunks[chunk.get("chunk_id", "")] = chunk
    return chunks


def load_manifest(manifest_path: Path) -> set[tuple[str, str]]:
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return {(r["source_id"], r["document_id"]) for r in manifest.get("records", [])}


def compute_content_hash(payload: dict[str, Any]) -> str:
    """Deterministic sha256 over the canonical JSON of the payload.

    The caller must pass the dataset payload WITHOUT the ``content_hash`` field
    (the stored hash is a checksum of everything else), or pass the full
    payload and the hash is excluded inside this function.
    """
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_hash_from_raw(raw: dict[str, Any]) -> str:
    payload = dict(raw)
    payload.pop("content_hash", None)
    return compute_content_hash(payload)


def normalize_question_text(text: str) -> str:
    """Normalize question text for duplicate detection (per language)."""
    return _WS_RE.sub(" ", text.strip().casefold())


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise EvalDatasetError(message)


def _validate_question(
    q_raw: dict[str, Any],
    index: int,
    *,
    kb_chunks: dict[str, dict[str, Any]],
    manifest: set[tuple[str, str]],
    kb_categories: set[str],
    dataset_version: str,
) -> EvalQuestion:
    prefix = f"question[{index}]"

    missing = REQUIRED_QUESTION_FIELDS - set(q_raw)
    _check(not missing, f"{prefix}: missing required fields {sorted(missing)}")

    qid = q_raw["id"]
    language = q_raw["language"]
    category = q_raw["category"]
    question = q_raw["question"]
    golden_answer = q_raw["golden_answer"]
    gold_chunk_ids = q_raw["gold_chunk_ids"]
    expected_outcome = q_raw["expected_outcome"]
    dataset_usage = q_raw["dataset_usage"]
    question_version = q_raw["dataset_version"]

    _check(qid and isinstance(qid, str), f"{prefix}: 'id' must be a non-empty string")
    _check(language in ALLOWED_LANGUAGES, f"{prefix} ({qid}): invalid language {language!r}")
    _check(
        question_version == dataset_version,
        f"{prefix} ({qid}): dataset_version {question_version!r} != {dataset_version!r}",
    )
    _check(
        isinstance(gold_chunk_ids, list),
        f"{prefix} ({qid}): 'gold_chunk_ids' must be a list",
    )
    _check(expected_outcome in ALLOWED_OUTCOMES, f"{prefix} ({qid}): invalid expected_outcome {expected_outcome!r}")
    _check(
        dataset_usage == DATASET_USAGE_HELDOUT,
        f"{prefix} ({qid}): dataset_usage must be {DATASET_USAGE_HELDOUT!r} (held-out, off-limits to fine-tuning)",
    )
    _check(bool(question.strip()), f"{prefix} ({qid}): empty question")
    _check(bool(golden_answer.strip()), f"{prefix} ({qid}): empty golden_answer")

    is_synthetic = bool(q_raw.get("is_synthetic", False))
    source_id = q_raw.get("source_id", "")
    document_id = q_raw.get("document_id", "")
    source_url = q_raw.get("source_url", "")
    title = q_raw.get("title", "")
    eligibility_input = q_raw.get("eligibility_input")
    fixture_rule = q_raw.get("fixture_rule")
    notes = q_raw.get("notes", "")

    if category in kb_categories:
        _check(
            expected_outcome == "answer",
            f"{prefix} ({qid}): in-domain question must have expected_outcome 'answer', got {expected_outcome!r}",
        )
        _check(
            gold_chunk_ids,
            f"{prefix} ({qid}): in-domain question must cite at least one gold_chunk_id",
        )
        _check(source_id and document_id, f"{prefix} ({qid}): in-domain question needs source_id/document_id")
        _check(
            (source_id, document_id) in manifest,
            f"{prefix} ({qid}): ({source_id}, {document_id}) not found in cleaned manifest",
        )
        for chunk_id in gold_chunk_ids:
            chunk = kb_chunks.get(chunk_id)
            _check(chunk is not None, f"{prefix} ({qid}): gold_chunk_id {chunk_id!r} missing from knowledge base")
            _check(
                chunk.get("source_id") == source_id and chunk.get("document_id") == document_id,
                f"{prefix} ({qid}): chunk {chunk_id!r} provenance does not match ({source_id}, {document_id})",
            )
            _check(
                chunk.get("currency_status") in ELIGIBLE_CURRENCY_STATUSES,
                f"{prefix} ({qid}): chunk {chunk_id!r} has currency_status {chunk.get('currency_status')!r}",
            )
            _check(
                chunk.get("extraction_status") == VALID_EXTRACTION_STATUS,
                f"{prefix} ({qid}): chunk {chunk_id!r} extraction_status {chunk.get('extraction_status')!r}",
            )
            _check(
                not chunk.get("manual_review"),
                f"{prefix} ({qid}): chunk {chunk_id!r} is flagged manual_review",
            )
        _check(
            not source_url or any(
                kb_chunks[c].get("source_url") == source_url for c in gold_chunk_ids
            ),
            f"{prefix} ({qid}): source_url {source_url!r} does not match cited chunks",
        )
        _check(
            not is_synthetic,
            f"{prefix} ({qid}): in-domain question must not be marked synthetic",
        )
    elif category == "out_of_domain":
        _check(
            expected_outcome == "refuse",
            f"{prefix} ({qid}): out_of_domain question must have expected_outcome 'refuse', got {expected_outcome!r}",
        )
        _check(not gold_chunk_ids, f"{prefix} ({qid}): out_of_domain question must not cite chunks")
        _check(not source_id, f"{prefix} ({qid}): out_of_domain question must not have a source_id")
        _check(not is_synthetic, f"{prefix} ({qid}): out_of_domain question must not be synthetic")
    elif category == "eligibility_real":
        _check(
            expected_outcome == "insufficient_information",
            f"{prefix} ({qid}): v1 rules are non-decisive; real eligibility must be 'insufficient_information', got {expected_outcome!r}",
        )
        _check(not gold_chunk_ids, f"{prefix} ({qid}): eligibility_real must not cite retrieval chunks")
        _check(eligibility_input is not None, f"{prefix} ({qid}): eligibility_real needs eligibility_input")
        _check(
            (source_id, document_id) in manifest if source_id else True,
            f"{prefix} ({qid}): ({source_id}, {document_id}) not found in cleaned manifest",
        )
        _check(not is_synthetic, f"{prefix} ({qid}): real eligibility case must not be synthetic")
    elif category == "eligibility_synthetic":
        _check(is_synthetic, f"{prefix} ({qid}): eligibility_synthetic must be marked is_synthetic=true")
        _check(
            expected_outcome in {"eligible", "not_eligible", "insufficient_information"},
            f"{prefix} ({qid}): synthetic fixture outcome must be eligible/not_eligible/insufficient_information",
        )
        _check(not gold_chunk_ids, f"{prefix} ({qid}): synthetic fixture must not cite retrieval chunks")
        _check(source_id == SYNTHETIC_SOURCE_ID, f"{prefix} ({qid}): synthetic source_id must be {SYNTHETIC_SOURCE_ID!r}")
        _check(
            document_id == SYNTHETIC_DOCUMENT_ID,
            f"{prefix} ({qid}): synthetic document_id must be {SYNTHETIC_DOCUMENT_ID!r}",
        )
        _check(fixture_rule is not None, f"{prefix} ({qid}): synthetic fixture needs fixture_rule")
    else:
        raise EvalDatasetError(f"{prefix} ({qid}): unknown category {category!r}")

    return EvalQuestion(
        id=qid,
        language=language,
        category=category,
        question=question,
        golden_answer=golden_answer,
        gold_chunk_ids=tuple(gold_chunk_ids),
        expected_outcome=expected_outcome,
        dataset_usage=dataset_usage,
        dataset_version=question_version,
        source_id=source_id,
        document_id=document_id,
        source_url=source_url,
        title=title,
        is_synthetic=is_synthetic,
        eligibility_input=eligibility_input,
        fixture_rule=fixture_rule,
        notes=notes,
    )


def load_eval_dataset(
    dataset_path: Path | None = None,
    knowledge_base_path: Path | None = None,
    cleaned_manifest_path: Path | None = None,
) -> EvalDataset:
    """Load and validate the M5 held-out evaluation dataset against the KB and manifest."""
    dataset_path = Path(dataset_path or DEFAULT_DATASET_PATH)
    kb_path = Path(knowledge_base_path or DEFAULT_KB_PATH)
    manifest_path = Path(cleaned_manifest_path or DEFAULT_MANIFEST_PATH)

    _check(dataset_path.is_file(), f"dataset not found: {dataset_path}")
    _check(kb_path.is_file(), f"knowledge base not found: {kb_path}")
    _check(manifest_path.is_file(), f"manifest not found: {manifest_path}")

    with open(dataset_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    kb_chunks = load_knowledge_base(kb_path)
    manifest = load_manifest(manifest_path)
    kb_categories = {c["category"] for c in kb_chunks.values() if c.get("category")}

    for req in ("dataset_id", "version", "schema_version", "purpose", "description"):
        _check(req in raw, f"dataset missing top-level field {req!r}")
    _check(raw.get("held_out") is True, "dataset must be marked held_out: true")
    _check(
        raw.get("dataset_usage") == DATASET_USAGE_HELDOUT,
        "dataset_usage must be 'held_out_eval'",
    )
    version = raw["version"]
    schema_version = raw["schema_version"]
    _check(version, "dataset version must be non-empty")
    _check(schema_version, "dataset schema_version must be non-empty")

    raw_questions = raw.get("questions", [])
    _check(isinstance(raw_questions, list) and raw_questions, "dataset 'questions' must be a non-empty list")

    ids = [q["id"] for q in raw_questions]
    _check(len(ids) == len(set(ids)), "question ids must be unique")

    seen_text: dict[str, set[str]] = {}
    questions: list[EvalQuestion] = []
    for index, q_raw in enumerate(raw_questions):
        q = _validate_question(
            q_raw,
            index,
            kb_chunks=kb_chunks,
            manifest=manifest,
            kb_categories=kb_categories,
            dataset_version=version,
        )
        normalized = normalize_question_text(q.question)
        bucket = seen_text.setdefault(q.language, set())
        _check(
            normalized not in bucket,
            f"duplicate question text in language {q.language!r}: {q.question[:80]!r}",
        )
        bucket.add(normalized)
        questions.append(q)

    languages_present = {q.language for q in questions}
    _check(
        languages_present >= ALLOWED_LANGUAGES,
        f"dataset must cover all languages {sorted(ALLOWED_LANGUAGES)}, got {sorted(languages_present)}",
    )

    expected_hash = raw.get("content_hash")
    _check(bool(expected_hash), "dataset must contain a content_hash")
    actual_hash = _canonical_hash_from_raw(raw)
    _check(
        expected_hash == actual_hash,
        f"content_hash mismatch: stored {expected_hash!r}, computed {actual_hash!r}",
    )

    return EvalDataset(
        dataset_id=raw["dataset_id"],
        version=version,
        schema_version=schema_version,
        purpose=raw["purpose"],
        description=raw["description"],
        held_out=True,
        content_hash=expected_hash,
        source_knowledge_base=raw.get("source_knowledge_base", str(kb_path)),
        questions=tuple(questions),
    )


def question_hashes(dataset: EvalDataset) -> dict[str, str]:
    """Map each held-out question id to a canonical text signature.

    M6 uses these signatures (via ``assert_no_overlap_with_finetuning``) to
    prove its fine-tuning QA pairs do not reuse held-out evaluation questions.
    """
    return {
        q.id: hashlib.sha256(normalize_question_text(q.question).encode("utf-8")).hexdigest()
        for q in dataset.questions
    }


def assert_no_overlap_with_finetuning(
    dataset: EvalDataset,
    finetuning_questions: list[str],
) -> None:
    """Raise EvalDatasetError if any finetuning question matches a held-out question.

    Called by M6 before fine-tuning. ``finetuning_questions`` is a list of
    question strings from the candidate fine-tuning dataset.
    """
    signatures = set(question_hashes(dataset).values())
    collisions = [
        q for q in finetuning_questions
        if hashlib.sha256(normalize_question_text(q).encode("utf-8")).hexdigest() in signatures
    ]
    if collisions:
        raise EvalDatasetError(
            f"{len(collisions)} finetuning question(s) collide with the held-out "
            f"evaluation dataset: {collisions[:5]}"
        )
