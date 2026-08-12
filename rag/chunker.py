"""Validated, structure-aware chunking for the cleaned DIU dataset.

The cleaned manifest is the authoritative document list.  Loading verifies every
manifest record path and both its serialized-file and cleaned-content SHA-256
hashes before any text is admitted to the knowledge base.  Chunking keeps PDF
page provenance, emits tables separately with their headers repeated, and never
uses both a PDF's aggregate ``cleaned_content`` and its page texts.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from rag.config import RagSettings, get_rag_settings
from rag.models import KnowledgeChunk, REQUIRED_RECORD_FIELDS


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?।])\s+(?=[\"'‘“(]*\S)")
_NUMBERED_HEADING = re.compile(
    r"^(?:section\s+)?(?:\d+(?:\.\d+)*[.)]?|[A-Za-z][.)])\s+\S+",
    re.IGNORECASE,
)
_LIST_ITEM = re.compile(
    r"^(?:[•▪◦‣#*-]|\(?\d{1,3}[.)]|\(?[A-Za-z][.)])\s*\S+"
)
_FIELD_LABEL = re.compile(r"^[^:]{1,64}:$")
_HEADING_NOISE = frozenset(
    {
        "active",
        "upcoming",
        "online",
        "n/a",
        "see more",
        "get update",
        "apply now",
    }
)


@dataclass(frozen=True)
class _TextUnit:
    """One indivisible or preferably-indivisible source-text unit."""

    text: str
    heading: Optional[str] = None
    atomic: bool = False


@dataclass(frozen=True)
class _ChunkPayload:
    """Chunk text plus its stable structural provenance before model creation."""

    content: str
    content_type: str
    source_locator: str
    page_number: Optional[int]
    program: Optional[str] = None


def load_cleaned_records(cleaned_root: Path | str) -> List[Dict[str, Any]]:
    """Load records enumerated by ``manifest.json`` after integrity validation.

    The function deliberately does not glob ``records/``: unlisted or stale files
    are not part of the cleaned snapshot.  Paths must resolve beneath
    ``cleaned_root``.  For each entry, the serialized file hash, source/document
    identity, raw hash, and cleaned-content hash must agree with the manifest and
    record body.

    Args:
        cleaned_root: Directory containing ``manifest.json`` and its record files.

    Returns:
        Records in manifest order.

    Raises:
        ValueError: If the manifest or any record is malformed or inconsistent.
        OSError: If a required file cannot be read.
    """

    root = Path(cleaned_root).resolve()
    manifest_path = root / "manifest.json"
    manifest = _read_json_object(manifest_path, label="cleaned manifest")
    entries = manifest.get("records")
    if not isinstance(entries, list):
        raise ValueError("cleaned manifest records must be a list")

    records: List[Dict[str, Any]] = []
    seen_sources: set[str] = set()
    seen_documents: set[str] = set()
    seen_paths: set[str] = set()
    for ordinal, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"manifest record {ordinal} must be an object")
        label = f"manifest record {ordinal}"
        relative_path = _required_string(entry, "record_path", label=label)
        record_path = _safe_relative_file(root, relative_path, label=label)
        normalized_path = record_path.relative_to(root).as_posix()
        if normalized_path in seen_paths:
            raise ValueError(f"duplicate manifest record_path: {normalized_path}")
        seen_paths.add(normalized_path)

        expected_file_hash = _required_sha256(entry, "record_file_hash", label=label)
        if _sha256_file(record_path) != expected_file_hash:
            raise ValueError(f"{relative_path}: record_file_hash mismatch")
        record = _read_json_object(record_path, label=relative_path)
        _validate_record(record, entry=entry, label=relative_path)

        source_id = str(record["source_id"])
        document_id = str(record["document_id"])
        if source_id in seen_sources:
            raise ValueError(f"duplicate source_id in cleaned manifest: {source_id}")
        if document_id in seen_documents:
            raise ValueError(f"duplicate document_id in cleaned manifest: {document_id}")
        seen_sources.add(source_id)
        seen_documents.add(document_id)
        records.append(record)
    return records


def chunk_record(
    record: Mapping[str, Any],
    settings: Optional[RagSettings] = None,
) -> List[KnowledgeChunk]:
    """Convert one validated-style cleaned record into retrievable chunks.

    HTML uses normalized headings, paragraphs, list runs, lines, and sentence
    boundaries.  PDF text is chunked page by page, avoiding duplicate indexing of
    its document-level aggregate.  Every retained structured table becomes one or
    more separate chunks; rows are atomic and the header is repeated in each part.
    Partial, historical, uncertain, and manual-review records are retained here so
    retrieval policy—not destructive preprocessing—controls their eligibility.

    Args:
        record: Cleaned record mapping using the Phase 5 schema.
        settings: Optional RAG settings; environment-backed defaults are used when
            omitted.

    Returns:
        Ordered chunks with deterministic, content-sensitive IDs and complete
        provenance metadata.
    """

    active_settings = settings or get_rag_settings()
    _validate_chunkable_record(record)
    payloads: List[_ChunkPayload] = []

    source_content_type = str(record["content_type"])
    if source_content_type == "pdf":
        pages = record.get("pages")
        if not isinstance(pages, list):
            raise ValueError(f"{record['source_id']}: pages must be a list")
        for page in sorted(pages, key=_page_sort_key):
            page_number, page_text = _validated_page(page, source_id=str(record["source_id"]))
            if not page_text:
                continue
            locator = f"page-{page_number}"
            page_chunks = _chunk_structured_text(page_text, settings=active_settings)
            if (
                len(page_chunks) == 1
                and len(page_chunks[0]) < active_settings.rag_min_chunk_size
                and _looks_like_orphan_heading(page_chunks[0])
            ):
                # A PDF cover/running-title page without substantive body is
                # provenance noise, unlike a partial HTML record intentionally
                # retained to represent a known source gap.
                page_chunks = []
            for part_index, text in enumerate(page_chunks, start=1):
                payloads.append(
                    _ChunkPayload(
                        content=text,
                        content_type="text",
                        source_locator=f"{locator}-text-{part_index}",
                        page_number=page_number,
                        program=record.get("program"),
                    )
                )
    else:
        content = _required_string(record, "cleaned_content", label=str(record["source_id"]))
        for part_index, text in enumerate(
            _chunk_structured_text(content, settings=active_settings), start=1
        ):
            payloads.append(
                _ChunkPayload(
                    content=text,
                    content_type="text",
                    source_locator=f"document-text-{part_index}",
                    page_number=None,
                    program=record.get("program"),
                )
            )

    payloads.extend(_table_payloads(record, settings=active_settings))
    return [
        _knowledge_chunk(record, payload=payload, chunk_index=index)
        for index, payload in enumerate(payloads)
    ]


def chunk_records(
    records: Iterable[Mapping[str, Any]],
    settings: Optional[RagSettings] = None,
) -> List[KnowledgeChunk]:
    """Chunk records in input order and reject any deterministic-ID collision."""

    active_settings = settings or get_rag_settings()
    chunks: List[KnowledgeChunk] = []
    seen_ids: set[str] = set()
    for record in records:
        for chunk in chunk_record(record, settings=active_settings):
            if chunk.chunk_id in seen_ids:
                raise ValueError(f"duplicate deterministic chunk_id: {chunk.chunk_id}")
            seen_ids.add(chunk.chunk_id)
            chunks.append(chunk)
    return chunks


def load_and_chunk_cleaned_dataset(
    cleaned_root: Path | str,
    settings: Optional[RagSettings] = None,
) -> List[KnowledgeChunk]:
    """Integrity-check the manifest snapshot and chunk every listed record."""

    return chunk_records(load_cleaned_records(cleaned_root), settings=settings)


def _validate_record(
    record: Mapping[str, Any],
    *,
    entry: Mapping[str, Any],
    label: str,
) -> None:
    missing = sorted(REQUIRED_RECORD_FIELDS - set(record))
    if missing:
        raise ValueError(f"{label}: missing required fields: {', '.join(missing)}")
    _validate_chunkable_record(record)

    for field_name in ("source_id", "document_id", "raw_content_hash"):
        expected = _required_string(entry, field_name, label=f"{label} manifest entry")
        if record.get(field_name) != expected:
            raise ValueError(f"{label}: {field_name} does not match manifest")

    manifest_content_hash = _required_sha256(
        entry, "cleaned_content_hash", label=f"{label} manifest entry"
    )
    if record.get("cleaned_content_hash") != manifest_content_hash:
        raise ValueError(f"{label}: cleaned_content_hash does not match manifest")


def _validate_chunkable_record(record: Mapping[str, Any]) -> None:
    if not isinstance(record, Mapping):
        raise ValueError("cleaned record must be an object")
    missing = sorted(REQUIRED_RECORD_FIELDS - set(record))
    if missing:
        source_id = record.get("source_id", "record")
        raise ValueError(f"{source_id}: missing required fields: {', '.join(missing)}")

    source_id = _required_string(record, "source_id", label="cleaned record")
    for field_name in (
        "document_id",
        "source_url",
        "title",
        "category",
        "cleaned_content",
        "content_type",
        "currency_status",
        "retrieved_at",
        "extraction_status",
    ):
        _required_string(record, field_name, label=source_id)
    for field_name in ("date_sensitive", "manual_review"):
        if not isinstance(record.get(field_name), bool):
            raise ValueError(f"{source_id}: {field_name} must be boolean")
    for field_name in ("quality_flags", "tables", "pages"):
        if not isinstance(record.get(field_name), list):
            raise ValueError(f"{source_id}: {field_name} must be a list")
    if not all(isinstance(flag, str) for flag in record["quality_flags"]):
        raise ValueError(f"{source_id}: quality_flags must contain only strings")

    cleaned_hash = _required_sha256(record, "cleaned_content_hash", label=source_id)
    if _sha256_text(str(record["cleaned_content"])) != cleaned_hash:
        raise ValueError(f"{source_id}: cleaned_content_hash mismatch")
    _required_sha256(record, "raw_content_hash", label=source_id)

    if record.get("program") is not None and not isinstance(record.get("program"), str):
        raise ValueError(f"{source_id}: program must be a string or null")
    if record.get("faculty") is not None and not isinstance(record.get("faculty"), str):
        raise ValueError(f"{source_id}: faculty must be a string or null")


def _table_payloads(
    record: Mapping[str, Any],
    *,
    settings: RagSettings,
) -> List[_ChunkPayload]:
    payloads: List[_ChunkPayload] = []
    tables = record.get("tables", [])
    if not isinstance(tables, list):
        raise ValueError(f"{record['source_id']}: tables must be a list")
    page_texts = _page_text_map(record)

    for table_ordinal, table in enumerate(tables, start=1):
        if not isinstance(table, Mapping):
            raise ValueError(f"{record['source_id']}: table {table_ordinal} must be an object")
        headers = table.get("headers")
        rows = table.get("rows")
        if (
            not isinstance(headers, list)
            or not headers
            or not all(isinstance(cell, str) and cell.strip() for cell in headers)
        ):
            raise ValueError(f"{record['source_id']}: table {table_ordinal} has invalid headers")
        if not isinstance(rows, list):
            raise ValueError(f"{record['source_id']}: table {table_ordinal} rows must be a list")
        width = len(headers)
        normalized_rows: List[List[str]] = []
        for row_ordinal, row in enumerate(rows, start=1):
            if (
                not isinstance(row, list)
                or len(row) != width
                or not all(isinstance(cell, str) for cell in row)
            ):
                raise ValueError(
                    f"{record['source_id']}: table {table_ordinal} row "
                    f"{row_ordinal} is not rectangular"
                )
            normalized_rows.append([_normalize_text(cell) for cell in row])
        if not normalized_rows:
            continue

        raw_locator = table.get("source_locator")
        base_locator = (
            raw_locator.strip()
            if isinstance(raw_locator, str) and raw_locator.strip()
            else f"table-{table_ordinal}"
        )
        page_number = table.get("page_number")
        if page_number is not None and (not isinstance(page_number, int) or page_number < 1):
            raise ValueError(f"{record['source_id']}: {base_locator} has invalid page_number")

        normalized_headers = [_normalize_text(cell) for cell in headers]
        context_occurrence, context_total = _table_context_position(
            tables,
            current_index=table_ordinal - 1,
            page_number=page_number,
            headers=normalized_headers,
        )
        context = _table_context(
            page_texts.get(page_number, "") if page_number is not None else "",
            headers=normalized_headers,
            rows=normalized_rows,
            previous_page_text=(
                page_texts.get(page_number - 1, "")
                if page_number is not None and page_number > 1
                else ""
            ),
            occurrence=context_occurrence,
            repeated_total=context_total,
        )
        program_column = _program_column(normalized_headers)
        groups = _group_table_rows(
            headers=normalized_headers,
            rows=normalized_rows,
            context=context,
            settings=settings,
            force_single_rows=program_column is not None and record.get("program") is None,
        )
        for part_number, group in enumerate(groups, start=1):
            chunk_program = record.get("program")
            if chunk_program is None and program_column is not None:
                chunk_program = group[0][program_column] or None
            content = _format_table(
                title=str(record["title"]),
                context=context,
                headers=normalized_headers,
                rows=group,
            )
            payloads.append(
                _ChunkPayload(
                    content=content,
                    content_type="table",
                    source_locator=f"{base_locator}-part-{part_number}",
                    page_number=page_number,
                    program=chunk_program,
                )
            )
    return payloads


def _group_table_rows(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    context: str,
    settings: RagSettings,
    force_single_rows: bool = False,
) -> List[List[List[str]]]:
    """Group only between rows; a source row is never split or truncated."""

    if force_single_rows:
        return [[list(row)] for row in rows]

    groups: List[List[List[str]]] = []
    current: List[List[str]] = []
    for source_row in rows:
        row = list(source_row)
        candidate = current + [row]
        candidate_text = _format_table(
            title="",
            context=context,
            headers=headers,
            rows=candidate,
        )
        if current and len(candidate_text) > settings.rag_chunk_size:
            groups.append(current)
            current = [row]
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


def _format_table(
    *,
    title: str,
    context: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> str:
    prefix: List[str] = []
    if title:
        prefix.append(title)
    if context and context.casefold() != title.casefold():
        prefix.append(f"Section: {context}")
    prefix.append(" | ".join(headers))
    prefix.extend(" | ".join(row) for row in rows)
    return _normalize_text("\n".join(prefix))


def _program_column(headers: Sequence[str]) -> Optional[int]:
    """Return an explicit source program-name column, without fuzzy inference."""

    accepted = {"program", "full program name"}
    for index, header in enumerate(headers):
        if header.casefold().strip() in accepted:
            return index
    return None


def _table_context(
    page_text: str,
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    previous_page_text: str = "",
    occurrence: int = 1,
    repeated_total: int = 1,
) -> str:
    """Find the nearest source-derived section governing a PDF table.

    A distinctive row cell anchors the table occurrence when similar headers
    repeat on one page.  Context is the closest strong source heading before that
    anchor.  If a table starts a page before any such heading, the last strong
    heading and its immediate scope/effective sentence may carry from the prior
    page.  No label is synthesized from table values.
    """

    if not page_text:
        return ""
    lines = [line for line in (_normalize_text(item) for item in page_text.splitlines()) if line]
    if not lines:
        return ""
    row_anchor = _unique_table_row_anchor(lines, rows)
    if repeated_total > 1:
        groups = _matching_header_groups(lines, headers)
        selected = min(max(occurrence, 1), len(groups)) - 1 if groups else -1
        anchor = groups[selected][-1] if selected >= 0 else row_anchor
    elif row_anchor is not None and _looks_like_table_section_heading(
        lines[row_anchor]
    ):
        # A distinctive row label can itself be the governing source section
        # (for example, a quota name followed immediately by its table).  Keep
        # that exact heading instead of walking back to an unrelated earlier
        # table whose generic column labels happen to overlap.
        anchor = row_anchor
    else:
        header_anchor = _nearest_table_header(lines, headers, before=row_anchor)
        anchor = header_anchor if header_anchor is not None else row_anchor
    if anchor is None:
        anchor = len(lines)

    heading_index = (
        anchor
        if anchor < len(lines) and _looks_like_table_section_heading(lines[anchor])
        else next(
            (
                index
                for index in range(anchor - 1, -1, -1)
                if _looks_like_table_section_heading(lines[index])
            ),
            None,
        )
    )
    if heading_index is not None:
        heading = lines[heading_index]
        scope = _following_scope_line(lines, heading_index, before=anchor)
        return _join_context(heading, scope)

    # A page-opening table may continue a section whose heading is on the prior
    # page.  Limit carry to early tables so an unrelated old heading cannot leak.
    if anchor <= 8 and previous_page_text:
        previous_lines = [
            line
            for line in (
                _normalize_text(item) for item in previous_page_text.splitlines()
            )
            if line
        ]
        prior_heading_index = next(
            (
                index
                for index in range(len(previous_lines) - 1, -1, -1)
                if _looks_like_table_section_heading(previous_lines[index])
            ),
            None,
        )
        if prior_heading_index is not None:
            heading = previous_lines[prior_heading_index]
            scope = _following_scope_line(
                previous_lines,
                prior_heading_index,
                before=len(previous_lines),
            )
            return _join_context(heading, scope)
    return ""


def _table_context_position(
    tables: Sequence[object],
    *,
    current_index: int,
    page_number: Optional[int],
    headers: Sequence[str],
) -> Tuple[int, int]:
    """Return this table's occurrence among similar same-page table headers."""

    signature = _table_header_signature(headers)
    positions: List[int] = []
    for index, table in enumerate(tables):
        if not isinstance(table, Mapping) or table.get("page_number") != page_number:
            continue
        candidate = table.get("headers")
        if not isinstance(candidate, list) or not all(
            isinstance(cell, str) for cell in candidate
        ):
            continue
        if _table_header_signature(candidate) == signature:
            positions.append(index)
    try:
        occurrence = positions.index(current_index) + 1
    except ValueError:
        occurrence = 1
    return occurrence, max(1, len(positions))


