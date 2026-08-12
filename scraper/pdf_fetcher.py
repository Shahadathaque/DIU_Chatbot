"""Original-byte acquisition for PDFs explicitly present in the registry."""

from __future__ import annotations

from typing import Optional

from scraper.fetcher import (
    FetchConfig,
    FetchResult,
    _fetch_error,
    _fetch_http,
    coerce_fetch_config,
)

_PDF_ACCEPT = "application/pdf, application/octet-stream;q=0.8, */*;q=0.1"


def fetch_pdf(
    url: str, config: Optional[FetchConfig] = None
) -> FetchResult:
    """Download a PDF as bytes and reject obvious HTML/error-page responses.

    No PDF rewriting, decompression, OCR, or text normalization occurs here.
    A valid PDF header may legally appear within the first 1,024 bytes, so the
    signature check permits a short binary preamble.
    """

    resolved = coerce_fetch_config(config)
    result = _fetch_http(
        url,
        resolved,
        fetch_method="requests_pdf",
        accept=_PDF_ACCEPT,
    )
    if b"%PDF-" not in result.body[:1024]:
        raise _fetch_error(
            "requests_pdf response does not contain a PDF signature",
            url=url,
            fetch_method="requests_pdf",
            status_code=result.status_code,
            final_url=result.final_url,
            redirect_chain=result.redirect_chain,
            attempts=result.attempts,
        )
    mime_type = (result.mime_type or "").lower()
    prefix = result.body[:1024].lstrip().lower()
    if "html" in mime_type or prefix.startswith((b"<!doctype html", b"<html")):
        raise _fetch_error(
            "requests_pdf returned an HTML payload instead of a PDF",
            url=url,
            fetch_method="requests_pdf",
            status_code=result.status_code,
            final_url=result.final_url,
            redirect_chain=result.redirect_chain,
            attempts=result.attempts,
        )
    return result


__all__ = ["fetch_pdf"]
