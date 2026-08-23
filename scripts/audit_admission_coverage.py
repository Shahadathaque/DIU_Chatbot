#!/usr/bin/env python3
"""Audit every public DIU admission-menu section without weakening retrieval."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.query_processing import QueryIntent, analyze_query  # noqa: E402
from rag.retriever import create_retriever  # noqa: E402
from scraper.registry import load_registry  # noqa: E402


@dataclass(frozen=True)
class CoverageCase:
    section: str
    query: str
    intent: QueryIntent
    categories: frozenset[str]
    variants: tuple[str, ...] = ()


COVERAGE_CASES = (
    CoverageCase("Admission", "Admission information", QueryIntent.ADMISSION_OVERVIEW, frozenset({"admission_overview"}), ("Tell me about DIU admission", "ভর্তি তথ্য", "admisson details")),
    CoverageCase("Admission Test Schedule", "Admission test schedule", QueryIntent.ADMISSION_TEST_SCHEDULE, frozenset({"admission_overview", "admission_notices", "current_admission_information"}), ("When is the admission test?", "bhorti porikkha kobe?", "ভর্তি পরীক্ষার সময়সূচি")),
    CoverageCase("Admission Test Seat Plan", "Admission test seat plan", QueryIntent.ADMISSION_TEST_SEAT_PLAN, frozenset({"admission_test_result", "admission_overview", "admission_notices"}), ("Where is the admission test seat plan?", "seat plan", "ভর্তি পরীক্ষার সিট প্ল্যান")),
    CoverageCase("Admission Test Result", "Admission test result", QueryIntent.ADMISSION_TEST_RESULT, frozenset({"admission_test_result"}), ("Where are the admission test results?", "bhorti test result", "ভর্তি পরীক্ষার ফলাফল")),
    CoverageCase("Admission Contact", "Admission contact", QueryIntent.CONTACT, frozenset({"admission_contact_information"}), ("admission office number", "DIU hotline", "ভর্তি যোগাযোগ")),
    CoverageCase("Programs", "Programs", QueryIntent.PROGRAM_CATALOG, frozenset({"undergraduate_programs"}), ("What programs does DIU offer?", "List all courses", "কি কি প্রোগ্রাম আছে")),
    CoverageCase("Apply Online", "Apply online", QueryIntent.ONLINE_APPLICATION, frozenset({"admission_application_process"}), ("Where is the online admission form?", "online e apply", "অনলাইনে আবেদন")),
    CoverageCase("Admission Eligibility", "Admission eligibility", QueryIntent.ELIGIBILITY, frozenset({"undergraduate_programs"}), ("Can I apply to CSE?", "Do I qualify for SWE?", "আমি কি CSE প্রোগ্রামে ভর্তি হতে পারি?")),
    CoverageCase("Admission Process", "Admission process", QueryIntent.APPLICATION_PROCESS, frozenset({"admission_process"}), ("How do I apply?", "vorti kivabe korbo?", "ভর্তি প্রক্রিয়া")),
    CoverageCase("Admission Checklist and Documents", "Admission checklist and documents", QueryIntent.DOCUMENTS, frozenset({"required_admission_documents"}), ("What papers are required?", "ki ki documents lagbe?", "ভর্তির কাগজপত্র")),
    CoverageCase("Credit Transfer Guidelines", "Credit transfer guidelines", QueryIntent.CREDIT_TRANSFER, frozenset({"credit_transfer_guidelines"}), ("Can I transfer credits?", "credit transfer niyom", "ক্রেডিট ট্রান্সফার নিয়ম")),
    CoverageCase("Guidelines for Guardians", "Guidelines for guardians", QueryIntent.GUARDIAN_GUIDELINES, frozenset({"guardian_guidelines"}), ("Information for parents", "guardian guide", "অভিভাবকদের নির্দেশিকা")),
    CoverageCase("Tuition Fees for Local Students", "Tuition fees for local students", QueryIntent.TUITION, frozenset({"tuition_and_fees"}), ("fees for Bangladeshi students", "total cost of CSE", "দেশি শিক্ষার্থীদের টিউশন ফি")),
    CoverageCase("Tuition Fees for International Students", "Tuition fees for international students", QueryIntent.TUITION, frozenset({"international_admission"}), ("international tuition fees", "fees for foreign students", "বিদেশি শিক্ষার্থীদের টিউশন ফি")),
    CoverageCase("Payment Guidelines for All Students", "Payment guidelines for all students", QueryIntent.PAYMENT_GUIDELINES, frozenset({"payment_guidelines"}), ("How can I pay admission fees?", "payment kivabe korbo", "পেমেন্ট নিয়ম")),
    CoverageCase("Scholarships for Local Students", "Scholarships for local students", QueryIntent.SCHOLARSHIP, frozenset({"scholarships"}), ("Bangladeshi student scholarship", "local scholership", "দেশি শিক্ষার্থীদের স্কলারশিপ")),
    CoverageCase("Scholarships for International Students", "Scholarships for international students", QueryIntent.INTERNATIONAL_SCHOLARSHIP, frozenset({"international_scholarships"}), ("Scholarship International", "funding for foreign applicants", "বিদেশি শিক্ষার্থীদের স্কলারশিপ")),
    CoverageCase("Waivers", "Waiver", QueryIntent.WAIVER, frozenset({"waivers"}), ("tuition discount", "female waever", "ফি ছাড়")),
    CoverageCase("Waiver and Tuition Fee Calculator", "Waiver and tuition fee calculator", QueryIntent.WAIVER_CALCULATOR, frozenset({"waiver_calculator"}), ("calculate my waiver", "waiver hisab", "ওয়েভার ক্যালকুলেটর")),
    CoverageCase("Financial Aid and Scholarship", "Financial aid and scholarship", QueryIntent.FINANCIAL_AID, frozenset({"financial_aid"}), ("financial support", "financial help", "আর্থিক সহায়তা")),
    CoverageCase("Life Insurance", "Life insurance", QueryIntent.LIFE_INSURANCE, frozenset({"life_insurance"}), ("student life insurance", "life insurance details", "জীবন বীমা")),
)


def audit(*, run_retrieval: bool = False) -> list[str]:
    """Return human-readable failures for registry, intent, and optional retrieval."""

    registered_categories = {source.category for source in load_registry()}
    failures: list[str] = []
    retriever = create_retriever() if run_retrieval else None
    for case in COVERAGE_CASES:
        for query in (case.query, *case.variants):
            analysis = analyze_query(query)
            if analysis.intent is not case.intent:
                failures.append(
                    f"{case.section} ({query!r}): intent {analysis.intent!r}, "
                    f"expected {case.intent.value}"
                )
        if not case.categories & registered_categories:
            failures.append(
                f"{case.section}: registry has none of {sorted(case.categories)}"
            )
        if retriever is not None:
            for query in (case.query, *case.variants):
                results = retriever.retrieve(query, top_k=5)
                if not results:
                    failures.append(
                        f"{case.section} ({query!r}): retrieval returned no evidence; "
                        f"expected one of {sorted(case.categories)}"
                    )
                elif not any(
                    result.chunk.category in case.categories for result in results
                ):
                    observed = sorted({result.chunk.category for result in results})
                    failures.append(
                        f"{case.section} ({query!r}): categories {observed}, "
                        f"expected one of {sorted(case.categories)}"
                    )
    return failures


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retrieval",
        action="store_true",
        help="also use the configured real vector store and embedding provider",
    )
    args = parser.parse_args(argv)
    failures = audit(run_retrieval=args.retrieval)
    query_count = sum(1 + len(case.variants) for case in COVERAGE_CASES)
    print(
        f"Admission sections audited: {len(COVERAGE_CASES)} "
        f"({query_count} multilingual/typo/short queries)"
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    mode = "registry + intents + retrieval" if args.retrieval else "registry + intents"
    print(f"PASS: complete admission coverage ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
