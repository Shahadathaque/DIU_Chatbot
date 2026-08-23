#!/usr/bin/env python3
"""Audit adversarial intent, program, level, scope, and follow-up resolution."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.chat import ChatTurn  # noqa: E402
from backend.services.chat_service import resolve_followup  # noqa: E402
from rag.program_resolution import (  # noqa: E402
    matched_program_phrase,
    named_program_markers,
)
from rag.query_processing import QueryIntent, analyze_query  # noqa: E402
from rag.retriever import is_explicitly_out_of_domain  # noqa: E402


@dataclass(frozen=True)
class IntentCase:
    group: str
    query: str
    expected_intent: Optional[QueryIntent]
    expected_program_contains: Optional[str] = None
    expected_admission: bool = True
    expected_out_of_domain: bool = False


INTENT_CASES = (
    IntentCase("short", "waiver", QueryIntent.WAIVER),
    IntentCase("short", "payment", QueryIntent.PAYMENT_GUIDELINES),
    IntentCase("short", "insurance", QueryIntent.LIFE_INSURANCE),
    IntentCase("short", "result", QueryIntent.ADMISSION_TEST_RESULT),
    IntentCase("short", "schedule", QueryIntent.ADMISSION_TEST_SCHEDULE),
    IntentCase("short", "seatplan", QueryIntent.ADMISSION_TEST_SEAT_PLAN),
    IntentCase("typo", "female waever", QueryIntent.WAIVER),
    IntentCase("typo", "scholership", QueryIntent.SCHOLARSHIP),
    IntentCase("scope", "Scholarship International", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
    IntentCase("scope", "আন্তর্জাতিক শিক্ষার্থীদের বৃত্তি", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
    IntentCase("conflict", "financial aid and scholarships", QueryIntent.FINANCIAL_AID),
    IntentCase("conflict", "waiver and tuition fee calculator", QueryIntent.WAIVER_CALCULATOR),
    IntentCase("fact", "Does every undergraduate student receive a free laptop?", QueryIntent.FACT_CHECK),
    IntentCase("fact", "Does every undergraduate student receive a scholarship?", QueryIntent.FACT_CHECK),
    IntentCase("deadline", "Last Date to Apply", QueryIntent.DEADLINE),
    IntentCase("deadline", "current admission notice", QueryIntent.DEADLINE),
    IntentCase("schedule", "Faculty of Science and Information Technology admission test time and date", QueryIntent.ADMISSION_TEST_SCHEDULE),
    IntentCase("international", "Can a foreign student apply?", QueryIntent.INTERNATIONAL),
    IntentCase("documents", "What documents are required for bachelor admission?", QueryIntent.DOCUMENTS),
    IntentCase("payment", "How can I pay my admission fee?", QueryIntent.PAYMENT_GUIDELINES),
    IntentCase("payment", "tuition fee payment", QueryIntent.PAYMENT_GUIDELINES),
    IntentCase("payment", "admission fee kivabe dibo", QueryIntent.PAYMENT_GUIDELINES),
    IntentCase("transfer", "Can I transfer credits?", QueryIntent.CREDIT_TRANSFER),
    IntentCase("guardian", "Information for parents", QueryIntent.GUARDIAN_GUIDELINES),
    IntentCase("program", "Does DIU offer New Program?", QueryIntent.PROGRAM_INFO),
    IntentCase("mixed-language", "international student er jonno scholarship ache?", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
    IntentCase("mixed-language", "bideshi student scholarship", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
    IntentCase("bangla", "কিভাবে ভর্তি হব", QueryIntent.APPLICATION_PROCESS),
    IntentCase("bangla", "ভর্তি পরীক্ষার ফল", QueryIntent.ADMISSION_TEST_RESULT),
    IntentCase("normalization", "on-line admission form", QueryIntent.ONLINE_APPLICATION),
    IntentCase("natural-tuition", "How much do I pay for CSE?", QueryIntent.TUITION, "Computer Science and Engineering"),
    IntentCase("emoji", "CSE tuition fee? 🎓", QueryIntent.TUITION, "Computer Science and Engineering"),
    IntentCase("ood", "What is NSU tuition?", QueryIntent.TUITION, expected_out_of_domain=True),
)


PROGRAM_CASES = (
    ("Information Technology", "Information Technology & Management"),
    ("Information Technology and Management tuition fees", "Information Technology & Management"),
    ("BBA in Finance and Banking tuition fees", "Finance & Banking"),
    ("Development Studies tuition fees", "Development Studies"),
    ("MA in English tuition fees", "M. A in English"),
    ("MSS in Journalism Media and Communication tuition fees", "MSS in Journalism"),
    ("Master of Pharmacy tuition fees", "Master of Pharmacy"),
    ("M Pharm tuition fees", "Master of Pharmacy"),
    ("LLM tuition fees", "LL.M."),
    ("JMC tuition fees", "Journalism, Media and Communication"),
)


MARKER_CASES = (
    ("CSE and Master of Pharmacy tuition fees", ("cse", "mpharm")),
    ("BBA and BBA in Finance and Banking tuition fees", ("bba", "bba_finance")),
    ("Information Technology and Management tuition fees", ("itm",)),
    ("MA in English tuition fees", ("ma_english",)),
)


FOLLOWUP_CASES = (
    (
        "international fee context",
        "What about international students?",
        ("What is the tuition fee of CSE?",),
        ("Computer Science and Engineering", "tuition fee"),
        (),
    ),
    (
        "program switch",
        "What about SWE?",
        ("What is the tuition fee of CSE?",),
        ("Software Engineering", "tuition fee"),
        ("Computer Science and Engineering",),
    ),
    (
        "explicit topic switch",
        "Tell me about scholarships",
        ("What is the tuition fee of CSE?",),
        (),
        ("Computer Science and Engineering", "tuition fee"),
    ),
    (
        "diploma document context",
        "What about diploma students?",
        ("What documents do I need?",),
        ("required admission documents",),
        (),
    ),
    (
        "faculty topic reset",
        "what about fsit department",
        ("scholarship",),
        (),
        ("scholarship",),
    ),
)


def audit() -> dict[str, object]:
    failures: list[dict[str, object]] = []
    passed = 0

    for case in INTENT_CASES:
        analysis = analyze_query(case.query)
        actual_program = matched_program_phrase(case.query)
        checks = {
            "intent": analysis.intent is case.expected_intent,
            "admission_scope": analysis.is_admission_query is case.expected_admission,
            "out_of_domain": is_explicitly_out_of_domain(case.query)
            is case.expected_out_of_domain,
            "program": case.expected_program_contains is None
            or (
                actual_program is not None
                and case.expected_program_contains.casefold() in actual_program.casefold()
            ),
        }
        if all(checks.values()):
            passed += 1
        else:
            failures.append(
                {
                    "group": case.group,
                    "query": case.query,
                    "expected_intent": case.expected_intent.value if case.expected_intent else None,
                    "actual_intent": analysis.intent.value if analysis.intent else None,
                    "expected_program_contains": case.expected_program_contains,
                    "actual_program": actual_program,
                    "expected_admission": case.expected_admission,
                    "actual_admission": analysis.is_admission_query,
                    "expected_out_of_domain": case.expected_out_of_domain,
                    "actual_out_of_domain": is_explicitly_out_of_domain(case.query),
                    "checks": checks,
                }
            )

    for query, expected in PROGRAM_CASES:
        actual = matched_program_phrase(query)
        if actual is not None and expected.casefold() in actual.casefold():
            passed += 1
        else:
            failures.append(
                {
                    "group": "program-resolution",
                    "query": query,
                    "expected_program_contains": expected,
                    "actual_program": actual,
                }
            )

    for query, expected_markers in MARKER_CASES:
        actual_markers = tuple(named_program_markers(query))
        if actual_markers == expected_markers:
            passed += 1
        else:
            failures.append(
                {
                    "group": "multi-program-resolution",
                    "query": query,
                    "expected_markers": expected_markers,
                    "actual_markers": actual_markers,
                }
            )

    for name, query, prior_queries, required, forbidden in FOLLOWUP_CASES:
        history: list[ChatTurn] = []
        for prior in prior_queries:
            history.extend(
                [
                    ChatTurn(role="user", content=prior),
                    ChatTurn(role="assistant", content="Verified prior response."),
                ]
            )
        actual = resolve_followup(query, history)
        if all(value in actual for value in required) and not any(
            value in actual for value in forbidden
        ):
            passed += 1
        else:
            failures.append(
                {
                    "group": "follow-up",
                    "name": name,
                    "query": query,
                    "expected_contains": required,
                    "expected_excludes": forbidden,
                    "actual": actual,
                }
            )

    total = (
        len(INTENT_CASES)
        + len(PROGRAM_CASES)
        + len(MARKER_CASES)
        + len(FOLLOWUP_CASES)
    )
    return {
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