def _table_header_signature(headers: Sequence[str]) -> Tuple[str, ...]:
    if not headers:
        return ()
    tokens = re.findall(r"\w+", headers[0].casefold())
    ignored = {"of", "and", "including", "fourth", "subject", "the"}
    normalized = ["equiv" if token.startswith("equiv") else token for token in tokens]
    return tuple(token for token in normalized if token not in ignored)[:4]


def _matching_header_groups(
    lines: Sequence[str], headers: Sequence[str]
) -> List[List[int]]:
    """Group loose header matches so repeated visual tables remain distinguishable."""

    first_header = headers[0].casefold() if headers else ""
    header_tokens = set(re.findall(r"\w+", first_header))
    matches: List[int] = []
    for index in range(len(lines)):
        folded = " ".join(lines[index : index + 3]).casefold()
        prefix = first_header[: min(28, len(first_header))]
        line_tokens = set(re.findall(r"\w+", folded))
        if (prefix and prefix in folded) or (
            len(header_tokens) >= 3
            and len(header_tokens & line_tokens) >= min(4, len(header_tokens))
        ):
            matches.append(index)
    groups: List[List[int]] = []
    for index in matches:
        if not groups or index - groups[-1][-1] > 4:
            groups.append([index])
        else:
            groups[-1].append(index)
    return groups


