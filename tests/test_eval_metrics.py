"""Unit tests for the deterministic M5-B evaluation metrics (evaluation.metrics).

No models, no network, no knowledge base required — every test uses small
inline fixtures.
"""

from __future__ import annotations

import time

import pytest

from evaluation.metrics import (
    Stopwatch,
    average_precision,
    check_fabricated_citations,
    detect_script,
    domain_adherence,
    elapsed_seconds,
    extract_urls,
    format_latency_ms,
    groundedness,
    hallucination_ngram_rate,
    is_refusal,
    language_adherence,
    mean,
    normalize_text,
    normalized_exact_match,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_accuracy,
    rouge_1,
    rouge_2,
    rouge_l,
    rouge_n,
    token_f1,
    verbatim_snippet_containment,
)


class TestNormalizationAndExactMatch:
    def test_normalize_text_collapses_and_lowercases(self):
        assert normalize_text("  DIU Admission   Fees! ") == "diu admission fees"

    def test_normalize_text_keeps_bangla(self):
        assert normalize_text("ভর্তি ফি ২০২৬") == "ভর্তি ফি ২০২৬"

    def test_exact_match_ignores_punctuation_and_case(self):
        assert normalized_exact_match("DIU fees.", "diu fees") == 1.0
        assert normalized_exact_match("DIU fees", "DIU tuition") == 0.0


class TestTokenF1:
    def test_identical_is_one(self):
        assert token_f1("the quick fox", "the quick fox") == 1.0

    def test_no_overlap_is_zero(self):
        assert token_f1("alpha beta", "gamma delta") == 0.0

    def test_partial_overlap(self):
        f1 = token_f1("the quick brown fox", "the slow brown dog")
        assert 0.0 < f1 < 1.0

    def test_empty_prediction_is_zero(self):
        assert token_f1("", "some words") == 0.0


class TestRouge:
    def test_rouge_n_rejects_zero(self):
        with pytest.raises(ValueError):
            rouge_n("a b", "a b", 0)

    def test_rouge_1_identical(self):
        result = rouge_1("admission fee", "admission fee")
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_rouge_2_requires_bigrams(self):
        result = rouge_2("single", "single")
        assert result["f1"] == 0.0

    def test_rouge_l_lcs(self):
        result = rouge_l("a b c d", "a x b c d")
        # LCS is "a b c d" (4 of 5 reference tokens)
        assert result["recall"] == pytest.approx(4 / 5)
        assert result["precision"] == 1.0

    def test_rouge_l_no_overlap(self):
        assert rouge_l("a b", "x y")["f1"] == 0.0

    def test_rouge_scores_are_finite(self):
        for fn in (rouge_1, rouge_2, rouge_l):
            result = fn("some prediction text", "some reference")
            assert all(0.0 <= value <= 1.0 for value in result.values())


class TestSnippetContainment:
    def test_full_containment(self):
        assert verbatim_snippet_containment(
            "waiver is 20 percent for siblings", "waiver is 20 percent"
        ) == 1.0

    def test_no_containment(self):
        assert verbatim_snippet_containment("a b c d", "x y z") == 0.0

    def test_short_reference_shrinks_ngram(self):
        assert verbatim_snippet_containment("waiver fee", "waiver fee") == 1.0


class TestGroundednessProxies:
    def test_groundedness_full_support(self):
        evidence = ["tuition fee is 100000 taka per semester"]
        assert groundedness("tuition fee is 100000", evidence) == 1.0

    def test_groundedness_no_evidence_is_zero(self):
        assert groundedness("some answer", []) == 0.0

    def test_hallucination_rate_is_complement(self):
        evidence = ["official waiver policy document"]
        prediction = "completely unrelated text"
        assert hallucination_ngram_rate(prediction, evidence) == pytest.approx(
            1.0 - groundedness(prediction, evidence)
        )

    def test_hallucination_rate_zero_when_supported(self):
        evidence = ["waiver policy official document"]
        assert hallucination_ngram_rate("waiver policy", evidence) < 1.0


class TestCitations:
    def test_extract_urls(self):
        text = "see https://daffodilvarsity.edu.bd/programs and http://example.com/x."
        assert "https://daffodilvarsity.edu.bd/programs" in extract_urls(text)
        assert "http://example.com/x" in extract_urls(text)

    def test_no_fabrication_when_url_allowed(self):
        url = "https://daffodilvarsity.edu.bd/programs"
        result = check_fabricated_citations(f"source {url}", [url])
        assert result["url_count"] == 1
        assert result["fabricated_url_count"] == 0

    def test_fabricated_url_detected(self):
        result = check_fabricated_citations(
            "see https://fake.example.com/page", ["https://daffodilvarsity.edu.bd/programs"]
        )
        assert result["fabricated_url_count"] == 1
        assert result["fabricated_urls"] == ["https://fake.example.com/page"]

    def test_base_condition_any_url_is_fabricated(self):
        result = check_fabricated_citations("visit https://example.com/x", [])
        assert result["fabricated_url_count"] == 1

    def test_punctuation_stripped_from_url(self):
        result = check_fabricated_citations(
            "see https://daffodilvarsity.edu.bd/programs.",
            ["https://daffodilvarsity.edu.bd/programs"],
        )
        assert result["fabricated_url_count"] == 0


