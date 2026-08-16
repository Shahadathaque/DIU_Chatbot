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
        ("Show available programs", QueryIntent.PROGRAM_CATALOG),
        ("Show DIU's official program catalog", QueryIntent.PROGRAM_CATALOG),
        ("am i eligible for bsc in cse?", QueryIntent.ELIGIBILITY),
        ("CSE ar admission condition", QueryIntent.ELIGIBILITY),
        ("kono course er eligibility ki?", QueryIntent.ELIGIBILITY),
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


def test_program_name_is_preserved_in_reformulation() -> None:
    analysis = analyze_query("what is the total fee for CSE?")

    assert analysis.intent is QueryIntent.TUITION
    assert "computer science and engineering" in analysis.retrieval_query.casefold()


def test_unrelated_question_has_no_admission_intent() -> None:
    analysis = analyze_query("What is the weather in Dhaka?")

    assert analysis.intent is None
    assert not analysis.is_admission_query
