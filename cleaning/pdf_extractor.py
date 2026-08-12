"""Layout-aware embedded-text PDF extraction; OCR is intentionally excluded."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import List, Sequence

from cleaning.models import CleanTable, PageText
from cleaning.normalizer import normalize_matrix, normalize_text


@dataclass
class PdfExtractionResult:
    text: str
    source_text_length: int
    pages: List[PageText] = field(default_factory=list)
    tables: List[CleanTable] = field(default_factory=list)
    quality_flags: List[str] = field(default_factory=list)
    extraction_status: str = "success"
    extraction_quality: str = "good"
    extraction_method: str = "pdfplumber_embedded_text"
    table_candidates: int = 0
    rejected_table_candidates: int = 0


def extract_pdf(raw_pdf: bytes) -> PdfExtractionResult:
    if not raw_pdf.startswith(b"%PDF-"):
        raise ValueError("PDF payload does not begin with a PDF signature")
    try:
        import pdfplumber
    except ImportError as error:
        raise RuntimeError("pdfplumber is required for Phase 5 PDF extraction") from error

    pages: List[PageText] = []
    tables: List[CleanTable] = []
    raw_page_texts: List[str] = []
    table_candidates = 0
    rejected = 0

    with pdfplumber.open(BytesIO(raw_pdf)) as document:
        for page_number, page in enumerate(document.pages, start=1):
            raw_text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            raw_page_texts.append(raw_text)
            normalized = normalize_text(raw_text)
            try:
                candidates = page.extract_tables() or []
            except Exception:
                candidates = []
                rejected += 1
            reliable_count = 0
            for table_index, candidate in enumerate(candidates, start=1):
                table_candidates += 1
                cleaned = reliable_pdf_table(
                    candidate,
                    page_number=page_number,
                    table_index=table_index,
                )
                if cleaned is None:
                    rejected += 1
                    continue
                reliable_count += 1
                tables.append(cleaned)
            page_flags = []
            if not normalized:
                page_flags.append("no_embedded_text")
            pages.append(
                PageText(
                    page_number=page_number,
                    text=normalized,
                    character_count=len(normalized),
                    table_candidates=len(candidates),
                    reliable_tables=reliable_count,
                    quality_flags=page_flags,
                )
            )

    text = normalize_text("\n\n".join(page.text for page in pages if page.text))
    flags: List[str] = []
    empty_pages = [page.page_number for page in pages if not page.text]
    if empty_pages:
        flags.append("pdf_pages_without_embedded_text")
    if rejected:
        flags.append("pdf_table_uncertain")
    if not text:
        flags.extend(["empty_section", "short_content"])
        status = "failed"
        quality = "unusable_without_ocr"
    else:
        status = "success"
        quality = "good_with_layout_warnings" if flags else "good"

    return PdfExtractionResult(
        text=text,
        source_text_length=len("\n\n".join(raw_page_texts)),
        pages=pages,
        tables=tables,
        quality_flags=flags,
        extraction_status=status,
        extraction_quality=quality,
        table_candidates=table_candidates,
        rejected_table_candidates=rejected,
    )


def reliable_pdf_table(
    rows: Sequence[Sequence[object]], *, page_number: int, table_index: int
) -> CleanTable | None:
    matrix = normalize_matrix(rows)
    if len(matrix) < 2:
        return None
    width = len(matrix[0])
    if width < 2 or width > 12 or any(len(row) != width for row in matrix):
        return None
    if any(not cell for cell in matrix[0]):
        return None
    total = len(matrix) * width
    density = sum(bool(cell) for row in matrix for cell in row) / total
    if density < 0.72:
        return None
    if any(sum(bool(cell) for cell in row) < 2 for row in matrix[1:]):
        return None
    return CleanTable(
        headers=matrix[0],
        rows=matrix[1:],
        extraction_method="pdfplumber_table",
        page_number=page_number,
        source_locator=f"page-{page_number}-table-{table_index}",
    )
