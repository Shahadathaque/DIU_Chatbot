"""Authority-aware semantic retrieval over the DIU knowledge base."""

from __future__ import annotations

import re
import threading
import unicodedata
import math
from collections import Counter
from typing import Any, Iterable, List, Optional, Sequence

from rag.config import RagSettings, get_rag_settings
from rag.embeddings import EmbeddingUnavailableError, Embedder, create_embedder
from rag.faculty_resolution import faculty_names_match, matched_faculty_phrase
from rag.models import KnowledgeChunk, SearchFilters, SearchResult, VectorMatch
from rag.program_resolution import (
    PROGRAM_BY_MARKER,
    best_compatible_catalog_program,
    catalog_program_phrase,
    chunk_program_matches,
    matched_program_phrase,
    named_program_markers,
    normalize_program_text,
    program_level_matches,
    program_phrase_matches,
    program_search_phrase,
    single_named_program_marker,
)
from rag.query_processing import QueryIntent, analyze_query, tuition_audience
from rag.vector_store import VectorStore, create_vector_store


_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[\w\u0980-\u09ff]+", re.UNICODE)
_OTHER_INSTITUTION_PHRASES = (
    "brac university",
    "north south university",
    "east west university",
    "independent university bangladesh",
    "united international university",
)
_OTHER_INSTITUTION_ACRONYMS = ("nsu", "ewu", "iub", "uiu")
_DIU_PHRASES = (
    "daffodil",
    "ড্যাফোডিল",
    "ডিআইইউ",
)
_DIU_ACRONYMS = ("diu",)
_QUERY_EXPANSIONS = (
    (re.compile(r"\bdocuments?\b", re.I), " required documents checklist certificate transcript"),
    (re.compile(r"\b(?:document|documents|papers?)\s+lagbe\b", re.I), " required admission documents প্রয়োজনীয় কাগজপত্র"),
    (re.compile(r"\b(?:vorti|bhorti)\b", re.I), " admission ভর্তি"),
    (re.compile(r"\b(?:fee|fees|tuition)\b", re.I), " tuition fees খরচ"),
    (re.compile(r"\b(?:waiver|scholarship)s?\b", re.I), " waiver scholarship financial aid বৃত্তি"),
    (re.compile(r"(?:ডকুমেন্ট|কাগজপত্র|কাগজ)", re.I), " required admission documents checklist certificate transcript Necessary Documents"),
    (re.compile(r"(?:ভর্তি|ভর্তির)", re.I), " admission"),
    (re.compile(r"(?:আবেদন)", re.I), " apply application"),
    (re.compile(r"(?:টিউশন|ফি|খরচ)", re.I), " tuition fees cost"),
    (re.compile(r"(?:বৃত্তি|স্কলারশিপ|ওয়েভার|ওয়েভার)", re.I), " scholarship waiver financial aid"),
    (re.compile(r"\bcse\b", re.I), " Computer Science and Engineering"),
)
_DOMAIN_TERM_PATTERN = re.compile(
    r"(?i)(?:\b(?:admissions?|admit|apply\w*|programs?|courses?|degrees?|"
    r"documents?|certificates?|transcripts?|gpas?|tuition|fees?|costs?|"
    r"scholarships?|waivers?|financial\s+aid|international\s+students?|"
    r"seat\s+plans?|admission\s+test|credit\s+transfer|guardians?|"
    r"payment\s+guidelines?|life\s+insurance|"
    r"eligibility|eligible|deadlines?|requirements?|contacts?|campus|semesters?|"
    r"vorti|bhorti)\b|ভর্তি|আবেদন|ডকুমেন্ট|কাগজপত্র|কাগজ|টিউশন|ফি|খরচ|"
    r"বৃত্তি|স্কলারশিপ|ওয়েভার|ওয়েভার|প্রোগ্রাম|কোর্স|যোগাযোগ)"
)
_STRUCTURED_DATA_PATTERN = re.compile(
    r"(?i)(?:\b(?:waivers?|scholarships?|tuition|fees?|cost|rates?|gpas?|"
    r"percentages?|deadlines?|requirements?)\b|%|বৃত্তি|টিউশন|ফি|খরচ|"
    r"ওয়েভার|ওয়েভার)"
)
_TUITION_PATTERN = re.compile(r"(?i)\b(?:tuition|fees?|cost)\b|টিউশন|ফি|খরচ")
_WAIVER_PATTERN = re.compile(r"(?i)\bwaivers?\b|ওয়েভার|ওয়েভার")
_SCHOLARSHIP_PATTERN = re.compile(r"(?i)\bscholarships?\b|বৃত্তি|স্কলারশিপ")
_ADMISSION_GPA_PATTERN = re.compile(
    r"(?i)(?:\b(?:gpa|grades?)\b.*\b(?:admission|apply|required|requirement|"
    r"minimum|needed|eligible|eligibility)\b|\b(?:admission|apply|required|"
    r"requirement|minimum|needed|eligible|eligibility)\b.*\b(?:gpa|grades?)\b)"
)
_GPA_QUERY_PATTERN = re.compile(r"(?i)\b(?:gpa|grades?)\b")
_LOCAL_CURRENCY_PATTERN = re.compile(
    r"(?i)(?:\b(?:bdt|taka|tk\.?|local|domestic|bangladeshi)\b|৳)"
)
_INTERNATIONAL_CURRENCY_PATTERN = re.compile(
    r"(?i)(?:\b(?:usd|dollars?|international|foreign)\b|\$)"
)
_DOCUMENT_PATTERN = re.compile(
    r"(?i)\bdocuments?\b|ডকুমেন্ট|কাগজপত্র|কাগজ"
)
_DEADLINE_PATTERN = re.compile(r"(?i)\bdeadlines?\b")
_ADMISSION_PROCESS_PATTERN = re.compile(
    r"(?i)(?:\b(?:admission|application)\s+process\b|"
    r"\bhow\s+(?:do|can|to)\s+(?:i\s+)?apply\b|আবেদন)"
)
_PROGRAM_CATALOG_QUERY = "the complete DIU program catalog across all faculties"
_PROGRAM_MISMATCH_PENALTY = -0.50
_AID_FOCUS_IGNORED_TOKENS = {
    "about",
    "aid",
    "any",
    "available",
    "categories",
    "category",
    "details",
    "diu",
    "does",
    "fee",
    "fees",
    "financial",
    "give",
    "have",
    "information",
    "official",
    "policy",
    "rate",
    "rates",
    "scholarship",
    "scholarships",
    "show",
    "tell",
    "there",
    "tuition",
    "waiver",
    "waivers",
    "what",
    "which",
}
_CLAIM_FOCUS_IGNORED_TOKENS = {
    "about", "admission", "admissions", "all", "an", "and", "any", "are",
    "can", "course", "courses", "daffodil", "did", "diu", "do", "does",
    "every", "for", "from", "get", "gets", "give", "gives", "has", "have",
    "in", "information", "is", "it", "me", "of", "official", "on", "program",
    "programs", "student", "students", "tell", "that", "the", "their", "there",
    "to", "undergraduate", "undergraduates", "university", "what", "which", "will",
    "with", "would", "প্রোগ্রাম", "কোর্স", "ভর্তি", "শিক্ষার্থী",
}
_SCOPE_FOCUS_IGNORED_TOKENS = {
    "admission", "admissions", "and", "apply", "are", "at", "bhorti", "can",
    "date", "deadline", "diu", "do", "does", "faculty", "find", "for", "i",
    "information", "is", "kobe", "last", "my", "of", "official", "plan",
    "porikkha", "result", "results", "schedule", "seat", "test", "the", "time",
    "to", "vorti", "we", "when", "where", "you", "কবে", "তারিখ", "পরীক্ষা",
    "পরীক্ষার", "ফলাফল", "ভর্তি", "সময়সূচি", "সিট", "প্ল্যান",
}
_SCOPED_CURRENT_INTENTS = {
    QueryIntent.ADMISSION_TEST_SCHEDULE,
    QueryIntent.ADMISSION_TEST_SEAT_PLAN,
    QueryIntent.ADMISSION_TEST_RESULT,
    QueryIntent.DEADLINE,
}
def _matched_program_phrase(query: str) -> Optional[str]:
    """Return the official program phrase named by a program-related query."""

    return matched_program_phrase(query)

