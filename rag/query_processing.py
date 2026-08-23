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

from rag.faculty_resolution import matched_faculty_phrase
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
        "faculty",
        "faculties",
        "document",
        "documents",
        "guardian",
        "guardians",
        "guideline",
        "guidelines",
        "insurance",
        "eligibility",
        "eligible",
        "international",
        "local",
        "payment",
        "notice",
        "notices",
        "program",
        "programs",
        "student",
        "students",
        "undergraduate",
        "postgraduate",
        "requirement",
        "requirements",
        "result",
        "results",
        "schedule",
        "scholarship",
        "scholarships",
        "transfer",
        "tuition",
        "waiver",
        "waivers",
    }
)


class QueryIntent(str, Enum):
    APPLICATION_PROCESS = "application_process"
    ONLINE_APPLICATION = "online_application"
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
    INTERNATIONAL_SCHOLARSHIP = "international_scholarship"
    ADMISSION_TEST_SCHEDULE = "admission_test_schedule"
    ADMISSION_TEST_SEAT_PLAN = "admission_test_seat_plan"
    ADMISSION_TEST_RESULT = "admission_test_result"
    CREDIT_TRANSFER = "credit_transfer"
    GUARDIAN_GUIDELINES = "guardian_guidelines"
    PAYMENT_GUIDELINES = "payment_guidelines"
    WAIVER_CALCULATOR = "waiver_calculator"
    FINANCIAL_AID = "financial_aid"
    LIFE_INSURANCE = "life_insurance"
    ADMISSION_OVERVIEW = "admission_overview"
    FACT_CHECK = "fact_check"


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
    r"\bki\s+ki\s+lagbe\b|"
    r"\bwhat\s+(?:documents?\s+)?do\s+i\s+need\b.*\b(?:admission|apply|enrol|enroll)\b)"
)
_DIPLOMA_PATTERN = re.compile(r"(?i)\bdiploma\b|ডিপ্লোমা")
_APPLY_PATTERN = re.compile(
    r"(?i)(?:\b(?:apply\w*|application|admission\s+process|application\s+process|"
    r"admission\s+flow(?:chart)?|admission\s+steps?)\b|"
    r"\b(?:how|where)\s+(?:do\s+i\s+|can\s+i\s+|to\s+)?(?:enrol|enroll|register)\b|"
    r"\b(?:vorti|bhorti)\b.*\b(?:kivabe|korbo|hobe)\b|"
    r"কীভাবে\s+(?:আবেদন|ভর্তি)|কিভাবে\s+(?:আবেদন|ভর্তি)|আবেদন\s+করব|"
    r"ভর্তি(?:র)?\s+প্রক্রিয়া)"
)
_ONLINE_APPLICATION_PATTERN = re.compile(
    r"(?i)(?:\b(?:apply\s+online|online\s+(?:application|admission(?:\s+form)?|form))\b|"
    r"অনলাইন(?:ে)?\s+আবেদন|\bonline(?:\s+e)?\s+(?:apply|abedon)\b)"
)
_ELIGIBILITY_PATTERN = re.compile(
    r"(?i)(?:\b(?:eligible|eligibility|admission\s+condition|admission\s+criteria|"
    r"joggota|jogyota|condition)\b|যোগ্য(?:তা)?|ভর্তির\s+যোগ্য(?:তা)?)"
)
_PROGRAM_ELIGIBILITY_QUESTION_PATTERN = re.compile(
    r"(?i)(?:\b(?:can|may)\s+i\s+(?:apply|join|enrol|enroll|get\s+admitted)\b|"
    r"\bdo\s+i\s+qualify\b|\bamar\s+(?:joggota|jogyota)\b|আমি\s+কি.*(?:আবেদন|ভর্তি))"
)
_TUITION_PATTERN = re.compile(
    r"(?i)(?:\b(?:tuition|fees?|cost|payable|total\s+fee|admission\s+fee)\b|"
    r"\bhow\s+much\b.*\bpay\b|"
    r"টিউশন|ফি|খরচ)"
)
_WAIVER_PATTERN = re.compile(
    r"(?i)\bwaivers?\b|\b(?:tuition|fee)\s+(?:discount|concession)\b|"
    r"ওয়েভার|ওয়েভার|ফি\s+ছাড়"
)
_SCHOLARSHIP_PATTERN = re.compile(
    r"(?i)\b(?:scholarships?|financial\s+aid)\b|বৃত্তি|স্কলারশিপ"
)
_UNIVERSAL_FUNDING_CLAIM_PATTERN = re.compile(
    r"(?i)(?:\b(?:all|every|everyone|guaranteed|guarantee)\b.*"
    r"\b(?:scholarships?|waivers?|financial\s+aid)\b|"
    r"\b(?:scholarships?|waivers?|financial\s+aid)\b.*"
    r"\b(?:all|every|everyone|guaranteed|guarantee)\b)"
)
_INTERNATIONAL_SCHOLARSHIP_PATTERN = re.compile(
    r"(?i)(?=.*(?:\binternational\b|\bforeign\b|\bbideshi\b|বিদেশি|আন্তর্জাতিক))"
    r"(?=.*(?:\bscholarships?\b|\b(?:funding|grants?)\b|বৃত্তি|স্কলারশিপ))"
)
_FINANCIAL_AID_PATTERN = re.compile(
    r"(?i)\bfinancial\s+(?:aid|support|assistance)\b|আর্থিক\s+(?:সহায়তা|সহায়তা)|"
    r"\bfinancial\s+help\b"
)
_WAIVER_CALCULATOR_PATTERN = re.compile(
    r"(?i)(?:\b(?:waiver|tuition\s+fee)\s+calculator\b|"
    r"\bcalculate\b.*\b(?:waiver|tuition|fees?)\b|"
    r"ওয়েভার\s+ক্যালকুলেটর|ওয়েভার\s+ক্যালকুলেটর|"
    r"\bwaiver\s+hisab\b)"
)
_ADMISSION_TEST_SEAT_PLAN_PATTERN = re.compile(
    r"(?i)(?:\b(?:admission\s+test\s+)?seat\s+plan\b|"
    r"ভর্তি\s+পরীক্ষার\s+সিট\s+প্ল্যান|\b(?:vorti|bhorti)\s+seat\s+plan\b)"
)
_ADMISSION_TEST_RESULT_PATTERN = re.compile(
    r"(?i)(?:^\s*results?\s*[?.!]*\s*$|\badmission\s+test\s+results?\b|"
    r"ভর্তি\s+পরীক্ষার\s+(?:ফলাফল|ফল)|\b(?:vorti|bhorti)\s+(?:test\s+)?result\b)"
)
_ADMISSION_TEST_SCHEDULE_PATTERN = re.compile(
    r"(?i)(?:^\s*schedule\s*[?.!]*\s*$|"
    r"\badmission\s+test\s+(?:schedule|date|time)\b|"
    r"\bwhen\b.*\badmission\s+test\b|\badmission\s+test\b.*\bwhen\b|"
    r"ভর্তি\s+পরীক্ষার\s+(?:সময়সূচি|তারিখ)|"
    r"ভর্তি\s+পরীক্ষা.*কবে|"
    r"\b(?:vorti|bhorti)\s+(?:test|porikkha)\s+(?:schedule|date|time|kobe)\b)"
)
_CREDIT_TRANSFER_PATTERN = re.compile(
    r"(?i)\bcredit\s+transfer(?:\s+guidelines?)?\b|\btransfer(?:ring)?\s+credits?\b|ক্রেডিট\s+ট্রান্সফার|"
    r"\bcredit\s+transfer\s+(?:niyom|rule)\b"
)
_GUARDIAN_GUIDELINES_PATTERN = re.compile(
    r"(?i)(?:\b(?:guidelines?\s+for\s+)?(?:guardians?|parents?)\b|"
    r"অভিভাবক(?:দের)?\s+(?:নির্দেশিকা|নির্দেশনা)|"
    r"\bguardian\s+(?:niyom|guide)\b)"
)
_PAYMENT_GUIDELINES_PATTERN = re.compile(
    r"(?i)(?:^\s*payments?\s*[?.!]*\s*$|"
    r"\bpayment\s+(?:guidelines?|instructions?|process|methods?)\b|"
    r"\bhow\s+(?:(?:do|can|should)\s+(?:i|we)\s+|to\s+)?pay\b|"
    r"\bpay(?:ing)?\s+(?:the\s+)?(?:admission|tuition|semester)\s+fees?\b|"
    r"\b(?:admission|tuition|semester|program)\s+fees?\s+payments?\b|"
    r"\bfees?\s+payments?\s+(?:method|process|instructions?)\b|"
    r"পেমেন্ট\s+(?:নির্দেশিকা|নিয়ম|নিয়ম)|"
    r"(?:ফি|টাকা).*?(?:কীভাবে|কিভাবে).*?(?:দেব|দিব)|"
    r"\b(?:fees?|payment|pay)\b.*\b(?:kivabe|dibo|korbo)\b|"
    r"\bpayment\s+(?:niyom|kivabe)\b)"
)
_LIFE_INSURANCE_PATTERN = re.compile(
    r"(?i)(?:^\s*insurance\s*[?.!]*\s*$|"
    r"\b(?:student|guardian|student\s+and\s+guardian)?\s*life\s+insurance\b|"
    r"জীবন\s+বীমা|লাইফ\s+ইন্স্যুরেন্স|\blife\s+insurance\s+(?:ache|details?)\b)"
)
_PROGRAM_LIST_PATTERN = re.compile(
    r"(?i)(?:^\s*(?:programs?|courses?|degrees?)\s*[?.!]*\s*$|"
    r"\b(?:what|which)\b.*\b(?:programs|courses|degrees)\b|"
    r"\b(?:show|list|name)\b.*\b(?:programs?|courses?|degrees?)\b|"
    r"\bhow\s+many\b.*\b(?:programs?|courses?|degrees?)\b|"
    r"\ball\s+(?:diu\s+)?(?:undergraduate\s+|postgraduate\s+|graduate\s+)?"
    r"(?:programs?|courses?|degrees?)\b|"
    r"\b(?:programs?|courses?|degrees?)\b.*\b(?:available|offered|list)\b|"
    r"\b(?:programs?|courses?|degrees?)\b.*\b(?:offer|offers)\b|"
    r"\b(?:show|list)\b.*\bprogram\s+catalog\b|\bprogram\s+catalog\b|"
    r"(?:কি\s+কি|কোন\s+কোন).*?(?:প্রোগ্রাম|কোর্স)|"
    r"(?:প্রোগ্রাম|কোর্স).*?(?:তালিকা|কি\s+কি|আছে)|"
    r"\b(?:ki\s+ki|kon\s+kon)\b.*\b(?:programs?|courses?)\b|"
    r"\b(?:programs?|courses?)\b.*\b(?:ki\s+ki|gulo|ache)\b)"
)
_FACULTY_CATALOG_PATTERN = re.compile(r"(?i)\b(?:facult(?:y|ies)|departments?)\b")
_PROGRAM_INFO_PATTERN = re.compile(
    r"(?i)(?:\b(?:program|course|degree)\s+(?:information|info|details?|duration|"
    r"credits?|curriculum|faculty|department)\b|"
    r"\b(?:information|info|details?|duration|credits?|curriculum)\b.*"
    r"\b(?:program|course|degree)\b|"
    r"\bdoes\s+(?:diu|daffodil)\s+offer\b.*\b(?:program|course|degree)\b|"
    r"\bis\b.*\b(?:program|course|degree)\b.*\b(?:available|offered)\b|"
    r"(?:প্রোগ্রাম|কোর্স).*(?:তথ্য|বিস্তারিত|সময়কাল))"
)
_DEADLINE_PATTERN = re.compile(
    r"(?i)\b(?:deadline|last\s+date|closing\s+date|when\s+to\s+apply|"
    r"current\s+admission\s+notices?|admission\s+notices?)\b|শেষ\s+তারিখ"
)
_CONTACT_PATTERN = re.compile(
    r"(?i)\b(?:contact|phone|email|address|helpline|hotline|office\s+number)\b|যোগাযোগ"
)
_INTERNATIONAL_PATTERN = re.compile(
    r"(?i)\b(?:international|foreign|overseas|bideshi|student\s+visa|passport)\b|"
    r"বিদেশি|আন্তর্জাতিক"
)
_LOCAL_AUDIENCE_PATTERN = re.compile(
    r"(?i)\b(?:local|domestic|bangladeshi|bangladesh(?:i)?\s+students?)\b|"
    r"স্থানীয়|স্থানীয়|বাংলাদেশি"
)
_LOCAL_CURRENCY_PATTERN = re.compile(r"(?i)(?:\b(?:bdt|taka|tk\.?)\b|৳)")
_INTERNATIONAL_CURRENCY_PATTERN = re.compile(r"(?i)(?:\b(?:usd|dollars?)\b|\$)")
_ADMISSION_OVERVIEW_PATTERN = re.compile(
    r"(?i)(?:^\s*(?:diu\s+)?admissions?\s*[?.!]*\s*$|"
    r"\badmission\s+(?:information|info|details?|overview)\b|"
    r"\b(?:information|details?|overview)\s+(?:about|on|of)\s+(?:diu\s+)?admissions?\b|"
    r"\btell\s+me\s+about\s+(?:diu\s+)?admissions?\b|ভর্তি\s+(?:তথ্য|বিস্তারিত))"
)
_DOMAIN_ANCHOR_PATTERN = re.compile(
    r"(?i)(?:\b(?:diu|daffodil|admissions?|applicants?|students?|undergraduates?|"
    r"postgraduates?|programs?|courses?|degrees?|facult(?:y|ies)|departments?|"
    r"campus|semesters?)\b|ডিআইইউ|ড্যাফোডিল|ভর্তি|শিক্ষার্থী|প্রোগ্রাম|কোর্স)"
)
_ADMISSION_PATTERN = re.compile(
    r"(?i)(?:\b(?:diu|daffodil|admission|admit|apply\w*|vorti|bhorti)\b|"
    r"ডিআইইউ|ড্যাফোডিল|ভর্তি|আবেদন)"
)


