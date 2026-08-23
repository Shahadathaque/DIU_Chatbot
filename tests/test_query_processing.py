"""Regression coverage for multilingual admission-query understanding."""

from __future__ import annotations

import pytest

from rag.query_processing import QueryIntent, analyze_query


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("How do I apply?", QueryIntent.APPLICATION_PROCESS),
        ("application process", QueryIntent.APPLICATION_PROCESS),
        ("What steps does DIU's admission flowchart show?", QueryIntent.APPLICATION_PROCESS),
        ("vorti kivabe korbo?", QueryIntent.APPLICATION_PROCESS),
        ("কীভাবে আবেদন করব?", QueryIntent.APPLICATION_PROCESS),
        ("What documents do I need?", QueryIntent.DOCUMENTS),
        ("admission requirement", QueryIntent.DOCUMENTS),
        ("ভর্তির জন্য কী কী কাগজ লাগবে?", QueryIntent.DOCUMENTS),
        ("Can diploma students apply?", QueryIntent.DIPLOMA_APPLICATION),
        ("admission cost", QueryIntent.TUITION),
        ("এডমিশন ফি কত?", QueryIntent.TUITION),
        ("Tell me about scholarships", QueryIntent.SCHOLARSHIP),
        ("scholership", QueryIntent.SCHOLARSHIP),
        ("female waever", QueryIntent.WAIVER),
        ("Show available programs", QueryIntent.PROGRAM_CATALOG),
        ("Show DIU's official program catalog", QueryIntent.PROGRAM_CATALOG),
        ("am i eligible for bsc in cse?", QueryIntent.ELIGIBILITY),
        ("CSE ar admission condition", QueryIntent.ELIGIBILITY),
        ("kono course er eligibility ki?", QueryIntent.ELIGIBILITY),
        ("আমি কি CSE প্রোগ্রামে ভর্তির যোগ্য?", QueryIntent.ELIGIBILITY),
        ("CSE er eligibility ki?", QueryIntent.ELIGIBILITY),
        ("What are the international admission requirements?", QueryIntent.INTERNATIONAL),
        ("DIU te scholarship ba waiver ache?", QueryIntent.WAIVER),
    ],
)
def test_common_query_variants_have_stable_intents(
    query: str, intent: QueryIntent
) -> None:
    analysis = analyze_query(query)

    assert analysis.intent is intent
    assert analysis.retrieval_query
    assert analysis.normalized_query


def test_application_reformulation_is_evidence_oriented() -> None:
    analysis = analyze_query("How do I apply?")

    assert "admission application process" in analysis.retrieval_query.casefold()
    assert "flow" in analysis.retrieval_query.casefold()


def test_waiver_reformulation_corrects_typo_and_preserves_category_focus() -> None:
    analysis = analyze_query("female waever")

    assert analysis.normalized_query == "female waiver"
    assert analysis.intent is QueryIntent.WAIVER
    assert "female waiver" in analysis.retrieval_query.casefold()


def test_typo_correction_does_not_turn_unrelated_words_into_admission_terms() -> None:
    analysis = analyze_query("Recommend a documentary about weather")

    assert analysis.normalized_query == "Recommend a documentary about weather"
    assert analysis.intent is None
    assert not analysis.is_admission_query


def test_program_name_is_preserved_in_reformulation() -> None:
    analysis = analyze_query("what is the total fee for CSE?")

    assert analysis.intent is QueryIntent.TUITION
    assert "computer science and engineering" in analysis.retrieval_query.casefold()


@pytest.mark.parametrize(
    ("query", "canonical"),
    [
        ("Information Technology and Management tuition fees", "Information Technology & Management"),
        ("BBA in Finance and Banking tuition fees", "BBA in Finance & Banking"),
        ("Development Studies tuition fees", "Master of Development Studies"),
        ("M.A. in English tuition fees", "M. A in English"),
        (
            "MSS in Journalism, Media & Communication tuition fees",
            "MSS in Journalism, Media and Communication",
        ),
        ("M Pharm tuition fees", "Master of Pharmacy"),
    ],
)
def test_specific_program_variants_survive_query_reformulation(
    query: str, canonical: str
) -> None:
    analysis = analyze_query(query)

    assert analysis.intent is QueryIntent.TUITION
    assert canonical.casefold() in analysis.retrieval_query.casefold()


def test_unrelated_question_has_no_admission_intent() -> None:
    analysis = analyze_query("What is the weather in Dhaka?")

    assert analysis.intent is None
    assert not analysis.is_admission_query


def test_lowercase_banglish_particle_is_not_a_textile_program_alias() -> None:
    analysis = analyze_query("DIU te scholarship ba waiver ache?")

    assert analysis.intent is QueryIntent.WAIVER
    assert "Textile Engineering" not in analysis.retrieval_query


def test_uppercase_short_program_alias_remains_supported() -> None:
    analysis = analyze_query("TE tuition fees")

    assert analysis.intent is QueryIntent.TUITION
    assert "Textile Engineering" in analysis.retrieval_query


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("আমি কি CSE প্রোগ্রামে ভর্তির যোগ্য?", "bn"),
        ("CSE er eligibility ki?", "banglish"),
    ],
)
def test_eligibility_language_variants_are_detected(
    query: str, language: str
) -> None:
    assert analyze_query(query).language == language
