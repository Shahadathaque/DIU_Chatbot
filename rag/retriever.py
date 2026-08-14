"""Authority-aware semantic retrieval over the DIU knowledge base."""

from __future__ import annotations

import re
import unicodedata
import math
from collections import Counter
from typing import Iterable, List, Optional, Sequence

from rag.config import RagSettings, get_rag_settings
from rag.embeddings import Embedder, SentenceTransformerEmbedder
from rag.models import KnowledgeChunk, SearchFilters, SearchResult, VectorMatch
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
    r"eligibility|eligible|deadlines?|requirements?|contacts?|campus|semesters?|"
    r"vorti|bhorti)\b|ভর্তি|আবেদন|ডকুমেন্ট|কাগজপত্র|কাগজ|টিউশন|ফি|খরচ|"
    r"বৃত্তি|স্কলারশিপ|ওয়েভার|ওয়েভার|প্রোগ্রাম|কোর্স|যোগাযোগ)"
)
_PROGRAM_QUERY_MARKERS = {
    "cse": "Computer Science and Engineering",
    "swe": "Software Engineering",
    "cis": "Computing and Information System",
    "itm": "Information Technology & Management",
    "mct": "Multimedia & Creative Technology",
    "rme": "Robotics and Mechatronics Engineering",
    "bba": "Bachelor of Business Administration",
    "llb": "LL.B.",
    "llm": "LL.M.",
    "mba": "Master of Business Administration",
    "mds": "Master of Development Studies",
    "mph": "Master of Public Health",
    "bph": "Bachelor of Public Health",
    "bss": "BSS",
    "mss": "MSS",
    "barch": "Bachelor of Architecture",
    "ce": "Civil Engineering",
    "civil": "Civil Engineering",
    "eee": "Electrical and Electronic Engineering",
    "ice": "Information & Communication Engineering",
    "jmc": "Journalism, Media and Communication",
    "thm": "Tourism & Hospitality Management",
    "ags": "Agricultural Science",
    "esdm": "Environmental Science and Disaster Management",
    "pess": "Physical Education and Sports Science",
    "nfe": "Nutrition and Food Engineering",
    "bre": "Real Estate",
    "law": "LL.B.",
    "pharmacy": "Bachelor of Pharmacy",
    "textile": "Textile Engineering",
    "architecture": "Bachelor of Architecture",
    "agricultural": "Agricultural Science",
    "tourism": "Tourism & Hospitality Management",
    "accounting": "BBA in Accounting",
    "marketing": "BBA in Marketing",
    "finance": "BBA in Finance & Banking",
    "banking": "BBA in Finance & Banking",
    "management": "BBA in Management",
    "entrepreneurship": "Bachelor of Entrepreneurship",
    "বিবিএ": "Bachelor of Business Administration",
    "আইন": "LL.B.",
    "ফার্মেসি": "Bachelor of Pharmacy",
    "টেক্সটাইল": "Textile Engineering",
}
_PROGRAM_LIST_PATTERN = re.compile(
    r"(?i)(?:"
    r"\b(?:what|which)\b(?!\s+faculty\b).*\b(?:programs?|courses?|degrees?)\b"
    r"|\b(?:list|show|name|all)\b.*\b(?:programs?|courses?|degrees?)\b"
    r"|\b(?:programs?|courses?|degrees?)\b.*\b(?:available|offered)\b"
    r"|\bprogram\b.*\b(?:ache|gulo|ki)\b"
    r"|প্রোগ্রাম|কোর্স)"
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
_DEFAULT_POSTGRADUATE_PROGRAM_MARKERS = {"llm", "mba", "mds", "mph", "mss"}


def _matched_program_phrase(query: str) -> Optional[str]:
    """Return the official program phrase named by a program-related query."""

    matches = _named_program_markers(query)
    return _PROGRAM_QUERY_MARKERS[matches[0]] if len(matches) == 1 else None


def _named_program_acronyms(query: str) -> List[str]:
    """Return every program acronym the query explicitly names."""

    return _named_program_markers(query)


def _named_program_markers(query: str) -> List[str]:
    """Prefer exact catalog phrases over broader acronym/keyword matches."""

    lowered = unicodedata.normalize("NFKC", query).casefold()
    exact: List[str] = []
    marker_only: List[str] = []
    exact_phrases: set[str] = set()
    marker_phrases: set[str] = set()
    for acronym, official_phrase in _PROGRAM_QUERY_MARKERS.items():
        phrase = official_phrase.casefold()
        if phrase in lowered:
            if phrase not in exact_phrases:
                exact.append(acronym)
                exact_phrases.add(phrase)
        elif _contains_ascii_token(lowered, acronym) and phrase not in marker_phrases:
            marker_only.append(acronym)
            marker_phrases.add(phrase)
    # “BBA in Finance & Banking” contains the BBA marker but explicitly names
    # the more specific catalog phrase. In contrast, “CSE or SWE” has two marker
    # matches and remains intentionally ambiguous.
    return exact if exact else marker_only


def _single_named_program_acronym(query: str) -> Optional[str]:
    """Return the sole named program acronym, or None when none/multiple."""

    found = _named_program_acronyms(query)
    return found[0] if len(found) == 1 else None


def _chunk_program_matches(program: str, acronym: str) -> bool:
    """Return whether a chunk's program metadata belongs to the named acronym."""

    folded = program.casefold()
    phrase = _PROGRAM_QUERY_MARKERS[acronym].casefold()
    if phrase and phrase in folded:
        return True
    if acronym == "bba":
        return folded.strip(" .") == "bba"
    if _contains_ascii_token(folded, acronym):
        return True
    return bool(
        re.search(r"\(\s*" + re.escape(acronym) + r"\s*\)", folded, re.IGNORECASE)
    )


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

    lowered = unicodedata.normalize("NFKC", query).casefold()
    names_diu = any(marker in lowered for marker in _DIU_PHRASES) or any(
        _contains_ascii_token(lowered, acronym) for acronym in _DIU_ACRONYMS
    )
    return (
        names_diu
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
        intent_query = _base_query(query)
        if not is_likely_admission_query(intent_query):
            return []
        program_list_query = bool(_PROGRAM_LIST_PATTERN.search(intent_query))
        normalized = normalize_query(query)
        query_embedding = self.embedder.embed_query(normalized)
        filters = SearchFilters(
            category=category,
            program=program,
            include_historical=include_historical,
            include_uncertain=include_uncertain,
            include_manual_review=include_manual_review,
            include_partial=include_partial,
        )
        candidate_limit = max(top_k * self.candidate_multiplier, top_k)
        authoritative_filters = SearchFilters(category=category, program=program)
        authoritative_candidates = self.vector_store.search(
            query_embedding,
            top_k=candidate_limit,
            filters=authoritative_filters,
        )
        if any(
            (
                include_historical,
                include_uncertain,
                include_manual_review,
                include_partial,
            )
        ):
            expanded_candidates = self.vector_store.search(
                query_embedding,
                top_k=candidate_limit + len(authoritative_candidates),
                filters=filters,
            )
            candidates = self._merge_candidates(
                authoritative_candidates, expanded_candidates
            )
        else:
            candidates = authoritative_candidates
        program_phrase = _matched_program_phrase(normalized)
        if program_phrase is None and _PROGRAM_LIST_PATTERN.search(normalized):
            program_phrase = _PROGRAM_CATALOG_QUERY
        if program_phrase is not None:
            phrase_embedding = self.embedder.embed_query(program_phrase)
            program_candidates = self.vector_store.search(
                phrase_embedding,
                top_k=candidate_limit,
                filters=SearchFilters(category=category, program=program),
            )
            candidates = self._merge_candidates(program_candidates, candidates)
        named_faculty = None
        if program_list_query:
            faculty_focus = _catalog_faculty_focus(intent_query)
            if faculty_focus:
                focus_embedding = self.embedder.embed_query(faculty_focus)
                focus_candidates = self.vector_store.search(
                    focus_embedding,
                    top_k=candidate_limit,
                    filters=SearchFilters(category=category, program=program),
                )
                candidates = self._merge_candidates(focus_candidates, candidates)
            named_faculty = _matched_catalog_faculty(intent_query, candidates)
        if named_faculty is not None:
            candidates = [
                match
                for match in candidates
                if match.chunk.content_type.casefold() == "table"
                and str(match.chunk.faculty or "").casefold()
                == named_faculty.casefold()
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
        candidates = [
            match
            for match in candidates
            if _evidence_matches_query_context(intent_query, match.chunk)
        ]
        ranked = [
            self._rerank(normalized, match, intent_query=intent_query)
            for match in candidates
        ]
        ranked.sort(
            key=lambda result: (
                *self._authority_rank(result.chunk),
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
            similarity_threshold=-1.0 if program_list_query else similarity_threshold,
            relevance_threshold=-1.0 if program_list_query else relevance_threshold,
            preferred_categories=set(self._topic_category_bonuses(intent_query)),
            program_list_query=program_list_query,
        )

    @staticmethod
    def _merge_candidates(
        authoritative: Sequence[VectorMatch], expanded: Sequence[VectorMatch]
    ) -> List[VectorMatch]:
        """Merge search lanes while preserving the authoritative copy of a row."""

        merged = {match.chunk.chunk_id: match for match in expanded}
        merged.update({match.chunk.chunk_id: match for match in authoritative})
        return list(merged.values())

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

        acronym = _single_named_program_acronym(query)
        if acronym is None:
            return 0.0
        program = getattr(chunk, "program", None)
        if not program:
            return 0.0
        if _chunk_program_matches(str(program), acronym):
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
    ) -> List[SearchResult]:
        selected: List[SearchResult] = []
        source_counts: Counter[str] = Counter()
        seen_hashes = set()
        signatures: List[set[str]] = []
        for result in ranked:
            if result.similarity_score < similarity_threshold:
                continue
            if result.relevance_score < relevance_threshold:
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
            bonuses["scholarships"] = 0.070
        if re.search(r"\bwaivers?\b|ওয়েভার|ওয়েভার", lowered):
            bonuses["waivers"] = 0.070
        if re.search(r"\bcurrent\s+admission|admission\s+details", lowered):
            bonuses["admission_overview"] = 0.070
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
        for acronym, official_phrase in _PROGRAM_QUERY_MARKERS.items():
            if not _contains_ascii_token(lowered, acronym):
                if official_phrase.casefold() not in lowered:
                    continue
            if official_phrase.casefold() not in program:
                continue
            bonus += 0.035
            asks_for_master = bool(
                re.search(r"\b(?:masters?|m\.?\s*sc\.?|postgraduate)\b", lowered)
            )
            is_master = bool(re.match(r"m\.?\s*sc", program))
            is_bachelor = bool(re.match(r"b\.?\s*sc", program))
            if asks_for_master and is_master:
                bonus += 0.030
            elif not asks_for_master and is_bachelor:
                bonus += 0.025
            break
        if (
            str(getattr(chunk, "content_type", "")).casefold() == "table"
            and _STRUCTURED_DATA_PATTERN.search(lowered)
        ):
            bonus += 0.050
        return bonus


def create_retriever(settings: Optional[RagSettings] = None) -> Retriever:
    """Construct the configured production or explicit local retriever."""

    settings = settings or get_rag_settings()
    store = create_vector_store(settings)
    store.setup()
    embedder = SentenceTransformerEmbedder(
        store.embedding_model_name,
        expected_dimension=store.embedding_dimension,
        model_revision=store.embedding_model_revision,
        batch_size=settings.embedding_batch_size,
        device=settings.embedding_device,
    )
    return Retriever(
        embedder,
        store,
        min_similarity_score=settings.rag_min_similarity_score,
        min_relevance_score=settings.rag_min_relevance_score,
        candidate_multiplier=settings.rag_candidate_multiplier,
        max_results_per_source=settings.rag_max_results_per_source,
    )


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


def _evidence_matches_query_context(query: str, chunk: KnowledgeChunk) -> bool:
    """Reject evidence that cannot answer the query's explicit fact and program.

    Dense similarity alone cannot distinguish near-identical fee rows or an
    admission GPA from a waiver-maintenance SGPA. This compatibility gate uses
    only stable metadata and wording already present in the query/chunk; it does
    not encode any changing admission value.
    """

    category = chunk.category.casefold()
    intent = _fact_intent(query)
    acronym = _single_named_program_acronym(query)

    if intent == "tuition":
        if _INTERNATIONAL_CURRENCY_PATTERN.search(query):
            if category != "international_admission":
                return False
        elif category != "tuition_and_fees":
            return False
        if _LOCAL_CURRENCY_PATTERN.search(query) and "$" in chunk.content:
            return False
        if acronym is not None:
            program = str(chunk.program or "")
            return bool(program) and _chunk_program_matches(
                program, acronym
            ) and _program_level_matches(query, program, acronym)
        return True

    if intent == "admission_gpa" and acronym is not None:
        if category != "program_specific_admission":
            return False
        program = str(chunk.program or "")
        return bool(program) and _chunk_program_matches(program, acronym)

    if intent == "waiver":
        if category != "waivers":
            return False
        if acronym is None:
            return True
        if _GPA_QUERY_PATTERN.search(query) and chunk.content_type.casefold() != "table":
            return False
        if chunk.program:
            return _chunk_program_matches(str(chunk.program), acronym)
        return _chunk_content_matches_program(chunk.content, acronym)

    if intent == "scholarship":
        return category == "scholarships"

    if intent == "documents":
        return category == "required_admission_documents" and _document_level_matches(
            query, chunk
        )

    if intent == "admission_process":
        return category == "admission_process"

    if intent == "deadline":
        return category in {
            "admission_notices",
            "admission_overview",
            "current_admission_information",
        }

    if acronym is not None and intent is None:
        if category not in {"undergraduate_programs", "program_specific_admission"}:
            return False
        program = str(chunk.program or "")
        return bool(program) and _chunk_program_matches(
            program, acronym
        ) and _program_level_matches(query, program, acronym)

    return True


def _fact_intent(query: str) -> Optional[str]:
    """Return the fact type requiring strict evidence compatibility."""

    if _WAIVER_PATTERN.search(query):
        return "waiver"
    if _SCHOLARSHIP_PATTERN.search(query):
        return "scholarship"
    if _ADMISSION_GPA_PATTERN.search(query):
        return "admission_gpa"
    if _TUITION_PATTERN.search(query):
        return "tuition"
    if _DOCUMENT_PATTERN.search(query):
        return "documents"
    if _DEADLINE_PATTERN.search(query):
        return "deadline"
    if _ADMISSION_PROCESS_PATTERN.search(query):
        return "admission_process"
    return None


def _chunk_content_matches_program(content: str, acronym: str) -> bool:
    lowered = unicodedata.normalize("NFKC", content).casefold()
    phrase = _PROGRAM_QUERY_MARKERS[acronym].casefold()
    return phrase in lowered or _contains_ascii_token(lowered, acronym)


def _program_level_matches(query: str, program: str, acronym: str) -> bool:
    """Keep the intended degree level when an acronym exists at both levels."""

    lowered_query = query.casefold()
    lowered_program = program.casefold().strip()
    if "diploma holder" in lowered_program and "diploma" not in lowered_query:
        return False
    program_is_master = bool(
        re.match(r"(?:m\.?\s*sc\.?|master|mba\b|ll\.?\s*m\.?)", lowered_program)
    )
    asks_for_master = bool(
        re.search(r"\b(?:masters?|m\.?\s*sc\.?|postgraduate)\b", lowered_query)
    )
    asks_for_bachelor = bool(
        re.search(r"\b(?:bachelors?|b\.?\s*sc\.?|undergraduate)\b", lowered_query)
    )
    if asks_for_master:
        return program_is_master
    if asks_for_bachelor:
        return not program_is_master
    if acronym in _DEFAULT_POSTGRADUATE_PROGRAM_MARKERS:
        return program_is_master
    return not program_is_master


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
