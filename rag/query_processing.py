"""Deterministic multilingual query understanding for DIU retrieval.

This module reformulates user wording into stable, evidence-oriented search text.
It never supplies admission facts: every canonical phrase describes only the
kind of official evidence the retriever should look for.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rag.program_resolution import matched_program_phrase


_SPACE_RE = re.compile(r"\s+")
_ASCII_WORD_RE = re.compile(r"[A-Za-z]+")
_DOMAIN_WORDS = frozenset(
    {
        "admission",
        "admissions",
        "application",
        "applications",
        "deadline",
        "deadlines",
        "document",
        "documents",
        "eligibility",
        "eligible",
        "international",
        "program",
        "programs",
        "requirement",
        "requirements",
        "scholarship",
        "scholarships",
        "tuition",
        "waiver",
        "waivers",
    }
)


class QueryIntent(str, Enum):
    APPLICATION_PROCESS = "application_process"
    DOCUMENTS = "documents"
    DIPLOMA_APPLICATION = "diploma_application"
    TUITION = "tuition"
    SCHOLARSHIP = "scholarship"
    WAIVER = "waiver"
    PROGRAM_CATALOG = "program_catalog"
    PROGRAM_INFO = "program_info"
    ELIGIBILITY = "eligibility"
    DEADLINE = "deadline"
    CONTACT = "contact"
    INTERNATIONAL = "international"
    ADMISSION_OVERVIEW = "admission_overview"


@dataclass(frozen=True)
class QueryAnalysis:
    original_query: str
    normalized_query: str
    retrieval_query: str
    intent: Optional[QueryIntent]
    language: str
    is_admission_query: bool


_UNSUPPORTED_PATTERN = re.compile(
    r"(?i)(?:\b(?:my|personal)\s+(?:application|admission)\s+status\b|"
    r"\binsurance\s+documents?\b|"
    r"\b(?:guarantee|secret|unofficial|leaked)\b.*\b(?:admission|scholarship|waiver)\b)"
)
_DOCUMENT_PATTERN = re.compile(
    r"(?i)(?:\b(?:documents?|docs?|papers?|paperwork|certificates?|transcripts?)\b|"
    r"ডকুমেন্ট|কাগজপত্র|কাগজ|সার্টিফিকেট|ট্রান্সক্রিপ্ট|\bkagoj(?:potro)?\b)"
)
_REQUIREMENT_PATTERN = re.compile(
    r"(?i)(?:\b(?:admission\s+)?requirements?\b|ভর্তির\s+শর্ত|কি\s+কি\s+লাগবে|"
    r"\bki\s+ki\s+lagbe\b)"
)
_DIPLOMA_PATTERN = re.compile(r"(?i)\bdiploma\b|ডিপ্লোমা")
_APPLY_PATTERN = re.compile(
    r"(?i)(?:\b(?:apply\w*|application|admission\s+process|application\s+process|"
    r"admission\s+flow(?:chart)?|admission\s+steps?)\b|"
    r"\b(?:vorti|bhorti)\b.*\b(?:kivabe|korbo|hobe)\b|"
    r"কীভাবে\s+আবেদন|কিভাবে\s+আবেদন|আবেদন\s+করব|ভর্তির\s+প্রক্রিয়া)"
)
_ELIGIBILITY_PATTERN = re.compile(
    r"(?i)(?:\b(?:eligible|eligibility|admission\s+condition|admission\s+criteria|"
    r"joggota|jogyota|condition)\b|যোগ্য(?:তা)?|ভর্তির\s+যোগ্য(?:তা)?)"
)
_TUITION_PATTERN = re.compile(
    r"(?i)(?:\b(?:tuition|fees?|cost|payable|total\s+fee|admission\s+fee)\b|"
    r"টিউশন|ফি|খরচ)"
)
_WAIVER_PATTERN = re.compile(r"(?i)\bwaivers?\b|ওয়েভার|ওয়েভার")
_SCHOLARSHIP_PATTERN = re.compile(
    r"(?i)\b(?:scholarships?|financial\s+aid)\b|বৃত্তি|স্কলারশিপ"
)
_PROGRAM_LIST_PATTERN = re.compile(
    r"(?i)(?:\b(?:what|which)\b.*\b(?:programs?|courses?|degrees?)\b|"
    r"\b(?:show|list|available|offered|all)\b.*\b(?:programs?|courses?|degrees?)\b|"
    r"\b(?:programs?|courses?|degrees?)\b.*\b(?:available|offered|list)\b|"
    r"\b(?:programs?|courses?|degrees?)\b.*\b(?:offer|offers)\b|"
    r"\b(?:show|list)\b.*\bprogram\s+catalog\b|\bprogram\s+catalog\b|"
    r"প্রোগ্রাম|কোর্স)"
)
_FACULTY_CATALOG_PATTERN = re.compile(r"(?i)\b(?:facult(?:y|ies)|departments?)\b")
_PROGRAM_WORD_PATTERN = re.compile(r"(?i)\b(?:programs?|courses?|degrees?)\b|প্রোগ্রাম|কোর্স")
_DEADLINE_PATTERN = re.compile(r"(?i)\b(?:deadline|last\s+date|when\s+to\s+apply)\b|শেষ\s+তারিখ")
_CONTACT_PATTERN = re.compile(r"(?i)\b(?:contact|phone|email|address)\b|যোগাযোগ")
_INTERNATIONAL_PATTERN = re.compile(r"(?i)\b(?:international|foreign|overseas)\b|বিদেশি")
_ADMISSION_PATTERN = re.compile(
    r"(?i)(?:\b(?:diu|daffodil|admission|admit|apply\w*|vorti|bhorti)\b|"
    r"ডিআইইউ|ড্যাফোডিল|ভর্তি|আবেদন)"
)


def analyze_query(query: str, *, program_phrase: Optional[str] = None) -> QueryAnalysis:
    """Normalize, classify, and safely reformulate one user question."""

    normalized = _normalize(query)
    detected_program = program_phrase or _program_phrase(normalized)
    language = _language(normalized)
    if _UNSUPPORTED_PATTERN.search(normalized):
        return QueryAnalysis(query, normalized, normalized, None, language, False)

    intent = _intent(normalized, detected_program)
    is_admission = bool(intent is not None or detected_program or _ADMISSION_PATTERN.search(normalized))
    retrieval_query = _canonical_query(intent, detected_program, normalized)
    return QueryAnalysis(
        original_query=query,
        normalized_query=normalized,
        retrieval_query=retrieval_query,
        intent=intent,
        language=language,
        is_admission_query=is_admission,
    )


def _normalize(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query)
    normalized = normalized.replace("’", "'").replace("‘", "'")
    normalized = _ASCII_WORD_RE.sub(_correct_domain_word, normalized)
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    if not normalized:
        raise ValueError("query cannot be blank")
    return normalized


def _correct_domain_word(match: re.Match[str]) -> str:
    """Correct one-edit admission terms without broad fuzzy matching.

    Restricting corrections to a small, stable intent vocabulary prevents an
    unrelated word such as ``documentary`` from becoming ``document`` while
    still accepting ordinary substitutions, missing letters, and adjacent
    transpositions in words such as ``waiver`` and ``scholarship``.
    """

    word = match.group(0)
    folded = word.casefold()
    if folded in _DOMAIN_WORDS or len(folded) < 5:
        return word
    matches = [
        candidate for candidate in _DOMAIN_WORDS if _is_one_edit(folded, candidate)
    ]
    return matches[0] if len(matches) == 1 else word


def _is_one_edit(left: str, right: str) -> bool:
    """Return whether two words differ by one Damerau-Levenshtein edit."""

    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = [
            index
            for index, pair in enumerate(zip(left, right))
            if pair[0] != pair[1]
        ]
        if len(differences) == 1:
            return True
        return bool(
            len(differences) == 2
            and differences[1] == differences[0] + 1
            and left[differences[0]] == right[differences[1]]
            and left[differences[1]] == right[differences[0]]
        )
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = long_index = 0
    skipped = False
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        if skipped:
            return False
        skipped = True
        long_index += 1
    return True


def _language(query: str) -> str:
    if re.search(r"[\u0980-\u09ff]", query):
        return "bn"
    if re.search(
        r"(?i)\b(?:vorti|bhorti|kivabe|korbo|lagbe|koto|joggota|jogyota|"
        r"kono|ache|ar|ami|ki|er|jonno)\b",
        query,
    ):
        return "banglish"
    return "en"


def _program_phrase(query: str) -> Optional[str]:
    return matched_program_phrase(query)


def _intent(query: str, program_phrase: Optional[str]) -> Optional[QueryIntent]:
    if _DIPLOMA_PATTERN.search(query) and (_APPLY_PATTERN.search(query) or _ELIGIBILITY_PATTERN.search(query)):
        return QueryIntent.DIPLOMA_APPLICATION
    if _WAIVER_PATTERN.search(query):
        return QueryIntent.WAIVER
    if _SCHOLARSHIP_PATTERN.search(query):
        return QueryIntent.SCHOLARSHIP
    if _TUITION_PATTERN.search(query):
        return QueryIntent.TUITION
    if _ELIGIBILITY_PATTERN.search(query) or (program_phrase and _REQUIREMENT_PATTERN.search(query)):
        return QueryIntent.ELIGIBILITY
    if _INTERNATIONAL_PATTERN.search(query):
        return QueryIntent.INTERNATIONAL
    if _DOCUMENT_PATTERN.search(query) or (_REQUIREMENT_PATTERN.search(query) and not program_phrase):
        return QueryIntent.DOCUMENTS
    if _APPLY_PATTERN.search(query):
        return QueryIntent.APPLICATION_PROCESS
    if _DEADLINE_PATTERN.search(query):
        return QueryIntent.DEADLINE
    if _CONTACT_PATTERN.search(query):
        return QueryIntent.CONTACT
    if _PROGRAM_LIST_PATTERN.search(query) or (
        program_phrase is None and _FACULTY_CATALOG_PATTERN.search(query)
    ):
        return QueryIntent.PROGRAM_CATALOG
    if program_phrase or _PROGRAM_WORD_PATTERN.search(query):
        return QueryIntent.PROGRAM_INFO
    if _ADMISSION_PATTERN.search(query):
        return QueryIntent.ADMISSION_OVERVIEW
    return None


def _canonical_query(
    intent: Optional[QueryIntent], program_phrase: Optional[str], original: str
) -> str:
    program = " {}".format(program_phrase) if program_phrase else ""
    tuition_query = (
        "DIU international student tuition fees USD total program fees cost{}"
        if _INTERNATIONAL_PATTERN.search(original)
        else "DIU local student tuition fees payable during admission total program fees cost{}"
    ).format(program)
    canonical = {
        QueryIntent.APPLICATION_PROCESS: "DIU admission application process flow online apply new applicant",
        QueryIntent.DOCUMENTS: "DIU required admission documents checklist certificate transcript online application",
        QueryIntent.DIPLOMA_APPLICATION: "Online Admission Form Local Bachelor Program Diploma Apply Type",
        QueryIntent.TUITION: tuition_query,
        QueryIntent.SCHOLARSHIP: "DIU financial aid scholarships local students scholarship categories",
        QueryIntent.WAIVER: "DIU official waiver policy tuition fee waiver categories{}".format(program),
        QueryIntent.PROGRAM_CATALOG: "DIU complete program catalog across all faculties programs offered",
        QueryIntent.PROGRAM_INFO: "DIU official program catalog{} program details".format(program),
        QueryIntent.ELIGIBILITY: "DIU{} program eligibility verification official program catalog".format(program),
        QueryIntent.DEADLINE: "DIU current admission notice application deadline last date",
        QueryIntent.CONTACT: "DIU official admission contact phone email address",
        QueryIntent.INTERNATIONAL: "DIU international student admission policy tuition contact",
        QueryIntent.ADMISSION_OVERVIEW: "DIU official admission information overview",
    }.get(intent)
    if canonical and intent in {QueryIntent.SCHOLARSHIP, QueryIntent.WAIVER}:
        canonical = _preserve_user_focus(canonical, original)
    return _SPACE_RE.sub(" ", canonical or original).strip()


def _preserve_user_focus(canonical: str, original: str) -> str:
    """Keep a user's non-factual category qualifier in the retrieval query."""

    if original.casefold() in canonical.casefold():
        return canonical
    return "{} user focus {}".format(canonical, original)
