"""Admission relevance, site boilerplate, and duplicate detection."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from cleaning.normalizer import normalize_text


BOILERPLATE_LINES = frozenset(
    {
        "DIU News",
        "Forum",
        "Students",
        "Parents",
        "Teachers",
        "Alumni",
        "Administration",
        "Help Desk",
        "Sitemap",
        "Academics",
        "Campus",
        "Research",
        "International",
        "About",
        "Home",
        "/",
        "Apply Now",
        "Request for Information",
        "Subscribe Us",
        "Subscribe",
        "Social Links",
        "Privacy Statement",
        "Report Copyright Infringement",
        "Report on Security Issues",
        "Newsletters",
        "Location Map",
        "Covid-19 updates",
        "Visitor Statistics:",
        "Today's Visitors:",
        "Total Visitors:",
        "Loading...",
        "All Rights Reserved.",
        "© Daffodil International University",
        "Need Assistance?",
        "Estimate My Fees",
    }
)

FOOTER_STARTS = (
    "Campus Life in 60 Seconds",
    "Start Your Journey",
)

ADMISSION_PATTERN = re.compile(
    r"(?i)\b(admission|admissions|admit|applicant|application|apply|enrol(?:l|ment)|"
    r"tuition|scholarship|waiver|eligib(?:le|ility)|deadline|semester|program|"
    r"required documents?|admission test)\b"
)


def remove_site_boilerplate(text: str) -> Tuple[str, int]:
    lines = normalize_text(text).splitlines()
    retained: List[str] = []
    removed = 0
    skipping_quick_links = False
    for line in lines:
        stripped = line.strip()
        if stripped == "Quick Links":
            skipping_quick_links = True
            removed += 1
            continue
        if skipping_quick_links:
            if stripped == "Important Information for International Students":
                skipping_quick_links = False
            elif stripped == "Need Assistance?":
                skipping_quick_links = False
                removed += 1
                continue
            else:
                removed += 1
                continue
        if any(stripped.startswith(prefix) for prefix in FOOTER_STARTS):
            removed += 1
            continue
        if stripped in BOILERPLATE_LINES or stripped in {"•", "Copyright ©"}:
            removed += 1
            continue
        if re.fullmatch(r"20\d{2}", stripped) and retained[-1:] == ["Copyright ©"]:
            removed += 1
            continue
        retained.append(stripped)
    return normalize_text("\n".join(retained)), removed


def filter_admission_only(text: str, *, title: str, category: str) -> Tuple[str, List[str]]:
    """Keep a relevant article whole, but select noticeboard entries individually."""

    normalized = normalize_text(text)
    if category not in {"admission_notices", "current_admission_information"}:
        return normalized, []

    flags = ["admission_only_filter_applied"]
    lines = [line for line in normalized.splitlines() if line]
    relevant_indices = [index for index, line in enumerate(lines) if ADMISSION_PATTERN.search(line)]

    if category == "current_admission_information" and len(relevant_indices) >= 2:
        for boundary in (
            "Explore the Inspiring Stories and Events of DIU Campus",
            "More News",
        ):
            if boundary in lines:
                lines = lines[: lines.index(boundary)]
                break
        return normalize_text("\n".join(lines)), flags

    if not relevant_indices:
        return normalize_text(title), flags + ["admission_filter_no_matches", "empty_section"]

    selected = {0}
    for index in relevant_indices:
        selected.update(range(max(0, index - 4), min(len(lines), index + 5)))
    retained = [line for index, line in enumerate(lines) if index in selected]
    return normalize_text("\n".join(retained)), flags


def _duplicate_tokens(value: str) -> List[str]:
    return re.findall(r"[\w$%]+", normalize_text(value).casefold())


def _shingles(tokens: Sequence[str], *, width: int = 5) -> set[Tuple[str, ...]]:
    if len(tokens) < width:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[index : index + width]) for index in range(len(tokens) - width + 1)}


def annotate_duplicates(
    records: Sequence[Dict[str, Any]], *, near_threshold: float = 0.92
) -> Dict[str, List[Dict[str, Any]]]:
    """Annotate exact and near matches without deleting either source record."""

    exact_pairs: List[Dict[str, Any]] = []
    near_pairs: List[Dict[str, Any]] = []
    by_hash: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_hash[str(record["cleaned_content_hash"])].append(record)

    exact_keys = set()
    for members in by_hash.values():
        if len(members) < 2:
            continue
        for left_index, left in enumerate(members):
            _add_flag(left, "duplicate_content")
            for right in members[left_index + 1 :]:
                key = tuple(sorted((left["document_id"], right["document_id"])))
                exact_keys.add(key)
                pair = {"document_ids": list(key), "similarity": 1.0}
                exact_pairs.append(pair)
                _relate(left, right, "exact_duplicate", 1.0)

    prepared = [
        (
            _duplicate_tokens(str(record["cleaned_content"])),
            None,
        )
        for record in records
    ]
    prepared = [(tokens, _shingles(tokens)) for tokens, _ in prepared]
    for left_index, left in enumerate(records):
        left_tokens, left_shingles = prepared[left_index]
        if len(left_tokens) < 50:
            continue
        for right_index, right in enumerate(records[left_index + 1 :], start=left_index + 1):
            key = tuple(sorted((left["document_id"], right["document_id"])))
            if key in exact_keys:
                continue
            right_tokens, right_shingles = prepared[right_index]
            if len(right_tokens) < 50:
                continue
            length_ratio = min(len(left_tokens), len(right_tokens)) / max(
                len(left_tokens), len(right_tokens)
            )
            if length_ratio < near_threshold:
                continue
            denominator = min(len(left_shingles), len(right_shingles))
            score = (
                len(left_shingles & right_shingles) / denominator
                if denominator
                else 0.0
            )
            if score < near_threshold:
                continue
            rounded = round(score, 6)
            _add_flag(left, "near_duplicate")
            _add_flag(right, "near_duplicate")
            _relate(left, right, "near_duplicate", rounded)
            near_pairs.append({"document_ids": list(key), "similarity": rounded})

    exact_pairs.sort(key=lambda item: item["document_ids"])
    near_pairs.sort(key=lambda item: item["document_ids"])
    return {"exact_pairs": exact_pairs, "near_pairs": near_pairs}


def _add_flag(record: Dict[str, Any], flag: str) -> None:
    flags = record.setdefault("quality_flags", [])
    if flag not in flags:
        flags.append(flag)
        flags.sort()


def _relate(
    left: Dict[str, Any], right: Dict[str, Any], relationship: str, similarity: float
) -> None:
    left.setdefault("related_documents", []).append(
        {
            "document_id": right["document_id"],
            "source_id": right["source_id"],
            "relationship": relationship,
            "similarity": similarity,
        }
    )
    right.setdefault("related_documents", []).append(
        {
            "document_id": left["document_id"],
            "source_id": left["source_id"],
            "relationship": relationship,
            "similarity": similarity,
        }
    )