def _unique_table_row_anchor(
    lines: Sequence[str], rows: Sequence[Sequence[str]]
) -> Optional[int]:
    """Locate a table using a distinctive row-cell phrase present once on-page."""

    candidates: List[Tuple[int, int]] = []
    for row in rows:
        for cell in row:
            normalized = _normalize_text(cell).casefold()
            if (
                len(normalized) < 6
                or not re.search(r"\w", normalized)
                or _looks_like_table_section_heading(normalized)
            ):
                continue
            probes = [normalized]
            words = normalized.split()
            if len(words) > 6:
                probes.append(" ".join(words[:6]))
            for probe in probes:
                matches = [
                    index
                    for index, line in enumerate(lines)
                    if probe in line.casefold()
                ]
                if len(matches) == 1:
                    candidates.append((len(probe), matches[0]))
                    break
    return max(candidates)[1] if candidates else None


def _nearest_table_header(
    lines: Sequence[str],
    headers: Sequence[str],
    *,
    before: Optional[int],
) -> Optional[int]:
    """Return the closest strong multi-line header match before the row anchor."""

    header_tokens = _context_tokens(" ".join(headers))
    if not header_tokens:
        return None
    minimum_overlap = max(3, min(6, round(len(header_tokens) * 0.35)))
    end = before if before is not None else len(lines)
    matches: List[Tuple[int, int]] = []
    for index in range(end):
        window_tokens = _context_tokens(" ".join(lines[index : index + 5]))
        overlap = len(header_tokens & window_tokens)
        if overlap >= minimum_overlap:
            matches.append((index, overlap))
    if not matches:
        return None
    best_overlap = max(score for _, score in matches)
    strong = [index for index, score in matches if score >= best_overlap - 1]
    return strong[-1]


