"""Regression coverage for multilingual admission-query understanding."""

from __future__ import annotations

import pytest

from rag.query_processing import QueryIntent, analyze_query, tuition_audience


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("How do I apply?", QueryIntent.APPLICATION_PROCESS),
        ("Apply online", QueryIntent.ONLINE_APPLICATION),
        ("অনলাইনে আবেদন", QueryIntent.ONLINE_APPLICATION),
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


def test_faculty_department_query_uses_program_catalog_intent() -> None:
    analysis = analyze_query("fsit department")

    assert analysis.intent is QueryIntent.PROGRAM_CATALOG
    assert analysis.is_admission_query


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
    "query",
    [
        "Information Technology",
        "Tell me about Information Technology",
        "Is Information Technology available?",
    ],
)
def test_unique_multiword_program_subject_is_program_information(query: str) -> None:
    analysis = analyze_query(query)

    assert analysis.intent is QueryIntent.PROGRAM_INFO
    assert analysis.is_admission_query
    assert "information technology & management" in analysis.retrieval_query.casefold()


def test_shared_multiword_subject_is_not_guessed_as_one_program() -> None:
    analysis = analyze_query("Business Administration")

    assert analysis.intent is None
    assert not analysis.is_admission_query


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


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("Admission test schedule", QueryIntent.ADMISSION_TEST_SCHEDULE),
        ("bhorti test date kobe?", QueryIntent.ADMISSION_TEST_SCHEDULE),
        ("ভর্তি পরীক্ষার সময়সূচি", QueryIntent.ADMISSION_TEST_SCHEDULE),
        ("seat plan", QueryIntent.ADMISSION_TEST_SEAT_PLAN),
        ("ভর্তি পরীক্ষার সিট প্ল্যান", QueryIntent.ADMISSION_TEST_SEAT_PLAN),
        ("Admission test result", QueryIntent.ADMISSION_TEST_RESULT),
        ("bhorti test result", QueryIntent.ADMISSION_TEST_RESULT),
        ("credit transfer guidelines", QueryIntent.CREDIT_TRANSFER),
        ("ক্রেডিট ট্রান্সফার নিয়ম", QueryIntent.CREDIT_TRANSFER),
        ("guidelines for guardians", QueryIntent.GUARDIAN_GUIDELINES),
        ("guardian guide", QueryIntent.GUARDIAN_GUIDELINES),
        ("payment guidelines", QueryIntent.PAYMENT_GUIDELINES),
        ("payment kivabe korbo", QueryIntent.PAYMENT_GUIDELINES),
        ("international student scholarship", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
        ("বিদেশি শিক্ষার্থীদের স্কলারশিপ", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
        ("waiver and tuition fee calculator", QueryIntent.WAIVER_CALCULATOR),
        ("waiver hisab", QueryIntent.WAIVER_CALCULATOR),
        ("financial aid", QueryIntent.FINANCIAL_AID),
        ("financial support", QueryIntent.FINANCIAL_AID),
        ("life insurance", QueryIntent.LIFE_INSURANCE),
        ("জীবন বীমা", QueryIntent.LIFE_INSURANCE),
        ("payment", QueryIntent.PAYMENT_GUIDELINES),
        ("insurance", QueryIntent.LIFE_INSURANCE),
        ("result", QueryIntent.ADMISSION_TEST_RESULT),
        ("schedule", QueryIntent.ADMISSION_TEST_SCHEDULE),
        ("আন্তর্জাতিক শিক্ষার্থীদের বৃত্তি", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
    ],
)
def test_complete_admission_section_queries_have_dedicated_intents(
    query: str, intent: QueryIntent
) -> None:
    analysis = analyze_query(query)

    assert analysis.intent is intent
    assert analysis.is_admission_query
    assert analysis.retrieval_query.casefold().startswith("diu")


def test_international_scholarship_is_not_rewritten_as_local() -> None:
    analysis = analyze_query("Scholarships for international students")

    assert analysis.intent is QueryIntent.INTERNATIONAL_SCHOLARSHIP
    assert "international students" in analysis.retrieval_query.casefold()
    assert "local students" not in analysis.retrieval_query.casefold()


def test_universal_scholarship_claim_uses_fact_compatibility_not_list_intent() -> None:
    analysis = analyze_query(
        "Does every undergraduate student receive a scholarship?"
    )

    assert analysis.intent is QueryIntent.FACT_CHECK
    assert "every undergraduate student" in analysis.retrieval_query.casefold()


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("Last Date to Apply", QueryIntent.DEADLINE),
        ("apply er last date kobe", QueryIntent.DEADLINE),
        ("How can I pay my admission fee?", QueryIntent.PAYMENT_GUIDELINES),
        ("tuition fee payment", QueryIntent.PAYMENT_GUIDELINES),
        ("admission-fee payment method", QueryIntent.PAYMENT_GUIDELINES),
        ("admission fee kivabe dibo", QueryIntent.PAYMENT_GUIDELINES),
        ("টাকা কিভাবে দিব", QueryIntent.PAYMENT_GUIDELINES),
        ("admission office number", QueryIntent.CONTACT),
        ("Can I transfer credits?", QueryIntent.CREDIT_TRANSFER),
        ("Information for parents", QueryIntent.GUARDIAN_GUIDELINES),
        ("funding for foreign applicants", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
        ("tuition discount", QueryIntent.WAIVER),
        ("When is the admission test?", QueryIntent.ADMISSION_TEST_SCHEDULE),
        ("Can I apply to CSE?", QueryIntent.ELIGIBILITY),
        ("Programs", QueryIntent.PROGRAM_CATALOG),
        ("Does DIU offer New Program?", QueryIntent.PROGRAM_INFO),
        ("seatplan", QueryIntent.ADMISSION_TEST_SEAT_PLAN),
        ("admission-test seat-plan", QueryIntent.ADMISSION_TEST_SEAT_PLAN),
        ("ভর্তি পরীক্ষার ফল", QueryIntent.ADMISSION_TEST_RESULT),
        ("online admission", QueryIntent.ONLINE_APPLICATION),
        ("on-line admission form", QueryIntent.ONLINE_APPLICATION),
        ("current admission notice", QueryIntent.DEADLINE),
        ("কিভাবে ভর্তি হব", QueryIntent.APPLICATION_PROCESS),
        ("How do I enroll?", QueryIntent.APPLICATION_PROCESS),
        ("bideshi student admission", QueryIntent.INTERNATIONAL),
        ("bideshi student scholarship", QueryIntent.INTERNATIONAL_SCHOLARSHIP),
        ("student visa", QueryIntent.INTERNATIONAL),
        ("How much do I pay for CSE?", QueryIntent.TUITION),
        ("CSE price", QueryIntent.TUITION),
        ("CSE er jonno koto dite hobe", QueryIntent.TUITION),
        ("What do I need for admission?", QueryIntent.DOCUMENTS),
    ],
)
def test_natural_section_paraphrases_keep_their_specific_intent(
    query: str, intent: QueryIntent
) -> None:
    assert analyze_query(query).intent is intent


