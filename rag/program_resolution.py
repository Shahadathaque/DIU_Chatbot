"""Canonical, catalog-oriented program-name resolution for DIU queries.

The resolver deliberately contains names and aliases, never admission facts or
fee values.  It normalizes harmless typography, prefers the longest explicit
program name, and keeps degree level separate from subject matching so the same
subject can safely exist at undergraduate and postgraduate levels.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional


_SPACE_RE = re.compile(r"\s+")
_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")
_INTENT_WORDS_RE = re.compile(
    r"\b(?:diu|daffodil|what|which|tell|show|give|me|about|does|do|have|offer|"
    r"offered|program|programme|course|degree|tuition|fees?|cost|total|"
    r"payable|admission|local|student|information|details?|please)\b"
)
_CASE_SENSITIVE_SHORT_ALIASES = {"ce", "te"}


@dataclass(frozen=True)
class ProgramAlias:
    marker: str
    canonical: str
    aliases: tuple[str, ...]
    default_level: Optional[str] = None


# Specific specializations are separate markers.  Their longer aliases beat
# broad subject markers (for example ITM beats Management) deterministically.
PROGRAM_ALIASES: tuple[ProgramAlias, ...] = (
    ProgramAlias("bba_finance", "BBA in Finance & Banking", ("bba in finance and banking", "finance and banking", "finance", "banking"), "undergraduate"),
    ProgramAlias("bba_accounting", "BBA in Accounting", ("bba in accounting", "accounting"), "undergraduate"),
    ProgramAlias("bba_management", "BBA in Management", ("bba in management", "management"), "undergraduate"),
    ProgramAlias("bba_marketing", "BBA in Marketing", ("bba in marketing", "marketing"), "undergraduate"),
    ProgramAlias("mba_leadership", "MBA in Leadership", ("mba in leadership",), "postgraduate"),
    ProgramAlias("executive_mba", "Master of Business Administration (Executive)", ("executive mba", "master of business administration executive"), "postgraduate"),
    ProgramAlias("ma_english", "M. A in English", ("ma in english", "master of arts in english"), "postgraduate"),
    ProgramAlias(
        "mss_jmc",
        "MSS in Journalism, Media and Communication",
        (
            "mss in journalism media and communication",
            "master of social science in journalism media and communication",
            "master of social sciences in journalism media and communication",
            "mss",
        ),
        "postgraduate",
    ),
    ProgramAlias("mds", "Master of Development Studies", ("master of development studies", "development studies", "mds"), "postgraduate"),
    ProgramAlias("mph", "Master of Public Health", ("master of public health", "mph"), "postgraduate"),
    ProgramAlias("mpharm", "Master of Pharmacy", ("master of pharmacy", "m pharm", "mpharm"), "postgraduate"),
    ProgramAlias("llm", "LL.M.", ("llm", "master of laws", "master of law"), "postgraduate"),
    ProgramAlias("mba", "Master of Business Administration", ("master of business administration", "mba"), "postgraduate"),
    ProgramAlias("pgd_islm", "Post Graduate Diploma in Information Science and Library Management", ("post graduate diploma in information science and library management", "pgd in islm", "pgd islm", "islm"), "postgraduate"),
    ProgramAlias("itm", "Information Technology & Management", ("information technology and management", "itm"), "undergraduate"),
    ProgramAlias("mct", "Multimedia & Creative Technology", ("multimedia and creative technology", "mct"), "undergraduate"),
    ProgramAlias("ice", "Information & Communication Engineering", ("information and communication engineering", "ice"), "undergraduate"),
    ProgramAlias("jmc", "Journalism, Media and Communication", ("journalism media and communication", "jmc"), "undergraduate"),
    ProgramAlias("public_health", "Bachelor of Public Health", ("bachelor of public health", "public health", "bph"), "undergraduate"),
    ProgramAlias("pharmacy", "Bachelor of Pharmacy", ("bachelor of pharmacy", "pharmacy", "b pharm", "bpharm", "ফার্মেসি"), "undergraduate"),
    ProgramAlias("english", "B.A. (Hons) in English", ("ba hons in english", "ba in english", "english department", "english"), "undergraduate"),
    ProgramAlias("tourism", "Tourism & Hospitality Management", ("bachelor of tourism and hospitality management", "tourism and hospitality management", "bthm", "thm", "tourism"), "undergraduate"),
    ProgramAlias("cse", "Computer Science and Engineering", ("computer science and engineering", "computer science", "cse"), "undergraduate"),
    ProgramAlias("swe", "Software Engineering", ("software engineering", "swe"), "undergraduate"),
    ProgramAlias("cis", "Computing and Information System", ("computing and information system", "cis"), "undergraduate"),
    ProgramAlias("rme", "Robotics and Mechatronics Engineering", ("robotics and mechatronics engineering", "rme"), "undergraduate"),
    ProgramAlias("cyber_security", "Cyber Security", ("cyber security",)),
    ProgramAlias("mis", "Management Information Systems", ("management information systems", "mis"), "postgraduate"),
    ProgramAlias("eee", "Electrical and Electronic Engineering", ("electrical and electronic engineering", "eee"), "undergraduate"),
    ProgramAlias("civil", "Civil Engineering", ("civil engineering", "civil", "ce"), "undergraduate"),
    ProgramAlias("ete", "Electronics and Telecommunication Engineering", ("electronics and telecommunication engineering", "ete"), "postgraduate"),
    ProgramAlias("textile", "Textile Engineering", ("textile engineering", "textile", "te", "টেক্সটাইল"), "undergraduate"),
    ProgramAlias("architecture", "Bachelor of Architecture", ("bachelor of architecture", "architecture", "b arch", "barch"), "undergraduate"),
    ProgramAlias("pess", "Physical Education and Sports Science", ("physical education and sports science", "pess"), "undergraduate"),
    ProgramAlias("esdm", "Environmental Science and Disaster Management", ("environmental science and disaster management", "esdm"), "undergraduate"),
    ProgramAlias("nfe", "Nutrition and Food Engineering", ("nutrition and food engineering", "nfe"), "undergraduate"),
    ProgramAlias("genetic_engineering", "Genetic Engineering and Biotechnology", ("genetic engineering and biotechnology", "genetic engineering"), "undergraduate"),
    ProgramAlias("digital_education", "Master of Teaching in Digital Education", ("master of teaching in digital education", "teaching in digital education", "digital education"), "postgraduate"),
    ProgramAlias("agriculture", "Agricultural Science", ("bachelor of agricultural science", "agricultural science", "agriculture", "agricultural", "ags"), "undergraduate"),
    ProgramAlias("fisheries", "Fisheries", ("fisheries",), "undergraduate"),
    ProgramAlias("real_estate", "Bachelor of Real Estate", ("bachelor of real estate", "real estate", "bre"), "undergraduate"),
    ProgramAlias("entrepreneurship", "Bachelor of Entrepreneurship", ("bachelor of entrepreneurship", "entrepreneurship"), "undergraduate"),
    ProgramAlias("llb", "LL.B.", ("llb", "bachelor of laws", "bachelor of law", "law", "আইন"), "undergraduate"),
    ProgramAlias("bba", "Bachelor of Business Administration", ("bachelor of business administration", "bba", "বিবিএ"), "undergraduate"),
)

PROGRAM_BY_MARKER = {item.marker: item for item in PROGRAM_ALIASES}


def normalize_program_text(text: str) -> str:
    """Normalize punctuation and common degree typography for comparison."""

    value = unicodedata.normalize("NFKC", text).casefold()
    value = value.replace("’", "'").replace("‘", "'")
    value = re.sub(r"master(?:'s|s)?", "master", value)
    value = value.replace("&", " and ")
    value = re.sub(r"[^\w\u0980-\u09ff]+", " ", value, flags=re.UNICODE)
    value = _SPACE_RE.sub(" ", value).strip()
    # Periods turn initialisms into separate tokens.  Compact only known degree
    # forms so ordinary words and program subjects remain untouched.
    replacements = (
        (r"\bm\s+pharm\b", "mpharm"),
        (r"\bb\s+pharm\b", "bpharm"),
        (r"\bm\s+sc\b", "msc"),
        (r"\bb\s+sc\b", "bsc"),
        (r"\bm\s+a\b", "ma"),
        (r"\bb\s+a\b", "ba"),
        (r"\bll\s+m\b", "llm"),
        (r"\bll\s+b\b", "llb"),
        (r"\bb\s+arch\b", "barch"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    return _SPACE_RE.sub(" ", value).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?:^|\s)" + re.escape(phrase) + r"(?:$|\s)", text))


def _alias_matches(query: str) -> list[tuple[ProgramAlias, str, tuple[int, int]]]:
    normalized = normalize_program_text(query)
    matches: list[tuple[ProgramAlias, str, tuple[int, int]]] = []
    for program in PROGRAM_ALIASES:
        candidates = (*program.aliases, program.canonical)
        occurrences: list[tuple[str, tuple[int, int]]] = []
        for alias in candidates:
            alias_norm = normalize_program_text(alias)
            if not alias_norm:
                continue
            if alias_norm in _CASE_SENSITIVE_SHORT_ALIASES and not re.search(
                rf"(?<![A-Za-z0-9]){re.escape(alias.upper())}(?![A-Za-z0-9])",
                query,
            ):
                continue
            pattern = re.compile(
                r"(?:^|\s)(" + re.escape(alias_norm) + r")(?:$|\s)"
            )
            for match in pattern.finditer(normalized):
                occurrences.append((alias_norm, match.span(1)))
        if occurrences:
            best, span = max(
                occurrences,
                key=lambda value: (len(value[0].split()), len(value[0])),
            )
            matches.append((program, best, span))
    return matches


def named_program_markers(query: str) -> list[str]:
    """Return the most-specific marker at each independently named span.

    A broad alias contained by a longer name is discarded (``management``
    inside ITM, or ``English`` inside MA in English), while separate program
    mentions are all retained even when their alias lengths differ.
    """

    matches = _alias_matches(query)
    if not matches:
        return []
    selected: list[tuple[ProgramAlias, tuple[int, int]]] = []
    for item, alias, span in sorted(
        matches,
        key=lambda value: (len(value[1].split()), len(value[1])),
        reverse=True,
    ):
        if any(span[0] < chosen[1] and chosen[0] < span[1] for _, chosen in selected):
            continue
        selected.append((item, span))
    selected.sort(key=lambda value: value[1][0])
    return list(dict.fromkeys(item.marker for item, _ in selected))


def matched_program_phrase(query: str) -> Optional[str]:
    markers = named_program_markers(query)
    return PROGRAM_BY_MARKER[markers[0]].canonical if len(markers) == 1 else None


def single_named_program_marker(query: str) -> Optional[str]:
    markers = named_program_markers(query)
    return markers[0] if len(markers) == 1 else None


def program_phrase_matches(program: str, phrase: str) -> bool:
    """Return whether catalog metadata is canonically compatible with a phrase."""

    program_norm = normalize_program_text(program)
    phrase_norm = normalize_program_text(phrase)
    if not program_norm or not phrase_norm:
        return False
    if _contains_phrase(program_norm, phrase_norm):
        return True
    marker = next(
        (
            item.marker
            for item in PROGRAM_ALIASES
            if normalize_program_text(item.canonical) == phrase_norm
        ),
        None,
    )
    return bool(marker and chunk_program_matches(program, marker))


def chunk_program_matches(program: str, marker: str) -> bool:
    """Match program metadata to one resolved marker without fee knowledge."""

    item = PROGRAM_BY_MARKER.get(marker)
    if item is None:
        return False
    program_norm = normalize_program_text(program)
    canonical_norm = normalize_program_text(item.canonical)

    # Generic BBA/MBA must not absorb named specializations or executive rows.
    if marker == "bba":
        core = normalize_program_text(_PARENTHETICAL_RE.sub(" ", program))
        return core in {"bba", "bachelor of business administration"}
    if marker == "mba":
        core = normalize_program_text(_PARENTHETICAL_RE.sub(" ", program))
        return core in {"mba", "master of business administration"}

    if _contains_phrase(program_norm, canonical_norm):
        return True
    return False


def degree_level(text: str) -> Optional[str]:
    normalized = normalize_program_text(text)
    tokens = set(normalized.split())
    if tokens & {"master", "msc", "ma", "mba", "llm", "mds", "mph", "mss", "mpharm", "postgraduate"}:
        return "postgraduate"
    if "post graduate" in normalized or normalized.startswith("pgd "):
        return "postgraduate"
    if tokens & {"bachelor", "bsc", "ba", "bba", "bss", "llb", "barch", "bph", "bpharm", "undergraduate"}:
        return "undergraduate"
    return None


def program_level_matches(query: str, program: str, marker: str) -> bool:
    """Prevent explicit or canonical degree level from crossing UG/PG rows."""

    query_norm = normalize_program_text(query)
    program_norm = normalize_program_text(program)
    if "diploma holder" in program_norm and "diploma" not in query_norm:
        return False
    expected = degree_level(query)
    if expected is None:
        item = PROGRAM_BY_MARKER.get(marker)
        expected = item.default_level if item else None
    actual = degree_level(program)
    return expected is None or actual == expected


def catalog_program_phrase(query: str, programs: Iterable[str]) -> Optional[str]:
    """Resolve an exact full catalog name from retrieved program metadata.

    This is the generic fallback for catalog programs that do not need a hand-
    maintained short alias.  Only full names (with optional parentheticals)
    qualify, so a broad subject cannot silently choose the wrong degree.
    """

    query_norm = normalize_program_text(query)
    candidates: list[tuple[tuple[int, int], str]] = []
    for program in programs:
        full = normalize_program_text(program)
        without_parenthetical = normalize_program_text(_PARENTHETICAL_RE.sub(" ", program))
        variants = {full, without_parenthetical}
        matched = [variant for variant in variants if variant and _contains_phrase(query_norm, variant)]
        if matched:
            best = max(matched, key=lambda value: (len(value.split()), len(value)))
            candidates.append(((len(best.split()), len(best)), program))
    if not candidates:
        return None
    best_score = max(score for score, _ in candidates)
    winners = list(dict.fromkeys(program for score, program in candidates if score == best_score))
    return winners[0] if len(winners) == 1 else None


def best_compatible_catalog_program(
    query: str, phrase: str, programs: Iterable[str]
) -> Optional[str]:
    """Choose the least-expanded catalog row compatible with a named program.

    A subject such as Software Engineering can occur in a base degree and in
    several named majors.  The base query resolves to the base row; an explicit
    full specialization is handled earlier by :func:`catalog_program_phrase`.
    """

    marker = single_named_program_marker(query) or ""
    phrase_tokens = set(normalize_program_text(phrase).split())
    candidates: list[tuple[tuple[int, int], str]] = []
    for program in programs:
        if not program_phrase_matches(program, phrase):
            continue
        if not program_level_matches(query, program, marker):
            continue
        core = normalize_program_text(program)
        program_tokens = set(core.split())
        extra = len(program_tokens - phrase_tokens - {"in", "of"})
        candidates.append(((extra, len(core)), program))
    if not candidates:
        return None
    best_score = min(score for score, _ in candidates)
    winners = list(dict.fromkeys(program for score, program in candidates if score == best_score))
    return winners[0] if len(winners) == 1 else None


def program_search_phrase(query: str) -> Optional[str]:
    """Strip tuition boilerplate to preserve an unknown catalog name search lane."""

    normalized = normalize_program_text(query)
    stripped = _INTENT_WORDS_RE.sub(" ", normalized)
    stripped = _SPACE_RE.sub(" ", stripped).strip()
    return stripped if len(stripped) >= 3 else None
