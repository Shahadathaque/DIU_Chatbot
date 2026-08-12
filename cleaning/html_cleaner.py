"""Conservative HTML-to-text and reliable-table cleaning."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

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
        program_table = _extract_program_grid(root)
        if program_table is not None:
            tables.append(program_table)

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