def _context_tokens(text: str) -> set[str]:
    ignored = {
        "and", "be", "each", "for", "fourth", "including", "in", "of",
        "subject", "the", "to",
    }
    values = re.findall(r"\w+", text.casefold())
    return {
        "equiv" if token.startswith("equiv") else token
        for token in values
        if token not in ignored
    }


def _looks_like_table_section_heading(line: str) -> bool:
    """Recognize explicit source section/scope headings, not generic body lines."""

    normalized = _normalize_text(line)
    if not normalized or len(normalized) > 180 or "%" in normalized:
        return False
    return bool(
        re.search(r"(?i)^[a-z]\)\s+.+(?:quota|waiver|program).*(?::)$", normalized)
        or re.search(
            r"(?i)^(?:for the faculty|for english medium background|"
            r"waiver schemes?|undergraduate programs$|master[’']?s degree for|"
            r"the tuition fee waiver in female quota)",
            normalized,
        )
    )


def _following_scope_line(
    lines: Sequence[str], heading_index: int, *, before: int
) -> str:
    """Keep one adjacent source sentence when it materially scopes the heading."""

    for line in lines[heading_index + 1 : min(before, heading_index + 4)]:
        normalized = _normalize_text(line)
        if not normalized or _looks_like_table_section_heading(normalized):
            continue
        if re.search(
            r"(?i)(?:effective from|from (?:spring|fall|summer)\s+\d{4}|"
            r"will be given tuition fee waiver|will get tuition fee waiver|"
            r"tuition fee waiver.*stated below)",
            normalized,
        ):
            return normalized
    return ""


