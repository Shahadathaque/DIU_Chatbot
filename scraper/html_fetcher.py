"""Conservative HTTP acquisition for registered static HTML sources."""

from __future__ import annotations

from typing import Optional

from scraper.fetcher import (
    FetchConfig,
    FetchResult,
    _fetch_error,
    _fetch_http,
    coerce_fetch_config,
)

_HTML_ACCEPT = (
    "text/html, application/xhtml+xml;q=0.9, text/plain;q=0.7, */*;q=0.1"
)


def fetch_html(
    url: str, config: Optional[FetchConfig] = None
) -> FetchResult:
    """Download one static page while preserving its response bytes.

    The content type is reported rather than forced.  This matters when an
    official endpoint legitimately redirects or returns a mislabeled payload;
    downstream storage can retain the bytes and provenance for review.
    """

    resolved = coerce_fetch_config(config)
    result = _fetch_http(
        url,
        resolved,
        fetch_method="requests",
        accept=_HTML_ACCEPT,
    )
    mime_type = (result.mime_type or "").lower()
    prefix = result.body[:1024].lstrip().lower()
    looks_html = prefix.startswith((b"<!doctype html", b"<html", b"<?xml"))
    declared_text = mime_type.startswith("text/") or mime_type == "application/xhtml+xml"
    if not result.body:
        raise _fetch_error(
            "requests returned an empty HTML response",
            url=url,
            fetch_method="requests",
            status_code=result.status_code,
            final_url=result.final_url,
            redirect_chain=result.redirect_chain,
            attempts=result.attempts,
        )
    if not declared_text and not looks_html:
        raise _fetch_error(
            f"requests returned unexpected HTML content type: {mime_type or 'unknown'}",
            url=url,
            fetch_method="requests",
            status_code=result.status_code,
            final_url=result.final_url,
            redirect_chain=result.redirect_chain,
            attempts=result.attempts,
        )
    return result


__all__ = ["fetch_html"]