def _named_program_acronyms(query: str) -> List[str]:
    """Return every program acronym the query explicitly names."""

    return _named_program_markers(query)


def _named_program_markers(query: str) -> List[str]:
    """Prefer exact catalog phrases over broader acronym/keyword matches."""

    return named_program_markers(query)


def _single_named_program_acronym(query: str) -> Optional[str]:
    """Return the sole named program acronym, or None when none/multiple."""

    return single_named_program_marker(query)


def _chunk_program_matches(program: str, acronym: str) -> bool:
    """Return whether a chunk's program metadata belongs to the named acronym."""

    return chunk_program_matches(program, acronym)


def normalize_query(query: str) -> str:
    """Normalize harmless text variance while preserving Bangla characters."""

    normalized = _base_query(query)
    expanded = normalized
    for pattern, suffix in _QUERY_EXPANSIONS:
        if pattern.search(normalized):
            expanded += suffix
    return _SPACE_RE.sub(" ", expanded).strip()


def is_explicitly_out_of_domain(query: str) -> bool:
    """Reject questions explicitly naming another university, not generic topics."""

    lowered = unicodedata.normalize("NFKC", query).casefold()
    names_diu = any(marker in lowered for marker in _DIU_PHRASES) or any(
        _contains_ascii_token(lowered, acronym) for acronym in _DIU_ACRONYMS
    )
    names_other = any(name in lowered for name in _OTHER_INSTITUTION_PHRASES) or any(
        _contains_ascii_token(lowered, acronym)
        for acronym in _OTHER_INSTITUTION_ACRONYMS
    )
    return not names_diu and names_other


def is_likely_admission_query(query: str) -> bool:
    """Apply a transparent domain gate before accepting dense-vector evidence."""

    analysis = analyze_query(query)
    lowered = analysis.normalized_query.casefold()
    names_diu = any(marker in lowered for marker in _DIU_PHRASES) or any(
        _contains_ascii_token(lowered, acronym) for acronym in _DIU_ACRONYMS
    )
    return (
        analysis.is_admission_query
        or names_diu
        or _matched_program_phrase(query) is not None
        or bool(_DOMAIN_TERM_PATTERN.search(lowered))
    )


