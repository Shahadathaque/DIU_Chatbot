"""Evidence-based chat service backed by the DIU retriever and optional generator."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from backend.core.errors import ApiError
from backend.models.chat import ChatResponse, ChatSource, Confidence, Language
from rag.generator import Generator, GeneratorUnavailableError
from rag.retriever import Retriever, _matched_program_phrase
from rag.query_processing import QueryIntent, analyze_query


_INTRO_BY_LANGUAGE: Dict[Language, str] = {
    "en": (
        "Evidence retrieved from official DIU sources "
        "(research prototype; this is a structured evidence summary, not an "
        "AI-generated answer):"
    ),
    "bn": (
        "অফিসিয়াল ডিআইইউ সূত্র থেকে প্রাপ্ত তথ্য "
        "(রিসার্চ প্রোটোটাইপ; এটি এআই-জেনারেটেড উত্তর নয়):"
    ),
    "banglish": (
        "Official DIU source theke prapto tottho (research prototype; "
        "eta AI-generated answer na):"
    ),
}

_INSUFFICIENT_ANSWER: Dict[Language, str] = {
    "en": (
        "I could not find enough verified information in DIU's official "
        "sources to answer your question confidently."
    ),
    "bn": (
        "আপনার প্রশ্নের উত্তর দেওয়ার জন্য অফিসিয়াল ডিআইইউ সূত্রে পর্যাপ্ত "
        "যাচাইকৃত তথ্য পাওয়া যায়নি।"
    ),
    "banglish": (
        "Apnar proshner uttor dewar jonno official DIU source e enough "
        "verified information paowa jay ni."
    ),
}

_LANGUAGE_NAME: Dict[Language, str] = {
    "en": "English",
    "bn": "Bengali (Bangla)",
    "banglish": "Banglish (Bengali written in Latin script)",
}

_SYSTEM_PROMPT = (
    "You are a concise admissions advisor for Daffodil International University "
    "(DIU). Answer the user's question using ONLY the DIU evidence supplied in the "
    "user message. Use the exact values in the evidence directly (for example the "
    "waiver rate or fee shown for the student's grades); do not paraphrase numbers "
    "you cannot see in the evidence. Do not invent admission requirements, dates, "
    "fees, programs, or policies. If the evidence does not support an answer, "
    "explicitly say that the available information is insufficient. Do not invent "
    "citations or URLs; never fabricate source links. Preserve uncertainty when "
    "the evidence is ambiguous. Never convert currencies. A value marked with $ "
    "is a USD value and must never be described as BDT. Do not describe a total "
    "program fee as a yearly or semester fee. If multiple rows give different "
    "values for different programs or faculties and the user did not identify "
    "one, do not choose a value for them; explain that it depends on the program "
    "or faculty and ask for that detail. Prefer the language the user requested. "
    "Do not add a process step that is absent from the supplied evidence. Answer "
    "briefly and directly. Prefer a short paragraph or at most six bullets. "
    "Do not add phone numbers, email addresses, or unrelated details unless the "
    "user asks for contact information."
)

_FOLLOWUP_TOPICS = (
    (re.compile(r"(?i)\bwaivers?\b|ওয়েভার|ওয়েভার"), "waiver"),
    (re.compile(r"(?i)\bscholarships?\b|বৃত্তি|স্কলারশিপ"), "scholarship"),
    (
        re.compile(
            r"(?i)(?:\b(?:gpa|grades?)\b.*\b(?:required|requirement|minimum|"
            r"needed|admission|apply|eligible)\b|\b(?:required|requirement|"
            r"minimum|needed|admission|apply|eligible)\b.*\b(?:gpa|grades?)\b)"
        ),
        "admission GPA requirement",
    ),
    (re.compile(r"(?i)\b(?:tuition|fees?|cost)\b|টিউশন|ফি|খরচ"), "tuition fee"),
    (
        re.compile(r"(?i)\bdocuments?\b|ডকুমেন্ট|কাগজপত্র|কাগজ"),
        "required admission documents",
    ),
    (re.compile(r"(?i)\bdeadlines?\b"), "admission deadline"),
    (
        re.compile(r"(?i)\b(?:apply|application|process)\b|আবেদন"),
        "admission process",
    ),
)
_PROGRAM_SENSITIVE_TOPICS = {
    "tuition fee",
    "waiver",
    "scholarship",
    "admission GPA requirement",
    "admission deadline",
}
_GPA_MENTION_PATTERN = re.compile(r"(?i)\b(?:gpa|grades?)\b")
_GPA_FIVE_PATTERN = re.compile(r"(?i)\bgpa\s*-?\s*5(?:\.0+)?\b")
_WAIVER_PROGRAM_CLARIFICATION: Dict[Language, str] = {
    "en": (
        "The waiver cannot be determined from GPA alone because DIU's policy "
        "uses different tables for different programs and faculties. Please "
        "tell me the program you intend to apply for."
    ),
    "bn": (
        "শুধু GPA থেকে ওয়েভারের হার নির্ধারণ করা যাচ্ছে না, কারণ DIU-এর নীতিতে "
        "প্রোগ্রাম ও ফ্যাকাল্টিভেদে আলাদা টেবিল আছে। আপনি কোন প্রোগ্রামে আবেদন "
        "করবেন তা বলুন।"
    ),
    "banglish": (
        "Shudhu GPA diye waiver rate nirdharon kora jacche na, karon DIU policy-te "
        "program o faculty onujayi alada table ache. Apni kon program-e apply "
        "korben seta bolun."
    ),
}
_ELIGIBILITY_GUIDANCE: Dict[Language, str] = {
    "en": (
        "I can confirm the program from DIU's official catalog, but I cannot "
        "determine your eligibility from this question alone. Use the Eligibility "
        "Checker and provide your academic background; its deterministic rule "
        "engine will report any missing official criteria instead of guessing."
    ),
    "bn": (
        "DIU-এর অফিসিয়াল ক্যাটালগ থেকে প্রোগ্রামটি নিশ্চিত করা যাচ্ছে, কিন্তু "
        "শুধু এই প্রশ্ন থেকে আপনার যোগ্যতা নির্ধারণ করা যায় না। Eligibility Checker-এ "
        "আপনার শিক্ষাগত তথ্য দিন; অফিসিয়াল মানদণ্ড অনুপস্থিত থাকলে এটি অনুমান না করে "
        "সেটি জানাবে।"
    ),
    "banglish": (
        "DIU-r official catalog theke program-ti confirm kora jacche, kintu shudhu "
        "ei proshno diye apnar eligibility decide kora jabe na. Eligibility Checker-e "
        "academic details din; official criteria missing hole eta guess na kore janabe."
    ),
}


def build_grounded_messages(
    message: str, language: Language, results: Sequence[Any]
) -> List[Dict[str, str]]:
    """Build a system+user prompt injecting retrieved evidence and source info."""
    evidence_blocks: List[str] = []
    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        evidence_blocks.append(
            "[{index}] Source: {title} ({url})\n"
            "Category: {category}\nProgram: {program}\nContent type: {content_type}\n"
            "{content}".format(
                index=index,
                title=chunk.title,
                url=chunk.source_url,
                category=chunk.category,
                program=chunk.program or "general",
                content_type=chunk.content_type,
                content=chunk.content.strip(),
            )
        )
    evidence_text = "\n\n".join(evidence_blocks)
    user_content = (
        "Language: {language}\n\n"
        "Question: {question}\n\n"
        "DIU evidence:\n{evidence}\n\n"
        "Answer the question using only the supplied evidence, in the requested "
        "language. If the evidence contains the exact value the question asks "
        "about (for example a waiver rate, fee, or requirement), state it "
        "directly. If the evidence is insufficient, say so explicitly. Be concise."
    ).format(
        language=_LANGUAGE_NAME[language],
        question=message,
        evidence=evidence_text,
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def resolve_followup(message: str, history: Optional[Sequence[Any]] = None) -> str:
    """Resolve the active program and topic from prior user turns.

    Program and topic are resolved independently. This lets ``what about BBA``
    switch away from CSE while retaining ``tuition fee``, and lets a later
    ``is there a waiver`` retain BBA without carrying an obsolete topic.
    Assistant text is deliberately ignored because it is generated content.
    """

    current_program = _matched_program_phrase(message)
    current_topic = _followup_topic(message)
    previous_program = _latest_history_value(history, _matched_program_phrase)
    previous_topic = _latest_history_value(history, _followup_topic)

    program = current_program or previous_program
    topic = current_topic or previous_topic
    needs_program = current_program is None and (
        current_topic is None or current_topic in _PROGRAM_SENSITIVE_TOPICS
    )
    needs_topic = current_topic is None and current_program is not None

    additions: List[str] = []
    if needs_program and program is not None:
        additions.append("Program: {}".format(program))
    elif needs_topic and current_program is not None:
        additions.append("Program: {}".format(current_program))
    if (current_topic is None and topic is not None) or (
        current_program is not None and current_topic is None and topic is not None
    ):
        additions.append("Topic: {}".format(topic))
    if not additions:
        return message
    base = message.rstrip().rstrip(".?!")
    return "{}. {}.".format(base, ". ".join(additions))


def _latest_history_value(
    history: Optional[Sequence[Any]], extractor: Any
) -> Optional[str]:
    """Return the newest value extracted from a prior user turn."""
    if not history:
        return None
    for turn in reversed(list(history)):
        if getattr(turn, "role", None) == "user":
            content = str(getattr(turn, "content", "") or "").strip()
            if content:
                value = extractor(content)
                if value is not None:
                    return str(value)
    return None


def _followup_topic(message: str) -> Optional[str]:
    for pattern, topic in _FOLLOWUP_TOPICS:
        if pattern.search(message):
            return topic
    return None


class ChatService:
    """Turn a user message into a source-grounded chat response.

    Retrieval and the domain gate remain owned by the ``Retriever``.  When the
    generator is present and evidence is available, the answer is LLM-generated
    but grounded in that evidence; otherwise the existing evidence-summary
    fallback is returned.  Sources always come from retrieved evidence, never
    from the model.
    """

    def __init__(
        self,
        retriever: Retriever,
        *,
        generator: Optional[Generator] = None,
        top_k: int = 5,
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self.top_k = top_k

    def answer(
        self,
        message: str,
        language: Language,
        history: Optional[Sequence[Any]] = None,
    ) -> ChatResponse:
        """Retrieve DIU evidence and return a grounded answer.

        When no evidence passes the retriever's authority gate (including
        out-of-domain questions), an insufficient-information response is
        returned with ``confidence`` low and no sources, and the generator is
        never called.
        """
        resolved = resolve_followup(message, history)
        resolved_analysis = analyze_query(
            resolved, program_phrase=_matched_program_phrase(resolved)
        )
        retrieval_top_k = (
            max(self.top_k, 60)
            if resolved_analysis.intent is QueryIntent.PROGRAM_CATALOG
            else self.top_k
        )
        results = self._retriever.retrieve(resolved, top_k=retrieval_top_k)
        if not results:
            return ChatResponse(
                answer=_INSUFFICIENT_ANSWER[language],
                sources=[],
                confidence="low",
                language=language,
            )
        structured_response = _structured_response(resolved, language, results)
        if structured_response is not None:
            return structured_response
        if self._generator is None:
            return self._evidence_response(results, language=language)
        return self._generated_response(resolved, language, results)

    def _generated_response(
        self, message: str, language: Language, results: List[Any]
    ) -> ChatResponse:
        messages = build_grounded_messages(message, language, results)
        try:
            answer = self._generator.generate(messages)
        except GeneratorUnavailableError as error:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="The language generation service is temporarily unavailable.",
            ) from error
        if not answer.strip():
            return self._evidence_response(results, language=language)
        return ChatResponse(
            answer=answer,
            sources=_sources_from(results),
            confidence=_confidence_from(results),
            language=language,
        )

    @staticmethod
    def _evidence_response(
        results: List[Any], *, language: Language
    ) -> ChatResponse:
        intro = _INTRO_BY_LANGUAGE[language]
        items: List[str] = []
        for index, result in enumerate(results, start=1):
            chunk = result.chunk
            excerpt = chunk.content.strip()
            items.append(f"{index}. [{chunk.title}] {excerpt}")
        answer = "\n\n".join([intro, *items])
        return ChatResponse(
            answer=answer,
            sources=_sources_from(results),
            confidence=_confidence_from(results),
            language=language,
        )


def _sources_from(results: Sequence[Any]) -> List[ChatSource]:
    """Deduplicate official DIU source URLs from retrieved evidence."""
    sources: List[ChatSource] = []
    seen_urls = set()
    for result in results:
        chunk = result.chunk
        url = chunk.source_url
        if url not in seen_urls:
            seen_urls.add(url)
            sources.append(ChatSource(title=chunk.title, url=url))
    return sources


def _confidence_from(results: Sequence[Any]) -> Confidence:
    best = max(float(result.relevance_score) for result in results)
    if best >= 0.85:
        return "high"
    if best >= 0.72:
        return "medium"
    return "low"


def _structured_response(
    message: str, language: Language, results: Sequence[Any]
) -> Optional[ChatResponse]:
    """Render facts whose table labels must not be reinterpreted by the LLM."""

    analysis = analyze_query(message, program_phrase=_matched_program_phrase(message))
    if analysis.intent is QueryIntent.ELIGIBILITY:
        return ChatResponse(
            answer=_ELIGIBILITY_GUIDANCE[language],
            sources=_sources_from(results),
            confidence=_confidence_from(results),
            language=language,
        )
    if analysis.intent is QueryIntent.PROGRAM_CATALOG:
        catalog_response = _program_catalog_response(language, results)
        if catalog_response is not None:
            return catalog_response
    topic = _followup_topic(message)
    if (
        topic == "waiver"
        and _GPA_MENTION_PATTERN.search(message)
        and _matched_program_phrase(message) is None
    ):
        return ChatResponse(
            answer=_WAIVER_PROGRAM_CLARIFICATION[language],
            sources=_sources_from(results),
            confidence=_confidence_from(results),
            language=language,
        )
    if topic == "waiver" and _matched_program_phrase(message) is not None:
        waiver_response = _waiver_table_response(message, language, results)
        if waiver_response is not None:
            return waiver_response
    if topic == "scholarship":
        scholarship_response = _scholarship_list_response(language, results)
        if scholarship_response is not None:
            return scholarship_response
    if topic != "tuition fee" or len(results) != 1:
        return None
    result = results[0]
    chunk = result.chunk
    if chunk.content_type.casefold() != "table":
        return None
    row = _table_row(chunk.content)
    if row is None:
        return None
    fields = [
        ("Payable During Admission", "payable during admission"),
        ("Average Semester Fees", "average semester fees"),
        ("Total Tuition Fees", "total tuition fees"),
        ("Total Program Fees", "total program fees"),
    ]
    values = [
        (label, _fee_amount(row.get(header, ""), chunk.category))
        for header, label in fields
        if row.get(header, "").strip()
    ]
    if not values:
        return None
    program = str(chunk.program or row.get("Full Program Name") or "the program")
    details = "; ".join("{} — {}".format(label, value) for label, value in values)
    if language == "bn":
        answer = "{}-এর অফিসিয়াল ফি টেবিল: {}।".format(program, details)
    elif language == "banglish":
        answer = "{}-er official fee table: {}.".format(program, details)
    else:
        answer = "For {}, the official fee table lists: {}.".format(program, details)
    return ChatResponse(
        answer=answer,
        sources=_sources_from(results),
        confidence=_confidence_from(results),
        language=language,
    )


def _program_catalog_response(
    language: Language, results: Sequence[Any]
) -> Optional[ChatResponse]:
    """Summarize complete structured catalog rows without model omissions."""

    programs: Dict[str, tuple[str, str]] = {}
    for result in results:
        chunk = result.chunk
        if (
            chunk.category.casefold() != "undergraduate_programs"
            or chunk.content_type.casefold() != "table"
            or not chunk.program
            or not chunk.faculty
        ):
            continue
        name = str(chunk.program).strip()
        faculty = str(chunk.faculty).strip()
        programs.setdefault(name.casefold(), (name, faculty))
    if not programs:
        return None

    by_faculty: Dict[str, List[str]] = {}
    for name, faculty in programs.values():
        by_faculty.setdefault(faculty, []).append(name)
    for names in by_faculty.values():
        names.sort(key=str.casefold)

    if len(by_faculty) == 1:
        faculty, names = next(iter(by_faculty.items()))
        listing = "\n".join(
            "{}. {}".format(index, name)
            for index, name in enumerate(names, start=1)
        )
        if language == "bn":
            answer = "{} ফ্যাকাল্টির অফিসিয়াল ক্যাটালগে:\n{}".format(
                faculty, listing
            )
        elif language == "banglish":
            answer = "{} faculty-r official catalog-e:\n{}".format(
                faculty, listing
            )
        else:
            answer = "The official catalog lists these {} programs:\n{}".format(
                faculty, listing
            )
    else:
        counts = "; ".join(
            "{} — {}".format(faculty, len(names))
            for faculty, names in sorted(
                by_faculty.items(), key=lambda item: item[0].casefold()
            )
        )
        if language == "bn":
            answer = "অফিসিয়াল DIU ক্যাটালগে মোট {}টি প্রোগ্রাম আছে: {}।".format(
                len(programs), counts
            )
        elif language == "banglish":
            answer = "Official DIU catalog-e mot {}ti program ache: {}.".format(
                len(programs), counts
            )
        else:
            answer = "The official DIU catalog contains {} programs: {}.".format(
                len(programs), counts
            )
    return ChatResponse(
        answer=answer,
        sources=_sources_from(results),
        confidence=_confidence_from(results),
        language=language,
    )


def _table_row(content: str) -> Optional[Dict[str, str]]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines[:-1]):
        if "Full Program Name" not in line or "|" not in line:
            continue
        headers = [value.strip() for value in line.split("|")]
        values = [value.strip() for value in lines[index + 1].split("|")]
        if len(headers) == len(values):
            return dict(zip(headers, values))
    return None


def _fee_amount(value: str, category: str) -> str:
    cleaned = value.strip()
    if "$" in cleaned or category.casefold() == "international_admission":
        return "USD {}".format(cleaned.replace("$", "").strip())
    return "BDT {}".format(cleaned)


def _waiver_table_response(
    message: str, language: Language, results: Sequence[Any]
) -> Optional[ChatResponse]:
    """Select the SSC/HSC waiver row without crossing into English-medium columns."""

    lowered = message.casefold()
    if not _GPA_FIVE_PATTERN.search(message) or "hsc" not in lowered:
        return None
    asks_both = "ssc" in lowered and "hsc" in lowered
    asks_golden = "golden" in lowered
    for result in results:
        chunk = result.chunk
        if chunk.content_type.casefold() != "table":
            continue
        for line in chunk.content.splitlines():
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) < 3:
                continue
            result_label = cells[0]
            folded_label = result_label.casefold()
            if "gpa-5" not in folded_label:
                continue
            if asks_golden != ("golden" in folded_label):
                continue
            if asks_both and "both in ssc and in hsc" not in folded_label:
                continue
            if not asks_both and (
                "in hsc" not in folded_label or "both" in folded_label
            ):
                continue
            rate, sgpa = cells[1], cells[2]
            if not rate or not sgpa:
                continue
            program = _matched_program_phrase(message) or "the selected program"
            if language == "bn":
                answer = (
                    "{}-এর নীতিতে ‘{}’ সারির জন্য টিউশন ফি ওয়েভার {} এবং "
                    "প্রয়োজনীয় SGPA {}।"
                ).format(program, result_label, rate, sgpa)
            elif language == "banglish":
                answer = (
                    "{}-er policy-te '{}' row-er tuition fee waiver {} ebong "
                    "required SGPA {}."
                ).format(program, result_label, rate, sgpa)
            else:
                answer = (
                    "For {}, the matching policy row is '{}': tuition-fee "
                    "waiver — {}; SGPA to be obtained — {}."
                ).format(program, result_label, rate, sgpa)
            return ChatResponse(
                answer=answer,
                sources=_sources_from(results),
                confidence=_confidence_from(results),
                language=language,
            )
    return None


def _scholarship_list_response(
    language: Language, results: Sequence[Any]
) -> Optional[ChatResponse]:
    """Extract the explicit names in an official ``Browse by Section`` block."""

    for result in results:
        lines = [line.strip() for line in result.chunk.content.splitlines() if line.strip()]
        try:
            start = next(
                index
                for index, line in enumerate(lines)
                if line.casefold() == "browse by section"
            )
        except StopIteration:
            continue
        names: List[str] = []
        for line in lines[start + 1 :]:
            if line.casefold() == "see more":
                break
            if "scholarship" in line.casefold():
                names.append(line)
        if not names:
            continue
        joined = ", ".join(names)
        if language == "bn":
            answer = (
                "অফিসিয়াল DIU পেজে স্পষ্টভাবে উল্লেখ আছে: {}। পেজে ‘See More’ "
                "থাকায় এটি সম্পূর্ণ তালিকা নয়।"
            ).format(joined)
        elif language == "banglish":
            answer = (
                "Official DIU page-e explicitly ache: {}. Page-e 'See More' "
                "thakay eta complete list na."
            ).format(joined)
        else:
            answer = (
                "The official DIU page explicitly names: {}. This is not exhaustive "
                "because the page also provides a 'See More' option."
            ).format(joined)
        return ChatResponse(
            answer=answer,
            sources=_sources_from([result]),
            confidence=_confidence_from([result]),
            language=language,
        )
    return None