def _join_context(heading: str, scope: str) -> str:
    context = " — ".join(value for value in (heading, scope) if value)
    return context if len(context) <= 300 else context[:297].rstrip() + "..."


def _page_text_map(record: Mapping[str, Any]) -> Dict[int, str]:
    values: Dict[int, str] = {}
    pages = record.get("pages", [])
    if not isinstance(pages, list):
        return values
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        number = page.get("page_number")
        text = page.get("text")
        if isinstance(number, int) and isinstance(text, str):
            values[number] = _normalize_text(text)
    return values


def _chunk_structured_text(text: str, *, settings: RagSettings) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    units = _text_units(normalized, max_size=settings.rag_chunk_size)
    chunks = _pack_units(
        units,
        max_size=settings.rag_chunk_size,
        overlap=settings.rag_chunk_overlap,
    )
    return _merge_small_chunks(
        chunks,
        minimum=settings.rag_min_chunk_size,
        maximum=settings.rag_chunk_size,
    )


def _text_units(text: str, *, max_size: int) -> List[_TextUnit]:
    paragraphs = [item for item in re.split(r"\n\s*\n", text) if item.strip()]
    units: List[_TextUnit] = []
    active_heading: Optional[str] = None
    for paragraph in paragraphs:
        lines = [
            line
            for line in (_normalize_text(item) for item in paragraph.splitlines())
            if line
        ]
        index = 0
        while index < len(lines):
            line = lines[index]
            if _looks_like_heading(line):
                active_heading = line
                units.append(_TextUnit(text=line, heading=line, atomic=True))
                index += 1
                continue
            if _looks_like_list_item(line):
                run = [line]
                index += 1
                while index < len(lines) and _looks_like_list_item(lines[index]):
                    run.append(lines[index])
                    index += 1
                units.extend(_split_list_run(run, heading=active_heading, max_size=max_size))
                continue

            run = [line]
            index += 1
            while (
                index < len(lines)
                and not _looks_like_heading(lines[index])
                and not _looks_like_list_item(lines[index])
            ):
                run.append(lines[index])
                index += 1
            prose = " ".join(run)
            units.extend(_split_prose(prose, heading=active_heading, max_size=max_size))
    return units


