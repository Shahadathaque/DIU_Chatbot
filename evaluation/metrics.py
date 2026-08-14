"""Deterministic, rule-based evaluation metrics for the DIU M5 baseline.

M5-B scope: deterministic metrics only. No LLM judge, no paid API, no external
metric library. Every score below is computed from plain token/character
operations over a single prediction/reference pair (or prediction/evidence
pair), so results are fully reproducible and explainable. These are intentional
proxies, documented as such.

Metric families provided here:

- lexical match: ``normalized_exact_match``, ``token_f1``
- ROUGE: ``rouge_1``, ``rouge_2``, ``rouge_l`` (overlapping n-grams / LCS)
- snippet fidelity: ``verbatim_snippet_containment``
- groundedness / hallucination proxies: ``groundedness``,
  ``hallucination_ngram_rate``
- citations: ``extract_urls``, ``check_fabricated_citations``
- behavior: ``is_refusal``, ``domain_adherence``, ``refusal_accuracy``,
  ``detect_script``, ``language_adherence``
- latency helpers: ``Stopwatch``, ``elapsed_seconds``, ``format_latency_ms``
- retrieval ranking: ``recall_at_k``, ``precision_at_k``,
  ``reciprocal_rank``, ``average_precision``

None of these functions load a model or touch the network.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence

_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[\w\u0980-\u09ff]+", re.UNICODE)
_URL_RE = re.compile(r"https?://[^\s)\]}>]+")
_BANGLA_CHAR_RE = re.compile(r"[\u0980-\u09ff]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")

_URL_TRAILING_PUNCTUATION = ".,;:!?)]}>\"'"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _tokens(text: str) -> List[str]:
    """Case-folded, NFKC-normalized word tokens (keeps Bangla script)."""
    return _TOKEN_RE.findall(unicodedata.normalize("NFKC", text).casefold())


def normalize_text(text: str) -> str:
    """Canonical form for exact matching: space-joined, punct-free tokens."""
    return " ".join(_tokens(text))


def _n_grams(tokens: Sequence[str], n: int) -> Counter:
    return Counter(tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1))


def _harmonic_mean(precision: float, recall: float) -> float:
    if precision + recall == 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def mean(values: Iterable[float]) -> float:
    """Arithmetic mean over a list; 0.0 for an empty list."""
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


# ---------------------------------------------------------------------------
# Lexical match
# ---------------------------------------------------------------------------


def normalized_exact_match(prediction: str, reference: str) -> float:
    """1.0 when the normalized forms are identical, else 0.0."""
    return 1.0 if normalize_text(prediction) == normalize_text(reference) else 0.0


def token_f1(prediction: str, reference: str) -> float:
    """Token-level F1 (micro-averaged overlap) between prediction and reference."""
    pred_tokens = _tokens(prediction)
    ref_tokens = _tokens(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = sum((Counter(pred_tokens) & Counter(ref_tokens)).values())
    if common == 0:
        return 0.0
    precision = common / len(pred_tokens)
    recall = common / len(ref_tokens)
    return _harmonic_mean(precision, recall)


# ---------------------------------------------------------------------------
# ROUGE
# ---------------------------------------------------------------------------


def rouge_n(prediction: str, reference: str, n: int) -> Dict[str, float]:
    """ROUGE-N precision/recall/f1 over word n-grams (standard definition)."""
    if n < 1:
        raise ValueError("rouge_n requires n >= 1")
    pred_grams = _n_grams(_tokens(prediction), n)
    ref_grams = _n_grams(_tokens(reference), n)
    if not pred_grams or not ref_grams:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    overlap = sum((pred_grams & ref_grams).values())
    precision = overlap / sum(pred_grams.values())
    recall = overlap / sum(ref_grams.values())
    return {"precision": precision, "recall": recall, "f1": _harmonic_mean(precision, recall)}


def rouge_1(prediction: str, reference: str) -> Dict[str, float]:
    """ROUGE-1 precision/recall/f1."""
    return rouge_n(prediction, reference, 1)


def rouge_2(prediction: str, reference: str) -> Dict[str, float]:
    """ROUGE-2 precision/recall/f1."""
    return rouge_n(prediction, reference, 2)


def _lcs_length(left: Sequence[str], right: Sequence[str]) -> int:
    """Length of the longest common subsequence of two token sequences."""
    previous = [0] * (len(right) + 1)
    for left_item in left:
        current = [0] * (len(right) + 1)
        for index, right_item in enumerate(right, start=1):
            if left_item == right_item:
                current[index] = previous[index - 1] + 1
            else:
                current[index] = max(previous[index], current[index - 1])
        previous = current
    return previous[len(right)]


def rouge_l(prediction: str, reference: str) -> Dict[str, float]:
    """ROUGE-L precision/recall/f1 based on the longest common subsequence."""
    pred_tokens = _tokens(prediction)
    ref_tokens = _tokens(reference)
    if not pred_tokens or not ref_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    lcs = _lcs_length(pred_tokens, ref_tokens)
    precision = lcs / len(pred_tokens)
    recall = lcs / len(ref_tokens)
    return {"precision": precision, "recall": recall, "f1": _harmonic_mean(precision, recall)}


# ---------------------------------------------------------------------------
# Snippet fidelity and groundedness proxies
# ---------------------------------------------------------------------------


def verbatim_snippet_containment(prediction: str, reference: str, n: int = 4) -> float:
    """Fraction of the reference's word n-grams found verbatim in the prediction.

    A high score means the prediction faithfully reproduces chunks of the
    golden answer (paraphrase-free fidelity). ``n`` shrinks automatically when
    the reference is too short to contain ``n`` tokens.
    """
    pred_tokens = _tokens(prediction)
    ref_tokens = _tokens(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0
    resolved_n = min(n, len(ref_tokens))
    pred_ngrams = set(_n_grams(pred_tokens, resolved_n).keys())
    ref_ngrams = set(_n_grams(ref_tokens, resolved_n).keys())
    if not ref_ngrams:
        return 0.0
    return len(ref_ngrams & pred_ngrams) / len(ref_ngrams)


def groundedness(prediction: str, evidence_texts: Sequence[str], n: int = 4) -> float:
    """Proxy for 'how much of the prediction is supported by retrieved evidence'.

    Fraction of the prediction's word n-grams that appear verbatim in the
    supplied evidence texts. With empty evidence this is 0.0, which is the
    honest reading for a no-RAG (base) condition that has no grounding source.
    """
    pred_tokens = _tokens(prediction)
    if not pred_tokens:
        return 0.0
    resolved_n = min(n, len(pred_tokens))
    pred_ngrams = set(_n_grams(pred_tokens, resolved_n).keys())
    if not pred_ngrams:
        return 0.0
    evidence_ngrams: set = set()
    for text in evidence_texts or ():
        evidence_ngrams.update(_n_grams(_tokens(text), resolved_n).keys())
    if not evidence_ngrams:
        return 0.0
    return len(pred_ngrams & evidence_ngrams) / len(pred_ngrams)


def hallucination_ngram_rate(prediction: str, evidence_texts: Sequence[str], n: int = 4) -> float:
    """Proxy for hallucination: fraction of prediction n-grams unsupported by evidence.

    This is ``1 - groundedness``. It is intentionally a coarse proxy: a model
    may be right from parametric knowledge while scoring 1.0 here, and it may
    copy unsupported n-grams from evidence while scoring 0.0.
    """
    return 1.0 - groundedness(prediction, evidence_texts, n=n)


# ---------------------------------------------------------------------------
# Citation checks
# ---------------------------------------------------------------------------


def extract_urls(text: str) -> List[str]:
    """Return all http(s) URLs found in ``text``, trailing punctuation stripped."""
    urls: List[str] = []
    for match in _URL_RE.findall(text):
        url = match.rstrip(_URL_TRAILING_PUNCTUATION)
        if url:
            urls.append(url)
    return urls


def check_fabricated_citations(prediction: str, allowed_urls: Sequence[str]) -> Dict[str, object]:
    """Flag any URL in the prediction that is not one of the allowed/supplied URLs.

    ``allowed_urls`` must be the retrieved evidence URLs for the RAG condition;
    pass an empty sequence for the base condition where no sources are provided,
    so any URL the model emits is unverifiable and therefore fabricated.
    """
    allowed = {url.rstrip(_URL_TRAILING_PUNCTUATION) for url in (allowed_urls or ())}
    urls = extract_urls(prediction)
    fabricated = [url for url in urls if url not in allowed]
    return {
        "url_count": len(urls),
        "fabricated_url_count": len(fabricated),
        "fabricated_urls": fabricated,
    }


# ---------------------------------------------------------------------------
# Domain adherence / refusal
# ---------------------------------------------------------------------------

_REFUSAL_PHRASES = (
    "i could not find enough",
    "cannot answer",
    "can't answer",
    "i don't know",
    "i do not know",
    "i am unable",
    "i'm unable",
    "unable to answer",
    "cannot help",
    "cannot determine",
    "cannot confirm",
    "cannot provide",
    "can't provide",
    "unable to provide",
    "out of scope",
    "outside the scope",
    "not enough information",
    "insufficient information",
    "insufficient evidence",
    "cannot verify",
    "not able to",
    "no information available",
    "i'm sorry",
    "i am sorry",
    "don't have specific",
    "do not have specific",
    "don't have enough information",
    "do not have enough information",
    "don't have access",
    "do not have access",
    "as of my last update",
    "there isn't specific",
    "does not have specific tuition fee details",
    "পর্যাপ্ত যাচাইকৃত তথ্য পাওয়া যায়নি",
    "যাচাইকৃত তথ্য পাওয়া যায়নি",
    "আমি জানি না",
    "জানি না",
    "জানতে পারি না",
    "তথ্য পাওয়া যায়নি",
    "তথ্য নেই",
    "apnar proshner uttor dewar jonno",
    "uttor dewar jonno",
    "enough verified information",
    "paowa jay ni",
    "jani na",
    "jaani na",
)


def is_refusal(text: str) -> bool:
    """Deterministic proxy: does the text signal a refused / cannot-answer response?"""
    lowered = unicodedata.normalize("NFKC", text).casefold()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


def domain_adherence(expected_refuse: bool, refused: bool) -> float:
    """1.0 when the refusal behavior matches the expectation, else 0.0.

    In-domain questions expect ``expected_refuse=False`` (the system should
    answer); out-of-domain questions expect ``expected_refuse=True``.
    """
    return 1.0 if bool(refused) == bool(expected_refuse) else 0.0


def refusal_accuracy(detected_refusal: bool, expected_refuse: bool) -> float:
    """Alias for ``domain_adherence`` scoped to refusal questions."""
    return domain_adherence(expected_refuse, detected_refusal)


# ---------------------------------------------------------------------------
# Language adherence
# ---------------------------------------------------------------------------


def detect_script(text: str) -> str:
    """Coarse script classification: 'bn', 'latin', 'mixed', or 'none'."""
    bangla = len(_BANGLA_CHAR_RE.findall(text))
    latin = len(_LATIN_CHAR_RE.findall(text))
    total = bangla + latin
    if total == 0:
        return "none"
    if bangla / total >= 0.5:
        return "bn"
    if bangla > 0:
        return "mixed"
    return "latin"


def language_adherence(prediction: str, requested_language: str) -> float:
    """Continuous proxy for 'is the answer in the requested language?'.

    - ``bn``: share of content characters that are Bangla script (>= 0.5 => 1.0).
    - ``en``: share of content characters that are Latin script (>= 0.5 => 1.0).
    - ``banglish``: Bangla written in Latin script is indistinguishable from
      English by script alone, so adherence is 1.0 only when the answer is
      entirely Latin-script (no Bangla characters). This is a documented
      limitation of a deterministic proxy.

    Returns 0.0 for empty or script-less predictions.
    """
    if not prediction.strip():
        return 0.0
    bangla = len(_BANGLA_CHAR_RE.findall(prediction))
    latin = len(_LATIN_CHAR_RE.findall(prediction))
    total = bangla + latin
    if total == 0:
        return 0.0
    bangla_ratio = bangla / total
    latin_ratio = latin / total
    if requested_language == "bn":
        return 1.0 if bangla_ratio >= 0.5 else bangla_ratio / 0.5
    if requested_language == "banglish":
        return 1.0 if latin_ratio == 1.0 else 0.0
    return 1.0 if latin_ratio >= 0.5 else latin_ratio / 0.5


# ---------------------------------------------------------------------------
# Latency helpers
# ---------------------------------------------------------------------------


class Stopwatch:
    """Tiny context manager that records an elapsed time in seconds."""

    def __enter__(self) -> "Stopwatch":
        self._start = time.perf_counter()
        self.elapsed = 0.0
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed = time.perf_counter() - self._start

    @property
    def seconds(self) -> float:
        return self.elapsed


def elapsed_seconds(start: float) -> float:
    """Seconds elapsed since the ``time.perf_counter()`` value ``start``."""
    return time.perf_counter() - start


def format_latency_ms(seconds: float) -> float:
    """Milliseconds as a float for deterministic JSON output."""
    return round(seconds * 1000.0, 3)


# ---------------------------------------------------------------------------
# Retrieval ranking metrics
# ---------------------------------------------------------------------------


def recall_at_k(retrieved_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """Fraction of gold items found within the first ``k`` retrieved items."""
    if k < 1:
        raise ValueError("k must be positive")
    gold = set(gold_ids)
    if not gold:
        return 0.0
    retrieved = set(retrieved_ids[:k])
    return len(retrieved & gold) / len(gold)


def precision_at_k(retrieved_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """Fraction of the first ``k`` retrieved items that are gold."""
    if k < 1:
        raise ValueError("k must be positive")
    retrieved = set(retrieved_ids[:k])
    if not retrieved:
        return 0.0
    gold = set(gold_ids)
    return len(retrieved & gold) / len(retrieved)


def reciprocal_rank(retrieved_ids: Sequence[str], gold_ids: Sequence[str]) -> float:
    """1/rank of the first gold item in the retrieval list; 0.0 if none found."""
    gold = set(gold_ids)
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in gold:
            return 1.0 / rank
    return 0.0


def average_precision(retrieved_ids: Sequence[str], gold_ids: Sequence[str]) -> float:
    """Mean of the precision values at each gold hit in the retrieval list."""
    gold = set(gold_ids)
    if not gold:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in gold:
            hits += 1
            precision_sum += hits / rank
    return precision_sum / len(gold)


__all__ = [
    "average_precision",
    "check_fabricated_citations",
    "detect_script",
    "domain_adherence",
    "elapsed_seconds",
    "extract_urls",
    "format_latency_ms",
    "groundedness",
    "hallucination_ngram_rate",
    "is_refusal",
    "language_adherence",
    "mean",
    "normalize_text",
    "normalized_exact_match",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "refusal_accuracy",
    "rouge_1",
    "rouge_2",
    "rouge_l",
    "rouge_n",
    "Stopwatch",
    "token_f1",
    "verbatim_snippet_containment",
]