class Retriever:
    """Embed, filter, lightly rerank, and de-duplicate DIU evidence."""

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        *,
        min_similarity_score: float = 0.75,
        min_relevance_score: float = 0.72,
        candidate_multiplier: int = 5,
        max_results_per_source: int = 2,
        reranker: Optional[Any] = None,
    ) -> None:
        if candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be positive")
        if max_results_per_source < 1:
            raise ValueError("max_results_per_source must be positive")
        _validated_score(min_similarity_score, name="min_similarity_score")
        _validated_score(min_relevance_score, name="min_relevance_score")
        if embedder.dimension != vector_store.embedding_dimension:
            raise ValueError(
                "embedder/vector-store dimension mismatch: "
                f"{embedder.dimension} != {vector_store.embedding_dimension}"
            )
        self.embedder = embedder
        self.vector_store = vector_store
        if embedder.model_name != vector_store.embedding_model_name:
            raise ValueError(
                "embedder/vector-store model mismatch: "
                f"{embedder.model_name!r} != {vector_store.embedding_model_name!r}"
            )
        if embedder.model_revision != vector_store.embedding_model_revision:
            raise ValueError(
                "embedder/vector-store model revision mismatch: "
                f"{embedder.model_revision!r} != "
                f"{vector_store.embedding_model_revision!r}"
            )
        self.min_similarity_score = min_similarity_score
        self.min_relevance_score = min_relevance_score
        self.candidate_multiplier = candidate_multiplier
        self.max_results_per_source = max_results_per_source
        self.reranker = reranker
        self._lexical_chunks_cache: dict[SearchFilters, List[KnowledgeChunk]] = {}
        self._lexical_cache_lock = threading.RLock()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        program: Optional[str] = None,
        *,
        include_historical: bool = False,
        include_uncertain: bool = False,
        include_manual_review: bool = False,
        include_partial: bool = False,
        min_similarity_score: Optional[float] = None,
        min_relevance_score: Optional[float] = None,
    ) -> List[SearchResult]:
        """Return filtered relevant chunks; default evidence is current/stable only."""

        if top_k < 1:
            raise ValueError("top_k must be positive")
        similarity_threshold = (
            self.min_similarity_score
            if min_similarity_score is None
            else min_similarity_score
        )
        relevance_threshold = (
            self.min_relevance_score
            if min_relevance_score is None
            else min_relevance_score
        )
        _validated_score(similarity_threshold, name="min_similarity_score")
        _validated_score(relevance_threshold, name="min_relevance_score")
        if is_explicitly_out_of_domain(query):
            return []
        raw_intent_query = _base_query(query)
        program_phrase = _matched_program_phrase(raw_intent_query)
        analysis = analyze_query(raw_intent_query, program_phrase=program_phrase)
        if not analysis.is_admission_query:
            return []
        intent_query = analysis.normalized_query
        program_list_query = analysis.intent is QueryIntent.PROGRAM_CATALOG
        normalized = analysis.retrieval_query
        filters = SearchFilters(
            category=category,
            program=program,
            include_historical=include_historical,
            include_uncertain=include_uncertain,
            include_manual_review=include_manual_review,
            include_partial=include_partial,
        )
        candidate_limit = max(top_k * self.candidate_multiplier, top_k)
        lexical_fallback_active = False

        def search_lane(
            lane_query: str,
            *,
            lane_filters: SearchFilters,
            lane_limit: int = candidate_limit,
        ) -> List[VectorMatch]:
            """Search one retrieval lane, degrading only provider dependency.

            Once the embedding provider reports an availability failure, all
            remaining lanes in this request use the same deterministic lexical
            candidate path. Authority and metadata filtering still occurs in
            the vector store and the normal compatibility gates still run
            below. Programming/configuration errors are intentionally not
            swallowed.
            """

            nonlocal lexical_fallback_active
            if not lexical_fallback_active:
                try:
                    lane_embedding = self.embedder.embed_query(lane_query)
                except EmbeddingUnavailableError:
                    lexical_fallback_active = True
                else:
                    return self.vector_store.search(
                        lane_embedding,
                        top_k=lane_limit,
                        filters=lane_filters,
                    )
            chunks = self._list_lexical_chunks(lane_filters)
            return self._lexical_candidates(
                lane_query,
                chunks,
                top_k=lane_limit,
            )

        authoritative_filters = SearchFilters(category=category, program=program)
        authoritative_candidates = search_lane(
            normalized,
            lane_limit=candidate_limit,
            lane_filters=authoritative_filters,
        )
        if any(
            (
                include_historical,
                include_uncertain,
                include_manual_review,
                include_partial,
            )
        ):
            expanded_candidates = search_lane(
                normalized,
                lane_limit=candidate_limit + len(authoritative_candidates),
                lane_filters=filters,
            )
            candidates = self._merge_candidates(
                authoritative_candidates, expanded_candidates
            )
        else:
            candidates = authoritative_candidates
        lexical_compatibility_chunk_ids: set[str] = set()
        compatible_categories = (
            _intent_candidate_categories(analysis.intent, intent_query)
            if lexical_fallback_active
            else ()
        )
        for compatible_category in compatible_categories:
            if category is not None and category.casefold() != compatible_category:
                continue
            category_candidates = search_lane(
                intent_query,
                lane_limit=candidate_limit,
                lane_filters=SearchFilters(
                    category=compatible_category,
                    program=program,
                    include_historical=include_historical,
                    include_uncertain=include_uncertain,
                    include_manual_review=include_manual_review,
                    include_partial=include_partial,
                ),
            )
            candidates = self._merge_candidates(category_candidates, candidates)
            if lexical_fallback_active:
                # Category selection is deterministic, but authority and the
                # query/evidence compatibility gate below remain mandatory.
                # Exempt only those compatible rows from dense-score cutoffs,
                # whose numeric meaning does not exist during provider outage.
                lexical_compatibility_chunk_ids.update(
                    match.chunk.chunk_id for match in category_candidates
                )
        exact_topic_chunk_ids: set[str] = set()
        exact_topic_category = _exact_topic_category(analysis.intent)
        if exact_topic_category is not None and (
            category is None or category.casefold() == exact_topic_category
        ):
            # An explicit, one-to-one topic is stronger than generic semantic
            # similarity. Search its registered category directly so a small
            # official page cannot be crowded out by longer, broadly similar
            # admission pages. ``partial`` is allowed only in this exact lane:
            # title-only captures provide the verified official destination
            # needed for an honest "current information unavailable" answer.
            exact_topic_candidates = search_lane(
                normalized,
                lane_limit=candidate_limit,
                lane_filters=SearchFilters(
                    category=exact_topic_category,
                    program=program,
                    include_historical=include_historical,
                    include_uncertain=include_uncertain,
                    include_manual_review=include_manual_review,
                    include_partial=True,
                ),
            )
            candidates = self._merge_candidates(exact_topic_candidates, candidates)
            exact_topic_chunk_ids = {
                match.chunk.chunk_id for match in exact_topic_candidates
            }
        scope_tokens = (
            _scope_focus_tokens(intent_query)
            if analysis.intent in _SCOPED_CURRENT_INTENTS
            else set()
        )
        if scope_tokens:
            # Preserve explicit faculty, semester, year, or program qualifiers
            # that the canonical topic query intentionally omits.
            scoped_candidates = search_lane(
                intent_query,
                lane_limit=candidate_limit,
                lane_filters=filters,
            )
            candidates = self._merge_candidates(scoped_candidates, candidates)
        exact_focus_chunk_ids: set[str] = set()
        if (
            program_phrase is None
            and analysis.intent in {QueryIntent.SCHOLARSHIP, QueryIntent.WAIVER}
        ):
            focus_tokens = _aid_focus_tokens(intent_query)
            if focus_tokens:
                focus_category = (
                    "waivers"
                    if analysis.intent is QueryIntent.WAIVER
                    else "scholarships"
                )
                focus_candidates = search_lane(
                    intent_query,
                    lane_limit=candidate_limit,
                    lane_filters=SearchFilters(
                        category=category or focus_category,
                        program=program,
                    ),
                )
                exact_focus_candidates = [
                    match
                    for match in focus_candidates
                    if _chunk_matches_aid_focus(match.chunk, focus_tokens)
                ]
                if exact_focus_candidates:
                    candidates = exact_focus_candidates
                    exact_focus_chunk_ids = {
                        match.chunk.chunk_id for match in exact_focus_candidates
                    }
        program_lane_category = category or _program_lane_category(
            analysis.intent, intent_query
        )
        # The intent-oriented query intentionally removes conversational noise,
        # but an additional raw-name lane preserves full catalog names that do
        # not require a manually maintained alias.
        raw_program_phrase = program_search_phrase(intent_query)
        named_marker = _single_named_program_acronym(intent_query)
        raw_is_known_alias = bool(
            raw_program_phrase
            and named_marker
            and any(
                normalize_program_text(raw_program_phrase)
                == normalize_program_text(alias)
                for alias in (
                    *PROGRAM_BY_MARKER[named_marker].aliases,
                    PROGRAM_BY_MARKER[named_marker].canonical,
                )
            )
        )
        if (
            not program_list_query
            and analysis.intent
            in {
                QueryIntent.TUITION,
                QueryIntent.PROGRAM_INFO,
                QueryIntent.ELIGIBILITY,
                QueryIntent.WAIVER,
            }
            and raw_program_phrase
            and raw_program_phrase.casefold() != normalized.casefold()
            and (
                program_phrase is None
                or not raw_is_known_alias
            )
        ):
            raw_candidates = search_lane(
                raw_program_phrase,
                lane_limit=candidate_limit,
                lane_filters=SearchFilters(
                    category=program_lane_category,
                    program=program,
                ),
            )
            candidates = self._merge_candidates(raw_candidates, candidates)
        # Keep the program resolved from the user's wording. Canonical intent
        # text may omit it for document/application intents, but the dedicated
        # program lane must still remain available for precise evidence.
        program_phrase = program_phrase or _matched_program_phrase(normalized)
        if program_list_query:
            # Catalog/faculty intent outranks partial program aliases discovered
            # from the same words (for example Business & Entrepreneurship
            # versus Bachelor of Entrepreneurship). Do not let that stale
            # pre-analysis program phrase filter out the requested faculty.
            program_phrase = _PROGRAM_CATALOG_QUERY
        if program_phrase is not None:
            program_candidates = search_lane(
                program_phrase,
                lane_limit=candidate_limit,
                lane_filters=SearchFilters(
                    category=program_lane_category,
                    program=program,
                ),
            )
            candidates = self._merge_candidates(program_candidates, candidates)
        resolved_catalog_program: Optional[str] = None
        if not program_list_query:
            catalog_programs = [
                str(match.chunk.program)
                for match in candidates
                if match.chunk.program
            ]
            exact_catalog_program = catalog_program_phrase(
                intent_query,
                catalog_programs,
            )
            if exact_catalog_program is not None:
                program_phrase = exact_catalog_program
                resolved_catalog_program = exact_catalog_program
            elif program_phrase is not None:
                compatible_catalog_program = best_compatible_catalog_program(
                    intent_query, program_phrase, catalog_programs
                )
                if compatible_catalog_program is not None:
                    program_phrase = compatible_catalog_program
                    resolved_catalog_program = compatible_catalog_program
        named_faculty = None
        if program_list_query:
            faculty_focus = _catalog_faculty_focus(intent_query)
            if faculty_focus:
                focus_candidates = search_lane(
                    faculty_focus,
                    lane_limit=candidate_limit,
                    lane_filters=SearchFilters(category=category, program=program),
                )
                candidates = self._merge_candidates(focus_candidates, candidates)
            named_faculty = (
                matched_faculty_phrase(intent_query)
                or _matched_catalog_faculty(intent_query, candidates)
            )
        if named_faculty is not None:
            candidates = [
                match
                for match in candidates
                if match.chunk.content_type.casefold() == "table"
                and faculty_names_match(str(match.chunk.faculty or ""), named_faculty)
            ]
        elif program_list_query:
            catalog_candidates = [
                match
                for match in candidates
                if match.chunk.category.casefold() == "undergraduate_programs"
            ]
            structured_rows = [
                match
                for match in catalog_candidates
                if match.chunk.content_type.casefold() == "table"
                and match.chunk.program
            ]
            candidates = structured_rows or catalog_candidates
        if exact_focus_chunk_ids:
            # Program-name and raw-phrase lanes run after the aid-focus lane.
            # Keep them from reintroducing generic or heading-only chunks once
            # exact qualifier-compatible evidence has been established.
            candidates = [
                match
                for match in candidates
                if match.chunk.chunk_id in exact_focus_chunk_ids
            ]
        candidates = [
            match
            for match in candidates
            if _evidence_matches_query_context(
                intent_query,
                match.chunk,
                program_phrase=(
                    None if program_phrase == _PROGRAM_CATALOG_QUERY else program_phrase
                ),
            )
        ]
        ranked = [
            self._rerank(normalized, match, intent_query=intent_query)
            for match in candidates
        ]
        reranker_scores = (
            self.reranker.score(
                normalized,
                [result.chunk.content for result in ranked],
            )
            if self.reranker is not None and ranked
            else []
        )
        cross_scores = {
            result.chunk.chunk_id: float(score)
            for result, score in zip(ranked, reranker_scores)
        }
        ranked.sort(
            key=lambda result: (
                *self._authority_rank(result.chunk),
                -cross_scores.get(result.chunk.chunk_id, 0.0),
                -result.relevance_score,
                -self._topic_bonus(intent_query, result.chunk.category),
                -self._metadata_bonus(intent_query, result.chunk),
                -result.similarity_score,
                result.chunk.chunk_id,
            )
        )
        if _excludes_engineering(intent_query):
            ranked = [
                result
                for result in ranked
                if not _is_engineering_faculty_chunk(result.chunk)
            ]
        return self._suppress_duplicates(
            ranked,
            top_k=top_k,
            similarity_threshold=(
                -1.0
                if program_list_query or resolved_catalog_program is not None
                else similarity_threshold
            ),
            relevance_threshold=-1.0 if program_list_query else relevance_threshold,
            preferred_categories=set(self._topic_category_bonuses(intent_query)),
            program_list_query=program_list_query,
            exact_compatibility_chunk_ids=exact_focus_chunk_ids,
            threshold_exempt_chunk_ids=(
                exact_topic_chunk_ids | lexical_compatibility_chunk_ids
            ),
        )

    @staticmethod
    def _merge_candidates(
        authoritative: Sequence[VectorMatch], expanded: Sequence[VectorMatch]
    ) -> List[VectorMatch]:
        """Merge search lanes while retaining each row's strongest match.

        A canonical intent lane and a program-name lane can both return the
        same verified chunk. Keeping the weaker lane's score would incorrectly
        discard evidence that passed the calibrated semantic threshold.
        """

        merged = {match.chunk.chunk_id: match for match in expanded}
        for match in authoritative:
            previous = merged.get(match.chunk.chunk_id)
            if previous is None or match.similarity_score > previous.similarity_score:
                merged[match.chunk.chunk_id] = match
        return list(merged.values())

    def _list_lexical_chunks(
        self, filters: SearchFilters
    ) -> List[KnowledgeChunk]:
        """Reuse an immutable runtime index snapshot during provider outages."""

        with self._lexical_cache_lock:
            cached = self._lexical_chunks_cache.get(filters)
        if cached is not None:
            return cached
        chunks = self.vector_store.list_chunks(filters=filters)
        with self._lexical_cache_lock:
            return self._lexical_chunks_cache.setdefault(filters, chunks)

    @staticmethod
    def _lexical_candidates(
        query: str,
        chunks: Sequence[KnowledgeChunk],
        *,
        top_k: int,
    ) -> List[VectorMatch]:
        """Rank already-authorized chunks without an external embedding call.

        Scores measure explicit token coverage and exact normalized phrases in
        source metadata/content. They are deliberately conservative: later
        intent, program, faculty, audience, and claim-compatibility gates still
        decide whether a chunk can support the answer.
        """

        query_normalized = normalize_program_text(query)
        query_tokens = _normalized_match_tokens(query)
        matches: List[VectorMatch] = []
        for chunk in chunks:
            searchable = "{} {} {} {} {}".format(
                chunk.title,
                chunk.category.replace("_", " "),
                chunk.program or "",
                chunk.faculty or "",
                chunk.content,
            )
            searchable_normalized = normalize_program_text(searchable)
            searchable_tokens = _normalized_match_tokens(searchable)
            coverage = (
                len(query_tokens & searchable_tokens) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            exact_phrase = bool(
                query_normalized
                and re.search(
                    rf"(?<![a-z0-9]){re.escape(query_normalized)}(?![a-z0-9])",
                    searchable_normalized,
                )
            )
            score = 1.0 if exact_phrase else coverage
            matches.append(VectorMatch(chunk=chunk, similarity_score=score))
        matches.sort(
            key=lambda match: (-match.similarity_score, match.chunk.chunk_id)
        )
        return matches[:top_k]

    @staticmethod
    def _authority_rank(chunk: KnowledgeChunk) -> tuple[int, int]:
        """Order verified evidence first, then freshness, before relevance."""

        quality_rank = int(chunk.manual_review) + int(
            chunk.extraction_status != "success"
        )
        currency_rank = {
            "current_date_sensitive": 0,
            "stable_reference": 1,
            "uncertain": 2,
            "historical": 3,
        }.get(chunk.currency_status, 4)
        return quality_rank, currency_rank

    def _rerank(
        self, query: str, match: VectorMatch, *, intent_query: str
    ) -> SearchResult:
        authority_adjustment = {
            "current_date_sensitive": 0.035,
            "stable_reference": 0.020,
            "uncertain": -0.070,
            "historical": -0.110,
        }.get(match.chunk.currency_status, -0.080)
        if match.chunk.manual_review:
            authority_adjustment -= 0.100
        if match.chunk.extraction_status != "success":
            authority_adjustment -= 0.080
        lexical_bonus = min(0.035, self._lexical_overlap(query, match.chunk.content) * 0.035)
        topic_bonus = self._topic_bonus(intent_query, match.chunk.category)
        metadata_bonus = self._metadata_bonus(intent_query, match.chunk)
        score = max(
            -1.0,
            min(
                1.0,
                match.similarity_score
                + authority_adjustment
                + lexical_bonus
                + topic_bonus
                + metadata_bonus
                + self._program_mismatch_penalty(intent_query, match.chunk),
            ),
        )
        return SearchResult(
            chunk=match.chunk,
            similarity_score=match.similarity_score,
            relevance_score=score,
        )

    @staticmethod
    def _program_mismatch_penalty(query: str, chunk: KnowledgeChunk) -> float:
        """Suppress near-duplicate rows belonging to a program other than the one named.

        Tuition/waiver tables store one row per program with near-identical
        text, so their embeddings tie on relevance.  When a query names exactly
        one program, rows for a different program (but never general policy
        chunks without a program) are penalized so they fall below the
        relevance threshold instead of replacing the named program's evidence.
        """

        if matched_faculty_phrase(query) is not None:
            return 0.0
        acronym = _single_named_program_acronym(query)
        if acronym is None:
            return 0.0
        program = getattr(chunk, "program", None)
        if not program:
            return 0.0
        program_name = str(program)
        # A complete catalog name is stronger evidence than an alias embedded
        # inside it. For example, "DIU-BCU Dual Award (MPH), UK" is an exact
        # catalog program, not the generic Master of Public Health row merely
        # because its official name contains the token MPH.
        if catalog_program_phrase(query, [program_name]) == program_name:
            return 0.0
        if _chunk_program_matches(program_name, acronym):
            return 0.0
        return _PROGRAM_MISMATCH_PENALTY

    def _suppress_duplicates(
        self,
        ranked: Iterable[SearchResult],
        *,
        top_k: int,
        similarity_threshold: float,
        relevance_threshold: float,
        preferred_categories: set[str],
        program_list_query: bool = False,
        exact_compatibility_chunk_ids: Optional[set[str]] = None,
        threshold_exempt_chunk_ids: Optional[set[str]] = None,
    ) -> List[SearchResult]:
        exact_compatibility_chunk_ids = exact_compatibility_chunk_ids or set()
        threshold_exempt_chunk_ids = threshold_exempt_chunk_ids or set()
        selected: List[SearchResult] = []
        source_counts: Counter[str] = Counter()
        seen_hashes = set()
        signatures: List[set[str]] = []
        for result in ranked:
            if (
                result.chunk.chunk_id not in exact_compatibility_chunk_ids
                and result.chunk.chunk_id not in threshold_exempt_chunk_ids
                and result.similarity_score < similarity_threshold
            ):
                continue
            if (
                result.chunk.chunk_id not in threshold_exempt_chunk_ids
                and result.relevance_score < relevance_threshold
            ):
                continue
            chunk = result.chunk
            if chunk.content_hash in seen_hashes:
                continue
            is_catalog_row = bool(
                program_list_query
                and chunk.category.casefold() == "undergraduate_programs"
                and chunk.program
            )
            if is_catalog_row:
                source_limit = top_k
            else:
                source_limit = (
                    self.max_results_per_source
                    if chunk.category.casefold() in preferred_categories
                    else min(2, self.max_results_per_source)
                )
            if source_counts[chunk.source_id] >= source_limit:
                continue
            signature = _meaningful_tokens(chunk.content)
            if not is_catalog_row and any(
                _jaccard(signature, previous) >= 0.88 for previous in signatures
            ):
                continue
            selected.append(result)
            source_counts[chunk.source_id] += 1
            seen_hashes.add(chunk.content_hash)
            signatures.append(signature)
            if len(selected) >= top_k:
                break
        return selected

    @staticmethod
    def _lexical_overlap(query: str, content: str) -> float:
        query_tokens = _meaningful_tokens(query)
        content_tokens = _meaningful_tokens(content)
        if not query_tokens:
            return 0.0
        return len(query_tokens & content_tokens) / len(query_tokens)

    @staticmethod
    def _topic_bonus(query: str, category: str) -> float:
        """Give small, explainable boosts to categories named by query intent."""

        return Retriever._topic_category_bonuses(query).get(category.casefold(), 0.0)

    @staticmethod
    def _topic_category_bonuses(query: str) -> dict[str, float]:
        lowered = query.casefold()
        bonuses: dict[str, float] = {}
        if re.search(r"documents?|certificate|transcript|ডকুমেন্ট|কাগজ", lowered):
            bonuses["required_admission_documents"] = 0.080
        if re.search(r"\bapply|application\b|আবেদন", lowered):
            bonuses["admission_application_process"] = 0.080
            bonuses["admission_process"] = 0.040
        if re.search(r"\bprograms?|courses?|degrees?\b|প্রোগ্রাম|কোর্স", lowered):
            bonuses["undergraduate_programs"] = 0.070
        if re.search(r"\btuition|fees?|cost\b|টিউশন|ফি|খরচ", lowered):
            bonuses["tuition_and_fees"] = 0.065
            if re.search(r"international|বিদেশ", lowered):
                bonuses["international_admission"] = 0.065
        if re.search(r"\bscholarships?\b|বৃত্তি|স্কলারশিপ", lowered):
            if re.search(r"international|foreign|বিদেশ", lowered):
                bonuses["international_scholarships"] = 0.090
            else:
                bonuses["scholarships"] = 0.070
        if re.search(r"\bfinancial\s+(?:aid|support|assistance)\b|আর্থিক", lowered):
            bonuses["financial_aid"] = 0.090
        if re.search(r"\bwaivers?\b|ওয়েভার|ওয়েভার", lowered):
            bonuses["waivers"] = 0.070
        if re.search(r"\b(?:waiver|tuition\s+fee)\s+calculator\b|ক্যালকুলেটর", lowered):
            bonuses["waiver_calculator"] = 0.100
        if re.search(r"\badmission\s+test\s+(?:schedule|date|time)\b|সময়সূচি|তারিখ", lowered):
            bonuses["admission_overview"] = 0.080
            bonuses["admission_notices"] = 0.060
        if re.search(r"\b(?:admission\s+test\s+)?seat\s+plan\b|সিট\s+প্ল্যান", lowered):
            bonuses["admission_test_result"] = 0.080
            bonuses["admission_overview"] = 0.060
        if re.search(r"\badmission\s+test\s+results?\b|ফলাফল", lowered):
            bonuses["admission_test_result"] = 0.100
        if re.search(r"\bcredit\s+transfer\b|ক্রেডিট\s+ট্রান্সফার", lowered):
            bonuses["credit_transfer_guidelines"] = 0.100
        if re.search(r"\bguardians?\b|অভিভাবক", lowered):
            bonuses["guardian_guidelines"] = 0.100
        if re.search(r"\bpayment\s+(?:guidelines?|instructions?|process|methods?)\b|পেমেন্ট", lowered):
            bonuses["payment_guidelines"] = 0.100
        if re.search(r"\blife\s+insurance\b|জীবন\s+বীমা|লাইফ\s+ইন্স্যুরেন্স", lowered):
            bonuses["life_insurance"] = 0.100
        if re.search(r"\bcurrent\s+admission|admission\s+details", lowered):
            bonuses["admission_overview"] = 0.070
        if re.search(r"\b(?:deadline|last\s+date|when\s+to\s+apply)\b|শেষ\s+তারিখ", lowered):
            bonuses["admission_notices"] = 0.100
            bonuses["current_admission_information"] = 0.080
            bonuses["admission_overview"] = 0.050
        return bonuses

    @staticmethod
    def _metadata_bonus(query: str, chunk: KnowledgeChunk) -> float:
        """Favor broad summaries and an explicitly named program's exact rows."""

        category = str(getattr(chunk, "category", "")).casefold()
        program_value = getattr(chunk, "program", None)
        program = str(program_value).casefold() if program_value else ""
        lowered = query.casefold()
        bonus = 0.0
        if (
            category == "undergraduate_programs"
            and not program
            and re.search(r"\bprograms?|courses?|degrees?\b", lowered)
        ):
            bonus += 0.045
        marker = _single_named_program_acronym(query)
        if marker is not None:
            if not _chunk_program_matches(program, marker):
                return bonus
            bonus += 0.035
            expected_level_matches = _program_level_matches(query, program, marker)
            if expected_level_matches and PROGRAM_BY_MARKER[marker].default_level == "postgraduate":
                bonus += 0.030
            elif expected_level_matches:
                bonus += 0.025
        if (
            str(getattr(chunk, "content_type", "")).casefold() == "table"
            and _STRUCTURED_DATA_PATTERN.search(lowered)
        ):
            bonus += 0.050
        if category in {"scholarships", "waivers"}:
            focus_tokens = _aid_focus_tokens(query)
            if focus_tokens and _chunk_matches_aid_focus(chunk, focus_tokens):
                focus_strength = _aid_focus_strength(chunk, focus_tokens)
                bonus += min(0.070, 0.020 + 0.025 * (focus_strength - 1))
        return bonus


def create_retriever(settings: Optional[RagSettings] = None) -> Retriever:
    """Construct the configured production or explicit local retriever."""

    settings = settings or get_rag_settings()
    store = create_vector_store(settings)
    store.setup()
    embedder = create_embedder(
        settings,
        model_name=store.embedding_model_name,
        model_revision=store.embedding_model_revision,
        dimension=store.embedding_dimension,
    )
    reranker = None
    if settings.rag_reranker_enabled:
        reranker = CrossEncoderReranker(settings.rag_reranker_model_name)
    return Retriever(
        embedder,
        store,
        min_similarity_score=settings.rag_min_similarity_score,
        min_relevance_score=settings.rag_min_relevance_score,
        candidate_multiplier=settings.rag_candidate_multiplier,
        max_results_per_source=settings.rag_max_results_per_source,
        reranker=reranker,
    )


class CrossEncoderReranker:
    """Lazy optional cross-encoder used only when explicitly enabled."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def score(self, query: str, documents: Sequence[str]) -> List[float]:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return [
            float(score)
            for score in self._model.predict([(query, document) for document in documents])
        ]


def retrieve(
    query: str,
    top_k: int = 5,
    category: Optional[str] = None,
    program: Optional[str] = None,
    **options: object,
) -> List[SearchResult]:
    """Convenience API using the environment-configured retriever."""

    return create_retriever().retrieve(
        query,
        top_k=top_k,
        category=category,
        program=program,
        **options,
    )


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(unicodedata.normalize("NFKC", text))
        if len(token) > 1
    }


def _aid_focus_tokens(query: str) -> set[str]:
    """Extract explicit aid-category qualifiers from normalized user wording."""

    return _meaningful_tokens(query) - _AID_FOCUS_IGNORED_TOKENS


def _chunk_matches_aid_focus(chunk: KnowledgeChunk, focus_tokens: set[str]) -> bool:
    """Require verified aid evidence to contain every explicit focus token."""

    searchable = "{} {} {}".format(
        chunk.title,
        chunk.program or "",
        chunk.content,
    )
    if not focus_tokens <= _meaningful_tokens(searchable):
        return False
    content = chunk.content.strip()
    content_tokens = [
        token.casefold()
        for token in _TOKEN_RE.findall(unicodedata.normalize("NFKC", content))
    ]
    # Text extraction may split immediately after the next subsection title,
    # leaving a fragment such as ``c) Female Quota:`` at the end of the
    # preceding chunk. A heading without any following row/value is navigation,
    # not evidence for that qualifier. Structured table rows remain eligible.
    if (
        str(chunk.content_type).casefold() != "table"
        and content.endswith(":")
        and focus_tokens <= set(content_tokens[-4:])
        and all(content_tokens.count(token) == 1 for token in focus_tokens)
    ):
        return False
    folded = searchable.casefold()
    # Overlapping text chunks can end with only the next section's heading.
    # Do not treat a single qualifier at the very end as complete evidence.
    return not all(
        folded.count(token) == 1 and folded.find(token) >= len(folded) * 0.8
        for token in focus_tokens
    )


def _aid_focus_strength(chunk: KnowledgeChunk, focus_tokens: set[str]) -> int:
    """Measure repeated focus evidence, capped to avoid dominating authority."""

    searchable = "{} {} {}".format(
        chunk.title,
        chunk.program or "",
        chunk.content,
    ).casefold()
    return max(1, min(3, min(searchable.count(token) for token in focus_tokens)))


def _base_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query)
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    if not normalized:
        raise ValueError("query cannot be blank")
    return normalized


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _contains_ascii_token(text: str, token: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text))


def _matched_catalog_faculty(
    query: str, candidates: Sequence[VectorMatch]
) -> Optional[str]:
    """Resolve an explicit faculty from source metadata, not a maintained list."""

    query_tokens = _meaningful_tokens(query) - {
        "available",
        "courses",
        "degrees",
        "diu",
        "department",
        "departments",
        "faculty",
        "offer",
        "offered",
        "programs",
        "show",
        "which",
    }
    if not query_tokens:
        return None
    scores: dict[str, int] = {}
    display_names: dict[str, str] = {}
    for match in candidates:
        faculty = str(match.chunk.faculty or "").strip()
        if not faculty:
            continue
        key = faculty.casefold()
        display_names[key] = faculty
        faculty_tokens = _meaningful_tokens(faculty) - {"and", "faculty", "of"}
        overlap = len(query_tokens & faculty_tokens)
        acronym_tokens = [
            token.casefold()
            for token in _TOKEN_RE.findall(unicodedata.normalize("NFKC", faculty))
            if token.casefold() not in {"and", "faculty", "of"}
        ]
        initials = "".join(token[0] for token in acronym_tokens if token)
        acronyms = {initials, "f{}".format(initials)} if initials else set()
        if query_tokens & acronyms:
            overlap += 1
        if overlap:
            scores[key] = max(scores.get(key, 0), overlap)
    if not scores:
        return None
    best = max(scores.values())
    winners = [key for key, score in scores.items() if score == best]
    return display_names[winners[0]] if len(winners) == 1 else None


def _catalog_faculty_focus(query: str) -> str:
    """Strip generic list wording so semantic search can surface faculty rows."""

    ignored = {
        "are",
        "available",
        "courses",
        "degrees",
        "department",
        "departments",
        "diu",
        "does",
        "faculty",
        "in",
        "of",
        "offer",
        "offered",
        "programs",
        "the",
        "what",
        "which",
    }
    tokens = [
        token.casefold()
        for token in _TOKEN_RE.findall(unicodedata.normalize("NFKC", query))
        if token.casefold() not in ignored
    ]
    return " ".join(tokens)


def _excludes_engineering(query: str) -> bool:
    """Detect questions about programs outside the Engineering faculty."""

    lowered = unicodedata.normalize("NFKC", query).casefold()
    return bool(
        re.search(
            r"\b(?:outside|other than|except|excluding|not|non-?)\b.*\bengineering\b",
            lowered,
        )
    )


def _is_engineering_faculty_chunk(chunk: object) -> bool:
    faculty = str(getattr(chunk, "faculty", "") or "").casefold()
    return bool(faculty) and (
        faculty == "engineering" or faculty.endswith(" engineering")
    )


def _evidence_matches_query_context(
    query: str,
    chunk: KnowledgeChunk,
    *,
    program_phrase: Optional[str] = None,
) -> bool:
    """Reject evidence that cannot answer the query's explicit fact and program.

    Dense similarity alone cannot distinguish near-identical fee rows or an
    admission GPA from a waiver-maintenance SGPA. This compatibility gate uses
    only stable metadata and wording already present in the query/chunk; it does
    not encode any changing admission value.
    """

    category = chunk.category.casefold()
    intent = _fact_intent(query)
    acronym = _single_named_program_acronym(query)
    named_markers = _named_program_markers(query)

    def program_matches(program: str) -> bool:
        if program_phrase is not None:
            if not program_phrase_matches(program, program_phrase):
                return False
            return _program_level_matches(query, program, acronym or "")
        if named_markers:
            return any(
                _chunk_program_matches(program, marker)
                and _program_level_matches(query, program, marker)
                for marker in named_markers
            )
        if acronym is None:
            return True
        return _chunk_program_matches(program, acronym) and _program_level_matches(
            query, program, acronym
        )

    if intent == "tuition":
        audience = tuition_audience(query)
        if audience == "international":
            if category != "international_admission":
                return False
        elif audience == "both":
            if category not in {"international_admission", "tuition_and_fees"}:
                return False
        elif category != "tuition_and_fees":
            return False
        if audience == "local" and "$" in chunk.content:
            return False
        if program_phrase is not None or named_markers:
            program = str(chunk.program or "")
            return bool(program) and program_matches(program)
        return True

    if intent == "admission_gpa" and acronym is not None:
        if category != "program_specific_admission":
            return False
        program = str(chunk.program or "")
        return bool(program) and program_matches(program)

    if intent == "waiver":
        if category != "waivers":
            return False
        if not named_markers and program_phrase is None:
            return True
        if _GPA_QUERY_PATTERN.search(query) and chunk.content_type.casefold() != "table":
            return False
        if chunk.program:
            return program_matches(str(chunk.program))
        if not named_markers:
            return False
        return any(
            _chunk_content_matches_program(chunk.content, marker)
            for marker in named_markers
        )

    if intent == "scholarship":
        return category == "scholarships"

    if intent == "international_scholarship":
        return category == "international_scholarships"

    if intent == "financial_aid":
        return category == "financial_aid"

    if intent == "waiver_calculator":
        return category == "waiver_calculator"

    if intent == "admission_test_schedule":
        if category not in {
            "admission_overview",
            "admission_notices",
            "current_admission_information",
        }:
            return False
        return _scope_matches_chunk(query, chunk)

    if intent == "admission_test_seat_plan":
        if category not in {
            "admission_test_result",
            "admission_overview",
            "admission_notices",
        }:
            return False
        return _scope_matches_chunk(query, chunk)

    if intent == "admission_test_result":
        return category == "admission_test_result" and _scope_matches_chunk(query, chunk)

    if intent == "credit_transfer":
        return category == "credit_transfer_guidelines"

    if intent == "guardian_guidelines":
        return category == "guardian_guidelines"

    if intent == "payment_guidelines":
        return category == "payment_guidelines"

    if intent == "life_insurance":
        return category == "life_insurance"

    if intent == "documents":
        return category == "required_admission_documents" and _document_level_matches(
            query, chunk
        )

    if intent == "admission_process":
        return category == "admission_process"

    if intent == "online_application":
        return category == "admission_application_process"

    if intent == "diploma_application":
        return category == "admission_application_process"

    if intent == "eligibility":
        if category != "undergraduate_programs":
            return False
        if not named_markers and program_phrase is None:
            return True
        program = str(chunk.program or "")
        return bool(program) and program_matches(program)

    if intent == "program_info":
        if category != "undergraduate_programs":
            return False
        if not named_markers and program_phrase is None:
            return True
        program = str(chunk.program or "")
        return bool(program) and program_matches(program)

    if intent == "program_catalog":
        if category != "undergraduate_programs":
            return False
        faculty_phrase = matched_faculty_phrase(query)
        if faculty_phrase is None:
            return True
        return bool(chunk.faculty) and faculty_names_match(
            str(chunk.faculty), faculty_phrase
        )

    if intent == "contact":
        return category == "admission_contact_information"

    if intent == "international":
        return category == "international_admission"

    if intent == "admission_overview":
        return category in {"admission_overview", "current_admission_information"}

    if intent == "deadline":
        if program_phrase is not None:
            searchable = "{} {}".format(chunk.program or "", chunk.content)
            if not program_phrase_matches(searchable, program_phrase):
                return False
        if category not in {
            "admission_notices",
            "admission_overview",
            "current_admission_information",
        }:
            return False
        return _scope_matches_chunk(query, chunk)

    if intent == "fact_check":
        focus_tokens = _claim_focus_tokens(query)
        if not focus_tokens:
            return False
        searchable = "{} {} {} {}".format(
            chunk.title,
            chunk.program or "",
            chunk.faculty or "",
            chunk.content,
        )
        return focus_tokens <= _normalized_match_tokens(searchable)

    if (acronym is not None or program_phrase is not None) and intent is None:
        if category not in {"undergraduate_programs", "program_specific_admission"}:
            return False
        program = str(chunk.program or "")
        return bool(program) and program_matches(program)

    return True


def _fact_intent(query: str) -> Optional[str]:
    """Return the fact type requiring strict evidence compatibility."""

    # GPA thresholds are a special high-risk fact: only an explicit official
    # program-admission record may answer them. A catalog row proves that a
    # program exists, not that an applicant meets its GPA requirements.
    if _ADMISSION_GPA_PATTERN.search(query):
        return "admission_gpa"
    analysis = analyze_query(query, program_phrase=_matched_program_phrase(query))
    mapped = {
        QueryIntent.WAIVER: "waiver",
        QueryIntent.SCHOLARSHIP: "scholarship",
        QueryIntent.TUITION: "tuition",
        QueryIntent.DOCUMENTS: "documents",
        QueryIntent.APPLICATION_PROCESS: "admission_process",
        QueryIntent.ONLINE_APPLICATION: "online_application",
        QueryIntent.DIPLOMA_APPLICATION: "diploma_application",
        QueryIntent.ELIGIBILITY: "eligibility",
        QueryIntent.PROGRAM_INFO: "program_info",
        QueryIntent.PROGRAM_CATALOG: "program_catalog",
        QueryIntent.DEADLINE: "deadline",
        QueryIntent.CONTACT: "contact",
        QueryIntent.INTERNATIONAL: "international",
        QueryIntent.INTERNATIONAL_SCHOLARSHIP: "international_scholarship",
        QueryIntent.ADMISSION_TEST_SCHEDULE: "admission_test_schedule",
        QueryIntent.ADMISSION_TEST_SEAT_PLAN: "admission_test_seat_plan",
        QueryIntent.ADMISSION_TEST_RESULT: "admission_test_result",
        QueryIntent.CREDIT_TRANSFER: "credit_transfer",
        QueryIntent.GUARDIAN_GUIDELINES: "guardian_guidelines",
        QueryIntent.PAYMENT_GUIDELINES: "payment_guidelines",
        QueryIntent.WAIVER_CALCULATOR: "waiver_calculator",
        QueryIntent.FINANCIAL_AID: "financial_aid",
        QueryIntent.LIFE_INSURANCE: "life_insurance",
        QueryIntent.ADMISSION_OVERVIEW: "admission_overview",
        QueryIntent.FACT_CHECK: "fact_check",
    }.get(analysis.intent)
    if mapped is not None:
        return mapped

    if _WAIVER_PATTERN.search(query):
        return "waiver"
    if _SCHOLARSHIP_PATTERN.search(query):
        return "scholarship"
    if _TUITION_PATTERN.search(query):
        return "tuition"
    if _DOCUMENT_PATTERN.search(query):
        return "documents"
    if _DEADLINE_PATTERN.search(query):
        return "deadline"
    if _ADMISSION_PROCESS_PATTERN.search(query):
        return "admission_process"
    return None


def _program_lane_category(
    intent: Optional[QueryIntent], query: str
) -> Optional[str]:
    """Narrow only the supplemental program-name lane to compatible evidence."""

    if intent is QueryIntent.TUITION:
        audience = tuition_audience(query)
        if audience == "both":
            return None
        return "international_admission" if audience == "international" else "tuition_and_fees"
    if intent in {QueryIntent.PROGRAM_INFO, QueryIntent.ELIGIBILITY}:
        return "undergraduate_programs"
    if intent is QueryIntent.WAIVER:
        return "waivers"
    return None


def _exact_topic_category(intent: Optional[QueryIntent]) -> Optional[str]:
    """Return a one-to-one evidence category for an explicitly named topic."""

    return {
        QueryIntent.ONLINE_APPLICATION: "admission_application_process",
        QueryIntent.ADMISSION_TEST_RESULT: "admission_test_result",
        QueryIntent.CREDIT_TRANSFER: "credit_transfer_guidelines",
        QueryIntent.GUARDIAN_GUIDELINES: "guardian_guidelines",
        QueryIntent.PAYMENT_GUIDELINES: "payment_guidelines",
        QueryIntent.INTERNATIONAL_SCHOLARSHIP: "international_scholarships",
        QueryIntent.WAIVER_CALCULATOR: "waiver_calculator",
        QueryIntent.FINANCIAL_AID: "financial_aid",
        QueryIntent.LIFE_INSURANCE: "life_insurance",
    }.get(intent)


def _intent_candidate_categories(
    intent: Optional[QueryIntent], query: str
) -> tuple[str, ...]:
    """Return stable evidence categories compatible with a classified intent.

    These are schema routing labels, not admission facts. The result is used as
    an additional candidate lane and never bypasses evidence compatibility.
    """

    if intent is QueryIntent.TUITION:
        audience = tuition_audience(query)
        if audience == "international":
            return ("international_admission",)
        if audience == "both":
            return ("tuition_and_fees", "international_admission")
        return ("tuition_and_fees",)
    return {
        QueryIntent.APPLICATION_PROCESS: ("admission_process",),
        QueryIntent.ONLINE_APPLICATION: ("admission_application_process",),
        QueryIntent.DOCUMENTS: ("required_admission_documents",),
        QueryIntent.DIPLOMA_APPLICATION: ("admission_application_process",),
        QueryIntent.SCHOLARSHIP: ("scholarships",),
        QueryIntent.WAIVER: ("waivers",),
        QueryIntent.PROGRAM_CATALOG: ("undergraduate_programs",),
        QueryIntent.PROGRAM_INFO: ("undergraduate_programs",),
        QueryIntent.ELIGIBILITY: ("undergraduate_programs",),
        QueryIntent.DEADLINE: (
            "admission_notices",
            "current_admission_information",
            "admission_overview",
        ),
        QueryIntent.CONTACT: ("admission_contact_information",),
        QueryIntent.INTERNATIONAL: ("international_admission",),
        QueryIntent.INTERNATIONAL_SCHOLARSHIP: ("international_scholarships",),
        QueryIntent.ADMISSION_TEST_SCHEDULE: (
            "admission_overview",
            "admission_notices",
            "current_admission_information",
        ),
        QueryIntent.ADMISSION_TEST_SEAT_PLAN: (
            "admission_test_result",
            "admission_overview",
            "admission_notices",
        ),
        QueryIntent.ADMISSION_TEST_RESULT: ("admission_test_result",),
        QueryIntent.CREDIT_TRANSFER: ("credit_transfer_guidelines",),
        QueryIntent.GUARDIAN_GUIDELINES: ("guardian_guidelines",),
        QueryIntent.PAYMENT_GUIDELINES: ("payment_guidelines",),
        QueryIntent.WAIVER_CALCULATOR: ("waiver_calculator",),
        QueryIntent.FINANCIAL_AID: ("financial_aid",),
        QueryIntent.LIFE_INSURANCE: ("life_insurance",),
        QueryIntent.ADMISSION_OVERVIEW: ("admission_overview",),
    }.get(intent, ())


def _normalized_match_tokens(text: str) -> set[str]:
    """Return conservative lexical forms for claim/evidence compatibility."""

    tokens = _meaningful_tokens(text)
    forms = set(tokens)
    for token in tokens:
        if len(token) > 4 and token.endswith("ies"):
            forms.add(token[:-3] + "y")
        elif (
            len(token) > 3
            and token.endswith("s")
            and not token.endswith("ss")
            and token not in {"does", "has", "this", "thus", "was"}
        ):
            forms.add(token[:-1])
    return forms


def _claim_focus_tokens(query: str) -> set[str]:
    """Keep the asserted facts that official evidence must explicitly contain."""

    return _normalized_match_tokens(query) - _CLAIM_FOCUS_IGNORED_TOKENS


def _scope_focus_tokens(query: str) -> set[str]:
    """Extract explicit scope from a current date/result query."""

    return _normalized_match_tokens(query) - _SCOPE_FOCUS_IGNORED_TOKENS


def _scope_matches_chunk(query: str, chunk: KnowledgeChunk) -> bool:
    """Require explicit faculty/semester/year scope to survive retrieval."""

    focus = _scope_focus_tokens(query)
    if not focus:
        return True
    searchable = "{} {} {} {}".format(
        chunk.title,
        chunk.program or "",
        chunk.faculty or "",
        chunk.content,
    )
    return focus <= _normalized_match_tokens(searchable)


def _chunk_content_matches_program(content: str, acronym: str) -> bool:
    item = PROGRAM_BY_MARKER.get(acronym)
    if item is None:
        return False
    return program_phrase_matches(content, item.canonical)


def _program_level_matches(query: str, program: str, acronym: str) -> bool:
    """Keep the intended degree level when an acronym exists at both levels."""

    return program_level_matches(query, program, acronym)


def _document_level_matches(query: str, chunk: KnowledgeChunk) -> bool:
    """Keep a checklist for the applicant level explicitly named in the query."""

    lowered_query = query.casefold()
    program = str(chunk.program or "").casefold()
    asks_diploma = bool(re.search(r"\bdiploma\b", lowered_query))
    asks_master = bool(re.search(r"\b(?:masters?|postgraduate)\b", lowered_query))
    asks_bachelor = bool(
        re.search(r"\b(?:bachelors?|undergraduate)\b", lowered_query)
    )
    asks_online = bool(re.search(r"\bonline\b", lowered_query))
    asks_international = bool(
        re.search(r"\b(?:international|foreign|overseas)\b", lowered_query)
        or re.search(r"বিদেশি|আন্তর্জাতিক", query)
    )
    if asks_international:
        searchable = "{} {} {}".format(
            chunk.title, chunk.program or "", chunk.content
        ).casefold()
        return bool(
            re.search(r"\b(?:international|foreign|overseas)\b", searchable)
            or re.search(r"বিদেশি|আন্তর্জাতিক", searchable)
        )
    if asks_online:
        return "online" in program
    if asks_diploma:
        return "diploma" in program
    if asks_master:
        return "master" in program and "diploma" not in program
    if asks_bachelor:
        return (
            "bachelor" in program
            and "diploma" not in program
            and "online" not in program
        )
    return True


def _validated_score(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number between -1 and 1")
    parsed = float(value)
    if not math.isfinite(parsed) or not -1.0 <= parsed <= 1.0:
        raise ValueError(f"{name} must be a finite number between -1 and 1")
    return parsed