def _split_list_run(
    lines: Sequence[str], *, heading: Optional[str], max_size: int
) -> List[_TextUnit]:
    result: List[_TextUnit] = []
    current: List[str] = []
    for line in lines:
        if current and len("\n".join(current + [line])) > max_size:
            result.append(_TextUnit("\n".join(current), heading=heading, atomic=True))
            current = [line]
        else:
            current.append(line)
    if current:
        result.append(_TextUnit("\n".join(current), heading=heading, atomic=True))
    return result


def _split_prose(text: str, *, heading: Optional[str], max_size: int) -> List[_TextUnit]:
    if len(text) <= max_size:
        return [_TextUnit(text=text, heading=heading)]
    sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(text) if item.strip()]
    if len(sentences) == 1:
        return [
            _TextUnit(text=part, heading=heading)
            for part in _split_long_text(text, max_size=max_size)
        ]
    result: List[_TextUnit] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_size:
            if current:
                result.append(_TextUnit(text=current, heading=heading))
                current = ""
            result.extend(
                _TextUnit(text=part, heading=heading)
                for part in _split_long_text(sentence, max_size=max_size)
            )
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_size:
            result.append(_TextUnit(text=current, heading=heading))
            current = sentence
        else:
            current = candidate
    if current:
        result.append(_TextUnit(text=current, heading=heading))
    return result


