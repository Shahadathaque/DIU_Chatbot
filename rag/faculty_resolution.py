"""Conservative faculty-name resolution for catalog retrieval.

The resolver contains naming aliases only; it does not contain admission facts.
It deliberately requires either an exact bare faculty name, a faculty/department
qualifier, or catalog-discovery wording.  That prevents a program such as
``Civil Engineering`` from being mistaken for the whole Engineering faculty.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_EXPLICIT_FACULTY_RE = re.compile(r"\b(?:facult(?:y|ies)|departments?)\b", re.I)
_CATALOG_CONTEXT_RE = re.compile(
    r"\b(?:programs?|courses?|degrees?|catalog|offer|offers|offered|available|"
    r"show|list|which|what)\b",
    re.I,
)
_FOCUS_STOPWORDS = frozenset(
    {
        "about",
        "all",
        "are",
        "available",
        "catalog",
        "course",
        "courses",
        "daffodil",
        "degree",
        "degrees",
        "department",
        "departments",
        "diu",
        "does",
        "faculty",
        "faculties",
        "from",
        "has",
        "have",
        "in",
        "is",
        "list",
        "me",
        "name",
        "of",
        "offer",
        "offered",
        "offers",
        "program",
        "programs",
        "show",
        "tell",
        "the",
        "under",
        "university",
        "what",
        "which",
    }
)


@dataclass(frozen=True)
class FacultyName:
    canonical: str
    aliases: tuple[str, ...]


# These are catalog vocabulary aliases, not changing admission policies.  The
# runtime retriever still falls back to source metadata for future faculty names.
FACULTY_NAMES = (
    FacultyName(
        "Agriculture Sciences",
        ("agriculture sciences", "agricultural sciences"),
    ),
    FacultyName(
        "Business & Entrepreneurship",
        ("business and entrepreneurship",),
    ),
    FacultyName("Engineering", ("engineering",)),
    FacultyName(
        "Graduate Studies",
        ("graduate studies", "postgraduate studies"),
    ),
    FacultyName(
        "Health and Life Sciences",
        ("health and life sciences",),
    ),
    FacultyName(
        "Humanities & Social Sciences",
        ("humanities and social sciences",),
    ),
    FacultyName(
        "Science and Information Technology",
        ("science and information technology", "fsit"),
    ),
)


def normalize_faculty_text(value: str) -> str:
    """Normalize harmless punctuation and ``and``/``&`` variants."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return _SPACE_RE.sub(" ", normalized).strip()


def matched_faculty_phrase(query: str) -> Optional[str]:
    """Return one explicitly requested catalog faculty, otherwise ``None``.

    A match is accepted when generic catalog wording can be removed to leave
    exactly one faculty alias.  Queries explicitly containing ``faculty`` or
    ``department`` may contain additional intent wording, so an unambiguous
    full alias is also accepted there.
    """

    normalized = normalize_faculty_text(query)
    if not normalized:
        return None
    query_tokens = tuple(_TOKEN_RE.findall(normalized))
    focus = " ".join(token for token in query_tokens if token not in _FOCUS_STOPWORDS)

    exact_matches = {
        faculty.canonical
        for faculty in FACULTY_NAMES
        for alias in faculty.aliases
        if focus == normalize_faculty_text(alias)
    }
    if len(exact_matches) == 1:
        return next(iter(exact_matches))

    if not (
        _EXPLICIT_FACULTY_RE.search(normalized)
        and _CATALOG_CONTEXT_RE.search(normalized)
    ):
        return None
    contained_matches = {
        faculty.canonical
        for faculty in FACULTY_NAMES
        for alias in faculty.aliases
        if _contains_phrase(normalized, normalize_faculty_text(alias))
    }
    return next(iter(contained_matches)) if len(contained_matches) == 1 else None


def faculty_names_match(left: str, right: str) -> bool:
    """Compare a source faculty label with a resolved canonical name."""

    left_normalized = _without_faculty_wrapper(left)
    right_normalized = _without_faculty_wrapper(right)
    if left_normalized == right_normalized:
        return True
    canonical_left = _canonical_from_alias(left_normalized)
    canonical_right = _canonical_from_alias(right_normalized)
    return canonical_left is not None and canonical_left == canonical_right


def _canonical_from_alias(value: str) -> Optional[str]:
    matches = {
        faculty.canonical
        for faculty in FACULTY_NAMES
        if value == normalize_faculty_text(faculty.canonical)
        or any(value == normalize_faculty_text(alias) for alias in faculty.aliases)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _without_faculty_wrapper(value: str) -> str:
    normalized = normalize_faculty_text(value)
    tokens = [
        token
        for token in _TOKEN_RE.findall(normalized)
        if token not in {"faculty", "faculties", "of", "the"}
    ]
    return " ".join(tokens)


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))