@pytest.mark.parametrize(
    "query",
    [
        "All Students of Undergraduate Program Will Get a Laptop Free.",
        "Does DIU give every undergraduate student a free laptop?",
        "Is the laptop free for undergraduate students?",
        "Which program is best?",
    ],
)
def test_program_words_inside_claims_do_not_trigger_the_catalog(query: str) -> None:
    analysis = analyze_query(query)

    assert analysis.intent is QueryIntent.FACT_CHECK
    assert analysis.is_admission_query
    assert "complete program catalog" not in analysis.retrieval_query.casefold()


@pytest.mark.parametrize(
    "query",
    [
        "Show available programs",
        "List all undergraduate programs",
        "What programs does DIU offer?",
        "কি কি প্রোগ্রাম আছে",
    ],
)
def test_explicit_catalog_requests_still_use_catalog_intent(query: str) -> None:
    assert analyze_query(query).intent is QueryIntent.PROGRAM_CATALOG


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("local CSE tuition fees", "local"),
        ("international CSE tuition fees", "international"),
        ("CSE tuition fees in USD", "international"),
        ("CSE tuition fees in BDT", "local"),
        ("local and international CSE tuition fees", "both"),
        ("international CSE tuition fees in BDT", "international"),
    ],
)
def test_tuition_audience_resolution_preserves_explicit_scope(
    query: str, expected: str
) -> None:
    assert tuition_audience(query) == expected


def test_mixed_audience_tuition_canonical_query_keeps_bdt_and_usd_lanes() -> None:
    analysis = analyze_query("Compare local and international CSE tuition fees")

    assert analysis.intent is QueryIntent.TUITION
    assert "local student" in analysis.retrieval_query.casefold()
    assert "international student" in analysis.retrieval_query.casefold()
    assert "bdt" in analysis.retrieval_query.casefold()
    assert "usd" in analysis.retrieval_query.casefold()