class TestRefusalAndDomain:
    def test_refusal_english(self):
        assert is_refusal("I could not find enough verified information.")

    def test_refusal_bangla(self):
        assert is_refusal("পর্যাপ্ত যাচাইকৃত তথ্য পাওয়া যায়নি।")

    def test_refusal_banglish(self):
        assert is_refusal("Apnar proshner uttor dewar jonno ...")

    def test_normal_answer_not_refusal(self):
        assert not is_refusal("CSE tuition fee is 100000 taka per semester.")

    def test_domain_adherence_matches(self):
        assert domain_adherence(expected_refuse=False, refused=False) == 1.0
        assert domain_adherence(expected_refuse=True, refused=True) == 1.0
        assert domain_adherence(expected_refuse=True, refused=False) == 0.0

    def test_refusal_accuracy_alias(self):
        assert refusal_accuracy(detected_refusal=True, expected_refuse=True) == 1.0
        assert refusal_accuracy(detected_refusal=False, expected_refuse=True) == 0.0


class TestLanguageAdherence:
    def test_detect_script(self):
        assert detect_script("ড্যাফোডিল বিশ্ববিদ্যালয়") == "bn"
        assert detect_script("Daffodil University") == "latin"
        assert detect_script("ড্যাফোডিল University") == "mixed"
        assert detect_script("") == "none"

    def test_bangla_request_answered_in_bangla(self):
        assert language_adherence("ভর্তি ফি ১০০০০০ টাকা", "bn") == 1.0

    def test_bangla_request_answered_in_english_fails(self):
        assert language_adherence("tuition fee 100000 taka", "bn") == 0.0

    def test_english_request_answered_in_english(self):
        assert language_adherence("The fee is 100000 taka.", "en") == 1.0

    def test_banglish_is_latin_only(self):
        assert language_adherence("vorti fee 100000 taka", "banglish") == 1.0
        assert language_adherence("ভর্তি ফি", "banglish") == 0.0

    def test_empty_prediction_adherence_zero(self):
        assert language_adherence("", "en") == 0.0


class TestLatencyHelpers:
    def test_stopwatch_measures_time(self):
        with Stopwatch() as stopwatch:
            time.sleep(0.01)
        assert stopwatch.seconds >= 0.0

    def test_elapsed_seconds(self):
        start = time.perf_counter()
        time.sleep(0.01)
        assert elapsed_seconds(start) >= 0.0

    def test_format_latency_ms(self):
        assert format_latency_ms(0.123456) == pytest.approx(123.456)
        assert isinstance(format_latency_ms(0.001), float)


class TestRetrievalMetrics:
    def test_recall_at_k(self):
        assert recall_at_k(["a", "b", "c"], ["a", "x"], 1) == 0.5
        assert recall_at_k(["a", "b", "c"], ["a", "x"], 3) == 0.5
        assert recall_at_k(["a", "b"], ["a", "b"], 10) == 1.0

    def test_recall_empty_gold_is_zero(self):
        assert recall_at_k(["a"], [], 5) == 0.0

    def test_recall_rejects_bad_k(self):
        with pytest.raises(ValueError):
            recall_at_k(["a"], ["a"], 0)

    def test_precision_at_k(self):
        assert precision_at_k(["a", "b", "c"], ["a", "x"], 2) == 0.5
        assert precision_at_k(["a", "b"], ["a", "b"], 5) == 1.0

    def test_reciprocal_rank(self):
        assert reciprocal_rank(["x", "a", "b"], ["a"]) == 0.5
        assert reciprocal_rank(["x", "y"], ["a"]) == 0.0
        assert reciprocal_rank(["a"], ["a"]) == 1.0

    def test_average_precision(self):
        assert average_precision(["a", "x", "b"], ["a", "b"]) == pytest.approx(
            (1.0 + 2 / 3) / 2
        )


class TestMean:
    def test_mean_handles_empty(self):
        assert mean([]) == 0.0

    def test_mean_basic(self):
        assert mean([1.0, 2.0, 3.0]) == 2.0
