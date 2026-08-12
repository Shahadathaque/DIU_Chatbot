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
    r"(?i)(?:\b(?:admissions?|admit|apply|applications?|programs?|courses?|degrees?|"
    r"documents?|certificates?|transcripts?|tuition|fees?|costs?|"
    r"scholarships?|waivers?|financial\s+aid|international\s+students?|"
    r"eligibility|eligible|deadlines?|requirements?|contacts?|campus|semesters?|"
    r"vorti|bhorti)\b|ভর্তি|আবেদন|ডকুমেন্ট|কাগজপত্র|কাগজ|টিউশন|ফি|খরচ|"
    r"বৃত্তি|স্কলারশিপ|ওয়েভার|ওয়েভার|প্রোগ্রাম|কোর্স|যোগাযোগ)"
)
_PROGRAM_QUERY_MARKERS = {
    "cse": "computer science and engineering",
    "swe": "software engineering",
    "cis": "computing and information system",
    "itm": "information technology & management",
    "mct": "multimedia & creative technology",
    "rme": "robotics and mechatronics engineering",
    "bba": "bba",
}


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
    return names_diu or bool(_DOMAIN_TERM_PATTERN.search(lowered))


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
        ranked = [
            self._rerank(normalized, match, intent_query=intent_query)
            for match in candidates
        ]
        ranked.sort(
            key=lambda result: (
                *self._authority_rank(result.chunk),
                -result.relevance_score,
                -self._metadata_bonus(intent_query, result.chunk),
                -result.similarity_score,
                result.chunk.chunk_id,
            )
        )
        return self._suppress_duplicates(
            ranked,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            relevance_threshold=relevance_threshold,
            preferred_categories=set(self._topic_category_bonuses(intent_query)),
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
                + metadata_bonus,
            ),
        )
        return SearchResult(
            chunk=match.chunk,
            similarity_score=match.similarity_score,
            relevance_score=score,
        )

    def _suppress_duplicates(
        self,
        ranked: Iterable[SearchResult],
        *,
        top_k: int,
        similarity_threshold: float,
        relevance_threshold: float,
        preferred_categories: set[str],
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
            source_limit = (
                self.max_results_per_source
                if chunk.category.casefold() in preferred_categories
                else min(2, self.max_results_per_source)
            )
            if source_counts[chunk.source_id] >= source_limit:
                continue
            signature = _meaningful_tokens(chunk.content)
            if any(_jaccard(signature, previous) >= 0.88 for previous in signatures):
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
                continue
            if official_phrase not in program:
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


def _validated_score(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number between -1 and 1")
    parsed = float(value)
    if not math.isfinite(parsed) or not -1.0 <= parsed <= 1.0:
        raise ValueError(f"{name} must be a finite number between -1 and 1")
    return parsed
