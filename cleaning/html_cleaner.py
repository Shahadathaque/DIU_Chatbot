"""Conservative HTML-to-text and reliable-table cleaning."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from bs4 import BeautifulSoup, Tag

from cleaning.filters import filter_admission_only, remove_site_boilerplate
from cleaning.models import CleanTable
from cleaning.normalizer import normalize_matrix, normalize_text


@dataclass
class HtmlCleaningResult:
    text: str
    source_text_length: int
    tables: List[CleanTable] = field(default_factory=list)
    quality_flags: List[str] = field(default_factory=list)
    extraction_status: str = "success"
    extraction_quality: str = "good"
    removed_boilerplate_lines: int = 0


_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "canvas", "iframe")
_CHROME_TOKEN = re.compile(
    r"(?i)(?:^|[-_\s])(cookie|social-links?|site-footer|global-footer|newsletter|"
    r"subscribe|visitor-stat|chatbot|chat-widget|central-ai|language-selector|"
    r"country-selector)(?:$|[-_\s])"
)


def clean_html(
    raw_html: bytes,
    *,
    title: str,
    category: str,
    raw_extracted_text: str,
    dynamic_page: bool,
    source_id: str,
    dependency_responses: Optional[Mapping[str, str]] = None,
) -> HtmlCleaningResult:
    if source_id == "DIU-APP-001":
        text = _application_guidance(raw_extracted_text, title)
        return HtmlCleaningResult(
            text=text,
            source_text_length=len(raw_extracted_text),
            quality_flags=["form_controls_removed"],
            extraction_quality="good",
        )

    soup = BeautifulSoup(raw_html, "html.parser")
    for node in soup.find_all(_DROP_TAGS):
        node.decompose()
    for node in soup.find_all(["nav", "footer", "aside"]):
        node.decompose()
    for node in list(soup.find_all(True)):
        if node.attrs is None:
            continue
        tokens = " ".join(
            [str(node.get("id", "")), *[str(item) for item in node.get("class", [])]]
        )
        if _CHROME_TOKEN.search(tokens):
            node.decompose()

    root = _content_root(soup)
    quality_flags: List[str] = []

    preserve_form_labels = category in {"admission_application_process", "waivers"}
    forms = list(root.find_all("form"))
    if forms:
        if preserve_form_labels:
            for form in forms:
                for control in form.find_all(
                    ["input", "select", "option", "textarea", "button", "table"]
                ):
                    control.decompose()
            quality_flags.append("form_controls_removed")
        else:
            for form in forms:
                form.decompose()
            quality_flags.append("unrelated_forms_removed")

    tables: List[CleanTable] = []
    rejected_tables = 0
    for index, table in enumerate(list(root.find_all("table")), start=1):
        cleaned_table = _extract_reliable_table(table, index=index)
        if cleaned_table is None:
            rejected_tables += 1
            continue
        tables.append(cleaned_table)
        # The same responsive data is commonly rendered once as cards and once as
        # a desktop table. Retain its structured view without duplicating it in text.
        table.decompose()

    if source_id == "DIU-PROG-001":
        program_table = _program_catalog_table(dependency_responses)
        if program_table is None:
            program_table = _extract_program_grid(root)
        if program_table is not None:
            tables.append(program_table)

    if source_id == "DIU-FEE-001":
        tuition_table = _tuition_fee_table(dependency_responses)
        if tuition_table is not None:
            tables = [tuition_table]

    text = normalize_text(root.get_text("\n", strip=True))
    if dynamic_page and re.search(
        r"(?i)Important Notices\s+No notices available\.?", text
    ):
        quality_flags.append("dynamic_content_incomplete")
        text = re.sub(
            r"(?im)^Important Notices\s*$\n^No notices available\.?\s*$",
            "",
            text,
        )
    text, removed = remove_site_boilerplate(text)
    if title.casefold() not in text.casefold():
        text = normalize_text(f"{title}\n\n{text}")
    text, relevance_flags = filter_admission_only(
        text, title=title, category=category
    )
    quality_flags.extend(relevance_flags)
    if removed:
        quality_flags.append("boilerplate_removed")
    if rejected_tables:
        quality_flags.append("html_table_not_structured")

    meaningful = _meaningful_body(text, title)
    extraction_status = "success"
    extraction_quality = "good"
    if len(meaningful) < 50:
        quality_flags.extend(["empty_section", "short_content"])
        extraction_status = "partial"
        extraction_quality = "limited"
    elif len(text) < 200:
        quality_flags.append("short_content")
        extraction_quality = "limited"

    if dynamic_page and source_id == "DIU-PROG-002":
        quality_flags.append("dynamic_content_incomplete")
        extraction_status = "partial"
        extraction_quality = "limited"

    return HtmlCleaningResult(
        text=text,
        source_text_length=len(raw_extracted_text),
        tables=tables,
        quality_flags=sorted(set(quality_flags)),
        extraction_status=extraction_status,
        extraction_quality=extraction_quality,
        removed_boilerplate_lines=removed,
    )


def _content_root(soup: BeautifulSoup) -> Tag:
    candidates = soup.find_all("main")
    if not candidates:
        candidates = soup.find_all("article")
    if candidates:
        return max(candidates, key=lambda node: len(node.get_text(" ", strip=True)))
    if soup.body is not None:
        return soup.body
    return soup


def _extract_reliable_table(table: Tag, *, index: int) -> CleanTable | None:
    raw_rows = []
    header_from_markup = False
    for row_index, row in enumerate(table.find_all("tr")):
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = row.find_all(["th", "td"])
        if row_index == 0 and any(cell.name == "th" for cell in cells):
            header_from_markup = True
        raw_rows.append([cell.get_text(" ", strip=True) for cell in cells])
    matrix = normalize_matrix(raw_rows)
    if len(matrix) < 2 or len(matrix[0]) < 2 or not header_from_markup:
        return None
    width = len(matrix[0])
    if any(len(row) != width for row in matrix) or any(not cell for cell in matrix[0]):
        return None
    if any(sum(bool(cell) for cell in row) < 2 for row in matrix[1:]):
        return None
    return CleanTable(
        headers=matrix[0],
        rows=matrix[1:],
        extraction_method="beautifulsoup_html_table",
        source_locator=f"html-table-{index}",
    )


def _meaningful_body(text: str, title: str) -> str:
    lines = [line for line in normalize_text(text).splitlines() if line]
    if lines and lines[0].casefold() == normalize_text(title).casefold():
        lines = lines[1:]
    return "\n".join(lines).strip()


_PROGRAMS_API_SUFFIX = "/api/v1/public/academic/programs"
_TUITION_FEES_API_PATH = "/api/v1/public/tuition-fees"
_PROGRAM_PAGE_ORIGIN = "https://daffodilvarsity.edu.bd"
_PROGRAM_PATH_SEGMENT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DURATION_UNIT = re.compile(r"\b(?:years?|months?|semesters?)\b", re.IGNORECASE)


def _program_page_url(program: Mapping[str, Any]) -> str:
    """Return only the individual route explicitly described by catalog fields."""

    department = str(program.get("department_short_name") or "").strip()
    slug = str(program.get("slug") or "").strip()
    if not (
        _PROGRAM_PATH_SEGMENT.fullmatch(department)
        and _PROGRAM_PATH_SEGMENT.fullmatch(slug)
    ):
        return ""
    return f"{_PROGRAM_PAGE_ORIGIN}/department/{department}/program/{slug}"


def _catalog_duration(program: Mapping[str, Any]) -> str:
    """Keep source units verbatim and reject ambiguous bare numbers."""

    duration = str(program.get("duration") or "").strip()
    return duration if _DURATION_UNIT.search(duration) else ""



def _format_fee_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = text.replace(",", "")
    if compact.isdigit():
        return f"{int(compact):,}"
    return text


def _tuition_fee_table(
    dependency_responses: Optional[Mapping[str, str]],
) -> Optional[CleanTable]:
    """Build the complete local tuition-fee table from the official API."""

    if not dependency_responses:
        return None

    body: Optional[str] = None
    for url, value in dependency_responses.items():
        if _TUITION_FEES_API_PATH in url:
            body = value
            break
    if body is None:
        return None

    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None

    records = payload.get("tuitions") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return None

    rows: List[List[str]] = []
    seen_program_names: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        publication_status = record.get("publication_status")
        if publication_status not in (None, "", 1, "1", True):
            continue

        name = str(record.get("program_name") or "").strip()
        if not name:
            continue

        name_key = name.casefold()
        if name_key in seen_program_names:
            continue
        seen_program_names.add(name_key)

        rows.append(
            [
                name,
                str(record.get("majors") or "").strip(),
                str(record.get("credit") or "").strip(),
                str(record.get("program_duration") or "").strip(),
                _format_fee_value(record.get("admission_fees")),
                _format_fee_value(record.get("semester_cost")),
                _format_fee_value(record.get("tuition_fees")),
                _format_fee_value(record.get("total_fees")),
            ]
        )

    if not rows:
        return None

    return CleanTable(
        headers=[
            "Full Program Name",
            "Majors",
            "Credit Hours",
            "Duration",
            "Payable During Admission",
            "Average Semester Fees",
            "Total Tuition Fees",
            "Total Program Fees",
        ],
        rows=rows,
        extraction_method="official_tuition_fees_api",
        source_locator="official-local-tuition-fees",
        extraction_quality="reliable",
    )


def _program_catalog_table(
    dependency_responses: Optional[Mapping[str, str]],
) -> Optional[CleanTable]:
    """Build the authoritative program catalog from the official API response.

    The Programs page renders one faculty tab at a time, so the captured DOM
    only ever contains a subset of the offerings. When collection captured the
    approved ``academic/programs`` dependency response, this handler builds a
    full catalog table from that official payload instead of the DOM grid. The
    source's department slug and program slug are also retained as the same
    individual route rendered by the catalog. Missing or malformed route fields
    stay empty rather than producing a guessed URL.
    """

    if not dependency_responses:
        return None
    body: Optional[str] = None
    for url, value in dependency_responses.items():
        if url.rstrip("/").endswith(_PROGRAMS_API_SUFFIX):
            body = value
            break
    if body is None:
        return None
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None
    program_types = payload.get("program_types")
    if not isinstance(program_types, list):
        return None
    faculty_by_id: Dict[int, str] = {}
    for faculty in payload.get("data") or []:
        if not isinstance(faculty, dict):
            continue
        try:
            faculty_id = int(faculty.get("id"))
        except (TypeError, ValueError):
            continue
        faculty_name = str(faculty.get("faculty_name") or "").strip()
        if faculty_name:
            faculty_by_id[faculty_id] = faculty_name
    rows: List[List[str]] = []
    seen_program_names: set[str] = set()
    for program_type in program_types:
        if not isinstance(program_type, dict):
            continue
        level = str(program_type.get("program_type_name") or "").strip()
        programs = program_type.get("programs")
        if not isinstance(programs, list):
            continue
        for program in programs:
            if not isinstance(program, dict):
                continue
            name = str(program.get("name") or "").strip()
            if not name:
                continue
            name_key = name.casefold()
            if name_key in seen_program_names:
                continue
            seen_program_names.add(name_key)
            tag = str(program.get("program_short_name") or "").strip()
            faculty = str(program.get("faculty_name") or "").strip()
            if not faculty:
                try:
                    faculty = faculty_by_id.get(int(program.get("faculty_id"))) or ""
                except (TypeError, ValueError):
                    faculty = ""
            department = str(program.get("department_name") or "").strip()
            duration = _catalog_duration(program)
            program_url = _program_page_url(program)
            rows.append(
                [name, tag, level, faculty, department, duration, program_url]
            )
    if not rows:
        return None
    return CleanTable(
        headers=[
            "Full Program Name",
            "Short Tag / Initials",
            "Program Level",
            "Faculty",
            "Department",
            "Duration",
            "Program Page",
        ],
        rows=rows,
        extraction_method="official_programs_api",
        source_locator="official-programs-catalog",
        extraction_quality="reliable",
    )


def _extract_program_grid(root: Tag) -> CleanTable | None:
    label = root.find(string=lambda value: value and "Full Program Name" in value)
    if label is None:
        return None
    header = label.parent
    if header is None or header.parent is None:
        return None
    container = header.parent.parent
    if container is None:
        return None
    listing = container.find("ul", recursive=False)
    if listing is None:
        return None
    rows = []
    for item in listing.find_all("li", recursive=False):
        cells = [
            child.get_text(" ", strip=True)
            for child in item.find_all("div", recursive=False)
        ]
        if len(cells) != 2 or not all(cells):
            return None
        rows.append(cells)
    if not rows:
        return None
    return CleanTable(
        headers=["Full Program Name", "Short Tag / Initials"],
        rows=rows,
        extraction_method="beautifulsoup_program_grid",
        source_locator="program-grid-1",
    )


def _application_guidance(raw_text: str, title: str) -> str:
    """Retain public process/options while excluding blank personal-data controls."""

    lines = [line for line in normalize_text(raw_text).splitlines() if line]
    try:
        start = next(
            index for index, line in enumerate(lines) if line.casefold() == "current step:"
        )
    except StopIteration:
        return normalize_text(title)
    try:
        end = next(
            index
            for index in range(start, len(lines))
            if lines[index].startswith(
                "You have to finish the submission process of the online admission form"
            )
        )
    except StopIteration:
        end = min(len(lines) - 1, start + 80)
    return normalize_text(f"{title}\n\n" + "\n".join(lines[start : end + 1]))