def analyze_query(query: str, *, program_phrase: Optional[str] = None) -> QueryAnalysis:
    """Normalize, classify, and safely reformulate one user question."""

    normalized = _normalize(query)
    detected_faculty = matched_faculty_phrase(normalized)
    # Exact faculty wording is stronger than a partial program-name fragment.
    # For example, Agriculture Sciences is a faculty while Agricultural
    # Science is also a program; the bare official faculty label must route to
    # the catalog rather than the similarly named program.
    detected_program = (
        None
        if detected_faculty
        else (program_phrase or _program_phrase(normalized))
    )
    language = _language(normalized)
    if _UNSUPPORTED_PATTERN.search(normalized):
        return QueryAnalysis(query, normalized, normalized, None, language, False)

    intent = _intent(normalized, detected_program, detected_faculty)
    is_admission = bool(
        intent is not None
        or detected_program
        or detected_faculty
        or _ADMISSION_PATTERN.search(normalized)
        or _DOMAIN_ANCHOR_PATTERN.search(normalized)
    )
    retrieval_query = _canonical_query(
        intent, detected_program, normalized, faculty_phrase=detected_faculty
    )
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
    # Treat separators as word boundaries for intent phrases. Program matching
    # has its own punctuation-safe canonicalizer, so this does not alter names
    # such as M.A. or Finance & Banking.
    normalized = re.sub(r"[-_/]+", " ", normalized)
    normalized = re.sub(r"(?i)\bseat\s*plan\b", "seat plan", normalized)
    normalized = re.sub(r"(?i)\bon\s+line\b", "online", normalized)
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


