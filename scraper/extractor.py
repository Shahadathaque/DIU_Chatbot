"""Lightweight, non-destructive text extraction from collected source bytes.

Extraction here is deliberately modest.  The caller must retain
``FetchResult.body`` as the raw capture; this module only creates a convenient
text view and does not normalize facts, infer rules, summarize, or run OCR.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Optional, Tuple, Union

from scraper.exceptions import ExtractionError, FetchDependencyError
from scraper.fetcher import FetchResult


@dataclass(frozen=True)
class ExtractedContent:
    """An optional text view derived from an immutable raw capture."""

    text: Optional[str]
    title: Optional[str]
    extraction_method: str
    page_count: Optional[int] = None
    warnings: Tuple[str, ...] = ()


def extract_fetch_result(result: FetchResult) -> ExtractedContent:
    """Select conservative extraction from response type and byte signature."""

    mime_type = (result.mime_type or "").lower()
    prefix = result.body[:1024].lstrip().lower()

    if mime_type == "application/pdf" or b"%pdf-" in result.body[:1024].lower():
        return ExtractedContent(
            text=None,
            title=None,
            extraction_method="none",
            warnings=(
                "PDF embedded-text extraction is deferred; original bytes preserved and OCR not attempted",
            ),
        )
    if (
        result.rendered
        or "html" in mime_type
        or prefix.startswith(b"<!doctype html")
        or prefix.startswith(b"<html")
    ):
        return extract_html(result.body)
    if mime_type.startswith("text/"):
        return ExtractedContent(
            text=_decode_text(result.body),
            title=None,
            extraction_method="plain_text_decode",
        )
    return ExtractedContent(
        text=None,
        title=None,
        extraction_method="none",
        warnings=(f"No extractor selected for {mime_type or 'unknown MIME type'}",),
    )


def extract_html(payload: Union[bytes, str]) -> ExtractedContent:
    """Extract visible document strings without dropping page sections.

    Only executable/non-readable elements are omitted.  Navigation, footer,
    lists, tables, headings, repeated strings, dates, and formatting order are
    intentionally retained for the later cleaning phase.
    """

    beautiful_soup = _load_beautifulsoup()
    try:
        soup = beautiful_soup(payload, "html.parser")
        title = None
        if soup.title is not None:
            candidate = soup.title.get_text(" ", strip=True)
            title = candidate or None

        for element in soup.find_all(
            ["script", "style", "noscript", "template"]
        ):
            element.decompose()

        root = soup.body if soup.body is not None else soup
        fragments = [str(fragment).strip() for fragment in root.stripped_strings]
        text = "\n".join(fragment for fragment in fragments if fragment)
        return ExtractedContent(
            text=text,
            title=title,
            extraction_method="beautifulsoup_html_parser",
        )
    except Exception as exc:
        message = _concise_exception(exc)
        raise ExtractionError(f"HTML extraction failed: {message}") from exc


def extract_html_text(payload: Union[bytes, str]) -> str:
    """Return only the conservative HTML text view."""

    return extract_html(payload).text or ""


def extract_pdf(
    payload: bytes, *, strict_dependency: bool = False
) -> ExtractedContent:
    """Optionally extract embedded PDF text with pypdf, never OCR.

    ``pypdf`` is intentionally optional because it is not part of the Phase 4
    dependency set.  When absent, raw PDF acquisition remains fully supported
    and the result records why no derived text was produced.
    """

    pdf_reader = _load_pypdf(strict_dependency=strict_dependency)
    if pdf_reader is None:
        return ExtractedContent(
            text=None,
            title=None,
            extraction_method="none",
            warnings=(
                "PDF text extraction skipped because optional pypdf is not installed",
            ),
        )

    if b"%PDF-" not in payload[:1024]:
        raise ExtractionError("PDF extraction failed: missing PDF signature")

    try:
        reader = pdf_reader(BytesIO(payload), strict=False)
        title = _pdf_title(reader)
        pages = []
        warnings = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:
                pages.append("")
                warnings.append(
                    f"Page {index} text extraction failed: "
                    f"{_concise_exception(exc)}"
                )
        text = "\n\f\n".join(pages) if pages else None
        if text is not None and not text.strip():
            text = None
            warnings.append(
                "PDF contains no extractable embedded text; OCR was not attempted"
            )
        return ExtractedContent(
            text=text,
            title=title,
            extraction_method="pypdf_embedded_text",
            page_count=len(reader.pages),
            warnings=tuple(warnings),
        )
    except Exception as exc:
        message = _concise_exception(exc)
        # Embedded-text parsing is best effort and must never prevent the raw,
        # signature-validated PDF from being stored for later visual review.
        return ExtractedContent(
            text=None,
            title=None,
            extraction_method="none",
            warnings=(f"PDF text extraction failed; raw bytes preserved: {message}",),
        )


def extract_pdf_text(
    payload: bytes, *, strict_dependency: bool = False
) -> Optional[str]:
    """Return embedded PDF text when the optional extractor is available."""

    return extract_pdf(payload, strict_dependency=strict_dependency).text


def _load_beautifulsoup() -> Any:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise FetchDependencyError(
            "HTML extraction requires the pinned 'beautifulsoup4' package; "
            "install project requirements first"
        ) from exc
    return BeautifulSoup


def _load_pypdf(*, strict_dependency: bool) -> Optional[Any]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        if strict_dependency:
            raise FetchDependencyError(
                "Optional PDF text extraction requires 'pypdf'; raw PDF "
                "download works without it"
            ) from exc
        return None
    return PdfReader


def _pdf_title(reader: Any) -> Optional[str]:
    try:
        metadata = reader.metadata
        title = metadata.title if metadata is not None else None
    except Exception:
        return None
    if title is None:
        return None
    candidate = str(title).strip()
    return candidate or None


def _decode_text(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode("utf-8", errors="replace")


def _concise_exception(exc: BaseException, limit: int = 240) -> str:
    message = " ".join(str(exc).split()) or type(exc).__name__
    if len(message) > limit:
        return message[: limit - 1] + "…"
    return message


__all__ = [
    "ExtractedContent",
    "extract_fetch_result",
    "extract_html",
    "extract_html_text",
    "extract_pdf",
    "extract_pdf_text",
]