def _split_long_text(text: str, *, max_size: int) -> List[str]:
    """Last-resort whitespace splitter for a source line/sentence over the cap."""

    words = text.split()
    if not words:
        return []
    parts: List[str] = []
    current: List[str] = []
    for word in words:
        if len(word) > max_size:
            if current:
                parts.append(" ".join(current))
                current = []
            parts.extend(word[index : index + max_size] for index in range(0, len(word), max_size))
            continue
        candidate = " ".join(current + [word])
        if current and len(candidate) > max_size:
            parts.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts


def _pack_units(units: Sequence[_TextUnit], *, max_size: int, overlap: int) -> List[str]:
    chunks: List[str] = []
    current: List[_TextUnit] = []
    for unit in units:
        candidate = _render_units(current + [unit])
        if current and len(candidate) > max_size:
            rendered = _render_units(current)
            if rendered:
                chunks.append(rendered)
            current = _overlap_units(current, overlap=overlap, next_unit=unit, max_size=max_size)
            if len(_render_units(current + [unit])) > max_size:
                current = []
        current.append(unit)
    rendered = _render_units(current)
    if rendered:
        chunks.append(rendered)
    return chunks


def _overlap_units(
    previous: Sequence[_TextUnit],
    *,
    overlap: int,
    next_unit: _TextUnit,
    max_size: int,
) -> List[_TextUnit]:
    if overlap <= 0:
        return []
    selected: List[_TextUnit] = []
    length = 0
    for unit in reversed(previous):
        if unit.atomic and unit.heading == unit.text:
            continue
        addition = len(unit.text) + (1 if selected else 0)
        if length + addition > overlap:
            break
        selected.insert(0, unit)
        length += addition
        if length >= overlap:
            break
    if next_unit.heading and not any(item.text == next_unit.heading for item in selected):
        heading = _TextUnit(next_unit.heading, heading=next_unit.heading, atomic=True)
        selected.insert(0, heading)
    while selected and len(_render_units(selected + [next_unit])) > max_size:
        removable = next(
            (i for i, item in enumerate(selected) if item.text != next_unit.heading),
            0,
        )
        selected.pop(removable)
    return selected


def _render_units(units: Sequence[_TextUnit]) -> str:
    values: List[str] = []
    for unit in units:
        if values and values[-1] == unit.text:
            continue
        values.append(unit.text)
    return _normalize_text("\n".join(values))


def _merge_small_chunks(chunks: Sequence[str], *, minimum: int, maximum: int) -> List[str]:
    result: List[str] = []
    for index, chunk in enumerate(chunks):
        if len(chunk) < minimum and index + 1 < len(chunks):
            if _chunk_starts_with(chunks[index + 1], chunk) or _looks_like_orphan_heading(chunk):
                # Packing can leave a heading alone when the following unit nearly
                # fills the size budget.  Its source context remains in the adjacent
                # substantive chunk (and is often explicitly repeated there), so a
                # separate heading-only vector would only add retrieval noise.
                continue
        if result and len(chunk) < minimum and len(result[-1]) + 1 + len(chunk) <= maximum:
            result[-1] = _normalize_text(f"{result[-1]}\n{chunk}")
        else:
            result.append(chunk)
    if (
        len(result) > 1
        and len(result[0]) < minimum
        and len(result[0]) + 1 + len(result[1]) <= maximum
    ):
        result[1] = _normalize_text(f"{result[0]}\n{result[1]}")
        result.pop(0)
    return result


def _chunk_starts_with(chunk: str, prefix: str) -> bool:
    normalized_chunk = _normalize_text(chunk)
    normalized_prefix = _normalize_text(prefix)
    return normalized_chunk == normalized_prefix or normalized_chunk.startswith(
        normalized_prefix + "\n"
    )