def _intent(
    query: str,
    program_phrase: Optional[str],
    faculty_phrase: Optional[str] = None,
) -> Optional[QueryIntent]:
    if _ADMISSION_TEST_SEAT_PLAN_PATTERN.search(query):
        return QueryIntent.ADMISSION_TEST_SEAT_PLAN
    if _ADMISSION_TEST_RESULT_PATTERN.search(query):
        return QueryIntent.ADMISSION_TEST_RESULT
    if _ADMISSION_TEST_SCHEDULE_PATTERN.search(query):
        return QueryIntent.ADMISSION_TEST_SCHEDULE
    if _CREDIT_TRANSFER_PATTERN.search(query):
        return QueryIntent.CREDIT_TRANSFER
    if _GUARDIAN_GUIDELINES_PATTERN.search(query):
        return QueryIntent.GUARDIAN_GUIDELINES
    if _PAYMENT_GUIDELINES_PATTERN.search(query):
        return QueryIntent.PAYMENT_GUIDELINES
    if _LIFE_INSURANCE_PATTERN.search(query):
        return QueryIntent.LIFE_INSURANCE
    if _WAIVER_CALCULATOR_PATTERN.search(query):
        return QueryIntent.WAIVER_CALCULATOR
    if _INTERNATIONAL_SCHOLARSHIP_PATTERN.search(query):
        return QueryIntent.INTERNATIONAL_SCHOLARSHIP
    if _FINANCIAL_AID_PATTERN.search(query):
        return QueryIntent.FINANCIAL_AID
    if _DIPLOMA_PATTERN.search(query) and (_APPLY_PATTERN.search(query) or _ELIGIBILITY_PATTERN.search(query)):
        return QueryIntent.DIPLOMA_APPLICATION
    if _DOCUMENT_PATTERN.search(query) or (
        _REQUIREMENT_PATTERN.search(query)
        and not program_phrase
        and not _INTERNATIONAL_PATTERN.search(query)
    ):
        return QueryIntent.DOCUMENTS
    if _ONLINE_APPLICATION_PATTERN.search(query):
        return QueryIntent.ONLINE_APPLICATION
    if _UNIVERSAL_FUNDING_CLAIM_PATTERN.search(query):
        return QueryIntent.FACT_CHECK
    if _WAIVER_PATTERN.search(query):
        return QueryIntent.WAIVER
    if _SCHOLARSHIP_PATTERN.search(query):
        return QueryIntent.SCHOLARSHIP
    if _TUITION_PATTERN.search(query) or (
        program_phrase
        and re.search(
            r"(?i)(?:\b(?:price|amount|total)\b|\bhow\s+much\b.*\bpay\b|"
            r"\bkoto\b.*\b(?:pay|lagbe|dite|dib[o]?)\b)",
            query,
        )
    ):
        return QueryIntent.TUITION
    if (
        _ELIGIBILITY_PATTERN.search(query)
        or (
            program_phrase
            and (
                _REQUIREMENT_PATTERN.search(query)
                or _PROGRAM_ELIGIBILITY_QUESTION_PATTERN.search(query)
            )
        )
    ):
        return QueryIntent.ELIGIBILITY
    if _DEADLINE_PATTERN.search(query):
        return QueryIntent.DEADLINE
    if _INTERNATIONAL_PATTERN.search(query):
        return QueryIntent.INTERNATIONAL
    if _APPLY_PATTERN.search(query):
        return QueryIntent.APPLICATION_PROCESS
    if _CONTACT_PATTERN.search(query):
        return QueryIntent.CONTACT
    if faculty_phrase or _PROGRAM_LIST_PATTERN.search(query) or (
        program_phrase is None and _FACULTY_CATALOG_PATTERN.search(query)
    ):
        return QueryIntent.PROGRAM_CATALOG
    if program_phrase or _PROGRAM_INFO_PATTERN.search(query):
        return QueryIntent.PROGRAM_INFO
    if _ADMISSION_OVERVIEW_PATTERN.search(query):
        return QueryIntent.ADMISSION_OVERVIEW
    if _DOMAIN_ANCHOR_PATTERN.search(query):
        return QueryIntent.FACT_CHECK
    return None


def _canonical_query(
    intent: Optional[QueryIntent],
    program_phrase: Optional[str],
    original: str,
    *,
    faculty_phrase: Optional[str] = None,
) -> str:
    program = " {}".format(program_phrase) if program_phrase else ""
    audience = tuition_audience(original)
    if audience == "both":
        tuition_query = (
            "DIU local student tuition fees BDT and international student tuition fees "
            "USD total program fees cost{}"
        ).format(program)
    elif audience == "international":
        tuition_query = (
            "DIU international student tuition fees USD total program fees cost{}"
        ).format(program)
    else:
        tuition_query = (
            "DIU local student tuition fees payable during admission total program fees cost{}"
        ).format(program)
    canonical = {
        QueryIntent.APPLICATION_PROCESS: "DIU admission application process flow online apply new applicant",
        QueryIntent.ONLINE_APPLICATION: "DIU official online admission form apply online application portal",
        QueryIntent.DOCUMENTS: "DIU required admission documents checklist certificate transcript online application",
        QueryIntent.DIPLOMA_APPLICATION: "Online Admission Form Local Bachelor Program Diploma Apply Type",
        QueryIntent.TUITION: tuition_query,
        QueryIntent.SCHOLARSHIP: "DIU financial aid scholarships local students scholarship categories",
        QueryIntent.WAIVER: "DIU official waiver policy tuition fee waiver categories{}".format(program),
        QueryIntent.PROGRAM_CATALOG: (
            "DIU official program catalog {} faculty programs offered".format(
                faculty_phrase
            )
            if faculty_phrase
            else "DIU complete program catalog across all faculties programs offered"
        ),
        QueryIntent.PROGRAM_INFO: "DIU official program catalog{} program details".format(program),
        QueryIntent.ELIGIBILITY: "DIU{} program eligibility verification official program catalog".format(program),
        QueryIntent.DEADLINE: "DIU current admission notice application deadline last date",
        QueryIntent.CONTACT: "DIU official admission contact phone email address",
        QueryIntent.INTERNATIONAL: "DIU international student admission policy tuition contact",
        QueryIntent.INTERNATIONAL_SCHOLARSHIP: "DIU official scholarships for international students merit grants financial support",
        QueryIntent.ADMISSION_TEST_SCHEDULE: "DIU current admission test schedule date and time official admission notice",
        QueryIntent.ADMISSION_TEST_SEAT_PLAN: "DIU current admission test seat plan official admission notice",
        QueryIntent.ADMISSION_TEST_RESULT: "DIU current admission test result official result page",
        QueryIntent.CREDIT_TRANSFER: "DIU official credit transfer guidelines eligibility process",
        QueryIntent.GUARDIAN_GUIDELINES: "DIU official guidelines for guardians admission responsibilities",
        QueryIntent.PAYMENT_GUIDELINES: "DIU official payment guidelines for all students payment instructions",
        QueryIntent.WAIVER_CALCULATOR: "DIU official waiver and tuition fee calculator",
        QueryIntent.FINANCIAL_AID: "DIU official financial aid and scholarship programs",
        QueryIntent.LIFE_INSURANCE: "DIU official student and guardian life insurance",
        QueryIntent.ADMISSION_OVERVIEW: "DIU official admission information overview",
        QueryIntent.FACT_CHECK: "DIU official source evidence for {}".format(original),
    }.get(intent)
    if canonical and intent in {QueryIntent.SCHOLARSHIP, QueryIntent.WAIVER}:
        canonical = _preserve_user_focus(canonical, original)
    return _SPACE_RE.sub(" ", canonical or original).strip()


def tuition_audience(query: str) -> Optional[str]:
    """Resolve an explicit tuition audience without confusing it with currency.

    ``both`` is returned only when both student audiences are named.  This keeps
    requests such as "international fees in BDT" in the international evidence
    lane (where the assistant must preserve USD rather than invent a conversion).
    Currency words are used only when no explicit audience is present.
    """

    normalized = unicodedata.normalize("NFKC", query)
    local = bool(_LOCAL_AUDIENCE_PATTERN.search(normalized))
    international = bool(_INTERNATIONAL_PATTERN.search(normalized))
    if local and international:
        return "both"
    if international:
        return "international"
    if local:
        return "local"
    if _INTERNATIONAL_CURRENCY_PATTERN.search(normalized):
        return "international"
    if _LOCAL_CURRENCY_PATTERN.search(normalized):
        return "local"
    return None


def _preserve_user_focus(canonical: str, original: str) -> str:
    """Keep a user's non-factual category qualifier in the retrieval query."""

    if original.casefold() in canonical.casefold():
        return canonical
    return "{} user focus {}".format(canonical, original)