def _looks_like_orphan_heading(chunk: str) -> bool:
    lines = [line for line in _normalize_text(chunk).splitlines() if line]
    return bool(lines) and len(lines) <= 3 and all(_looks_like_heading(line) for line in lines)


def _knowledge_chunk(
    record: Mapping[str, Any],
    *,
    payload: _ChunkPayload,
    chunk_index: int,
) -> KnowledgeChunk:
    content = _normalize_text(payload.content)
    content_hash = _sha256_text(content)
    identity = "\x1f".join(
        (
            str(record["document_id"]),
            payload.content_type,
            payload.source_locator,
            str(payload.page_number or ""),
            content_hash,
        )
    )
    chunk_id = "diu-chunk-" + _sha256_text(identity)[:24]
    flags = tuple(sorted(set(str(flag) for flag in record.get("quality_flags", []))))
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id=str(record["document_id"]),
        source_id=str(record["source_id"]),
        source_url=str(record["source_url"]),
        title=str(record["title"]),
        category=str(record["category"]),
        program=payload.program,
        faculty=record.get("faculty"),
        content=content,
        content_type=payload.content_type,
        source_content_type=str(record["content_type"]),
        currency_status=str(record["currency_status"]),
        date_sensitive=bool(record["date_sensitive"]),
        manual_review=bool(record["manual_review"]),
        retrieved_at=str(record["retrieved_at"]),
        document_hash=str(record["cleaned_content_hash"]),
        source_hash=str(record["raw_content_hash"]),
        content_hash=content_hash,
        source_locator=payload.source_locator,
        page_number=payload.page_number,
        chunk_index=chunk_index,
        extraction_status=str(record["extraction_status"]),
        quality_flags=flags,
    )


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.casefold() in _HEADING_NOISE:
        return False
    if len(stripped) > 120 or stripped.endswith((".", "?", "!", ",", ";")):
        return False
    if _FIELD_LABEL.fullmatch(stripped):
        return False
    words = stripped.split()
    if _NUMBERED_HEADING.match(stripped) and len(words) <= 18:
        return True
    if stripped.isupper() and 1 <= len(words) <= 15:
        return True
    if len(words) <= 9 and not re.search(
        r"\b(?:is|are|was|were|will|have|has|must)\b", stripped, re.I
    ):
        titleish = sum(word[:1].isupper() for word in words if word[:1].isalpha())
        return bool(words) and titleish >= max(1, len(words) // 2)
    return False


def _looks_like_list_item(line: str) -> bool:
    return bool(_LIST_ITEM.match(line.strip()))


def _validated_page(page: object, *, source_id: str) -> Tuple[int, str]:
    if not isinstance(page, Mapping):
        raise ValueError(f"{source_id}: PDF page must be an object")
    number = page.get("page_number")
    text = page.get("text")
    if not isinstance(number, int) or number < 1:
        raise ValueError(f"{source_id}: PDF page_number must be a positive integer")
    if not isinstance(text, str):
        raise ValueError(f"{source_id}: PDF page text must be a string")
    return number, _normalize_text(text)


def _page_sort_key(page: object) -> int:
    if not isinstance(page, Mapping) or not isinstance(page.get("page_number"), int):
        return 2**31 - 1
    return int(page["page_number"])


def _safe_relative_file(root: Path, relative: str, *, label: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or not relative_path.parts:
        raise ValueError(f"{label}: record_path must be relative")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label}: record_path escapes cleaned dataset root") from error
    if not candidate.is_file():
        raise ValueError(f"{label}: record file is missing: {relative}")
    return candidate


def _read_json_object(path: Path, *, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _required_string(value: Mapping[str, Any], key: str, *, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{label}: {key} must be a non-empty string")
    return item


def _required_sha256(value: Mapping[str, Any], key: str, *, label: str) -> str:
    digest = _required_string(value, key, label=label)
    if not _SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{label}: {key} must be a lowercase SHA-256 digest")
    return digest


def _normalize_text(value: object) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")]
    output: List[str] = []
    for line in lines:
        if not line:
            if output and output[-1] != "":
                output.append("")
            continue
        output.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output).strip())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for payload in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(payload)
    return digest.hexdigest()


__all__ = [
    "chunk_record",
    "chunk_records",
    "load_and_chunk_cleaned_dataset",
    "load_cleaned_records",
]
