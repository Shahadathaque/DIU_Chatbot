"""Common fetch contracts and controlled source dispatch.

This module deliberately contains no crawling logic.  It accepts one already
registered source and selects exactly one acquisition strategy for that URL.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple, runtime_checkable
from urllib.parse import urljoin, urlsplit

from scraper.exceptions import FetchDependencyError, FetchError

LOGGER = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "DIU-Admission-Research-Collector/1.0 "
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36 "
)
ROBOTS_USER_AGENT = "DIU-Admission-Research-Collector"

_RETRYABLE_STATUS_CODES = frozenset({408, 425, 500, 502, 503, 504})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
RESPONSE_HEADER_ALLOWLIST = frozenset(
    {
        "accept-ranges",
        "age",
        "cache-control",
        "content-disposition",
        "content-encoding",
        "content-language",
        "content-length",
        "content-location",
        "content-type",
        "date",
        "etag",
        "expires",
        "last-modified",
        "location",
        "retry-after",
        "server",
        "vary",
    }
)


@runtime_checkable
class FetchableSource(Protocol):
    """Minimum source-registry interface needed by :func:`fetch_source`."""

    url: str
    dynamic_page: bool
    approved_dependency_urls: Tuple[str, ...]


@dataclass(frozen=True)
class FetchConfig:
    """Bounded network and browser settings for one-source acquisition."""

    user_agent: str = DEFAULT_USER_AGENT
    connect_timeout_seconds: float = 10.0
    request_timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    max_retry_delay_seconds: float = 10.0
    max_response_bytes: int = 50 * 1024 * 1024
    verify_tls: bool = True
    playwright_timeout_ms: int = 30_000
    playwright_network_idle_timeout_ms: int = 5_000
    playwright_settle_ms: int = 500
    max_redirects: int = 0
    before_attempt: Optional[Callable[[str], None]] = None
    after_attempt: Optional[Callable[[str], None]] = None

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("user_agent must not be blank")
        if not math.isfinite(self.connect_timeout_seconds) or self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")
        if not math.isfinite(self.request_timeout_seconds) or self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if not math.isfinite(self.retry_backoff_seconds) or self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        if not math.isfinite(self.max_retry_delay_seconds) or self.max_retry_delay_seconds < 0:
            raise ValueError("max_retry_delay_seconds cannot be negative")
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if self.playwright_timeout_ms <= 0:
            raise ValueError("playwright_timeout_ms must be positive")
        if self.playwright_network_idle_timeout_ms < 0:
            raise ValueError(
                "playwright_network_idle_timeout_ms cannot be negative"
            )
        if self.playwright_settle_ms < 0:
            raise ValueError("playwright_settle_ms cannot be negative")
        if self.max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")


@dataclass(frozen=True)
class FetchResult:
    """Raw bytes and response provenance returned by every fetch strategy."""

    body: bytes
    fetch_method: str
    status_code: Optional[int]
    final_url: str
    mime_type: Optional[str]
    headers: Dict[str, str]
    rendered: bool = False
    redirect_chain: Tuple[str, ...] = ()
    attempts: int = 1
    blocked_origins: Tuple[str, ...] = ()
    browser_version: Optional[str] = None
    approved_dependency_urls: Tuple[str, ...] = ()
    observed_dependency_urls: Tuple[str, ...] = ()
    redactions: Tuple[str, ...] = ()
    materialized_shadow_roots: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.body, bytes):
            raise TypeError("FetchResult.body must be bytes")
        if not self.fetch_method.strip():
            raise ValueError("FetchResult.fetch_method must not be blank")
        if not self.final_url.strip():
            raise ValueError("FetchResult.final_url must not be blank")


def fetch_source(
    source: FetchableSource, config: Optional[FetchConfig] = None
) -> FetchResult:
    """Fetch one registered source using PDF, rendered, or static dispatch.

    URLs are never discovered or followed beyond normal HTTP redirects.  The
    caller remains responsible for selecting sources from the registry and for
    applying between-source rate limits.
    """

    resolved = coerce_fetch_config(config)
    url = _validate_public_url(source.url)

    if _source_is_pdf(source, url):
        from scraper.pdf_fetcher import fetch_pdf

        return fetch_pdf(url, resolved)

    if bool(source.dynamic_page):
        from scraper.playwright_fetcher import fetch_dynamic_html

        return fetch_dynamic_html(
            url,
            resolved,
            approved_dependency_urls=tuple(
                getattr(source, "approved_dependency_urls", ()) or ()
            ),
        )

    from scraper.html_fetcher import fetch_html

    return fetch_html(url, resolved)


def coerce_fetch_config(config: Optional[Any]) -> FetchConfig:
    """Return ``FetchConfig`` from an instance, mapping, or settings object.

    Settings objects may expose a subset of fetch fields; absent values retain
    conservative defaults.  Unknown mapping keys are rejected so misspelled
    safety settings cannot silently take effect.
    """

    if config is None:
        return FetchConfig()
    if isinstance(config, FetchConfig):
        return config

    field_names = {item.name for item in fields(FetchConfig)}
    if isinstance(config, Mapping):
        unknown = set(config) - field_names
        if unknown:
            names = ", ".join(sorted(str(item) for item in unknown))
            raise ValueError(f"Unknown fetch configuration field(s): {names}")
        values = {name: config[name] for name in field_names if name in config}
        return FetchConfig(**values)

    values = {
        name: getattr(config, name)
        for name in field_names
        if hasattr(config, name)
    }
    return FetchConfig(**values)


def _fetch_http(
    url: str,
    config: FetchConfig,
    *,
    fetch_method: str,
    accept: str,
) -> FetchResult:
    """Perform a bounded streaming GET with retries for transient failures."""

    url = _validate_public_url(url)
    requests = _load_requests()
    headers = {
        "Accept": accept,
        "Accept-Encoding": "identity",
        "User-Agent": config.user_agent,
    }
    timeout = (
        config.connect_timeout_seconds,
        config.request_timeout_seconds,
    )
    attempts = config.max_retries + 1

    for attempt in range(1, attempts + 1):
        response = None
        current_url = url
        redirect_chain = []
        attempted_request = False
        try:
            if config.before_attempt is not None:
                config.before_attempt(url)
            attempted_request = True
            for redirect_number in range(config.max_redirects + 1):
                response = requests.get(
                    current_url,
                    allow_redirects=False,
                    headers=headers,
                    stream=True,
                    timeout=timeout,
                    verify=config.verify_tls,
                )
                status_code = int(response.status_code)
                if status_code not in _REDIRECT_STATUS_CODES:
                    break
                location = response.headers.get("Location")
                if not location:
                    raise _fetch_error(
                        f"{fetch_method} redirect is missing Location",
                        url=url,
                        fetch_method=fetch_method,
                        status_code=status_code,
                        final_url=current_url,
                        redirect_chain=tuple(redirect_chain),
                        attempts=attempt,
                    )
                next_url = _validate_public_url(urljoin(current_url, location))
                _require_registered_redirect(url, next_url, fetch_method)
                if redirect_number >= config.max_redirects:
                    raise _fetch_error(
                        f"{fetch_method} exceeded {config.max_redirects} redirects",
                        url=url,
                        fetch_method=fetch_method,
                        status_code=status_code,
                        final_url=next_url,
                        redirect_chain=tuple(redirect_chain + [next_url]),
                        attempts=attempt,
                    )
                redirect_chain.append(next_url)
                response.close()
                response = None
                current_url = next_url

            if status_code in _RETRYABLE_STATUS_CODES and attempt < attempts:
                retry_after = _parse_retry_after(
                    response.headers.get("Retry-After")
                    or response.headers.get("retry-after")
                )
                if (
                    retry_after is not None
                    and retry_after > config.max_retry_delay_seconds
                ):
                    raise _fetch_error(
                        f"{fetch_method} retry deferred by server Retry-After",
                        url=url,
                        fetch_method=fetch_method,
                        status_code=status_code,
                        final_url=current_url,
                        redirect_chain=tuple(redirect_chain),
                        attempts=attempt,
                    )
                delay = _retry_delay(response.headers, config, attempt)
                LOGGER.warning(
                    "%s received HTTP %s; retrying in %.1fs (attempt %s/%s)",
                    fetch_method,
                    status_code,
                    delay,
                    attempt,
                    attempts,
                )
                response.close()
                time.sleep(delay)
                continue

            if status_code < 200 or status_code >= 300:
                raise _fetch_error(
                    f"{fetch_method} returned HTTP {status_code}",
                    url=url,
                    fetch_method=fetch_method,
                    status_code=status_code,
                    final_url=current_url,
                    redirect_chain=tuple(redirect_chain),
                    attempts=attempt,
                )

            response_headers = _string_headers(response.headers)
            content_encoding = response_headers.get("content-encoding", "").strip().lower()
            if content_encoding not in {"", "identity"}:
                raise _fetch_error(
                    f"{fetch_method} ignored Accept-Encoding: identity "
                    f"(received {content_encoding})",
                    url=url,
                    fetch_method=fetch_method,
                    status_code=status_code,
                    final_url=current_url,
                    redirect_chain=tuple(redirect_chain),
                    attempts=attempt,
                )
            body = _read_bounded_body(
                response,
                max_bytes=config.max_response_bytes,
                url=url,
                fetch_method=fetch_method,
            )
            return FetchResult(
                body=body,
                fetch_method=fetch_method,
                status_code=status_code,
                final_url=current_url,
                mime_type=_mime_type(response_headers.get("content-type")),
                headers=response_headers,
                rendered=False,
                redirect_chain=tuple(redirect_chain),
                attempts=attempt,
            )
        except FetchError:
            raise
        except requests.exceptions.RequestException as exc:
            if attempt < attempts and _is_retryable_request_exception(
                exc, requests
            ):
                delay = _backoff_delay(config, attempt)
                LOGGER.warning(
                    "%s request failed; retrying in %.1fs (attempt %s/%s)",
                    fetch_method,
                    delay,
                    attempt,
                    attempts,
                )
                time.sleep(delay)
                continue
            message = _concise_exception(exc)
            raise _fetch_error(
                f"{fetch_method} request failed: {message}",
                url=url,
                fetch_method=fetch_method,
                cause=exc,
                final_url=current_url,
                redirect_chain=tuple(redirect_chain),
                attempts=attempt,
            ) from exc
        finally:
            if response is not None:
                response.close()
            if attempted_request and config.after_attempt is not None:
                config.after_attempt(url)

    raise _fetch_error(
        f"{fetch_method} request exhausted retries",
        url=url,
        fetch_method=fetch_method,
    )


def _load_requests() -> Any:
    try:
        import requests
    except ImportError as exc:
        raise FetchDependencyError(
            "Static and PDF fetching require the pinned 'requests' package; "
            "install project requirements first"
        ) from exc
    return requests


def _read_bounded_body(
    response: Any,
    *,
    max_bytes: int,
    url: str,
    fetch_method: str,
) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except (TypeError, ValueError):
            declared_size = -1
        if declared_size > max_bytes:
            raise _fetch_error(
                f"{fetch_method} response exceeds the {max_bytes}-byte limit",
                url=url,
                fetch_method=fetch_method,
                status_code=int(response.status_code),
            )

    chunks = []
    received = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        received += len(chunk)
        if received > max_bytes:
            raise _fetch_error(
                f"{fetch_method} response exceeds the {max_bytes}-byte limit",
                url=url,
                fetch_method=fetch_method,
                status_code=int(response.status_code),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_public_url(url: str) -> str:
    candidate = str(url).strip()
    if any(ord(character) < 32 for character in candidate):
        raise FetchError(f"Unsupported source URL: {candidate!r}")
    try:
        parsed = urlsplit(candidate)
        # Accessing these properties performs additional bracket/port checks.
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise FetchError(f"Unsupported source URL: {candidate!r}") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise FetchError(f"Unsupported source URL: {candidate!r}")
    return candidate


def _source_is_pdf(source: Any, url: str) -> bool:
    declared = getattr(source, "is_pdf", None)
    if isinstance(declared, bool):
        return declared
    return urlsplit(url).path.lower().endswith(".pdf")


def _require_registered_redirect(
    registered_url: str, redirect_url: str, fetch_method: str
) -> None:
    from scraper.utils import canonicalize_url

    if canonicalize_url(redirect_url) != canonicalize_url(registered_url):
        raise _fetch_error(
            f"{fetch_method} blocked redirect outside the registered canonical URL",
            url=registered_url,
            fetch_method=fetch_method,
            final_url=redirect_url,
            redirect_chain=(redirect_url,),
        )


def _string_headers(headers: Mapping[str, Any]) -> Dict[str, str]:
    captured = {}
    for key, value in headers.items():
        normalized_key = str(key).lower()
        if normalized_key in RESPONSE_HEADER_ALLOWLIST:
            captured[normalized_key] = str(value)
    return captured


def _mime_type(content_type: Optional[str]) -> Optional[str]:
    if not content_type:
        return None
    value = content_type.partition(";")[0].strip().lower()
    return value or None


def _retry_delay(
    headers: Mapping[str, Any], config: FetchConfig, attempt: int
) -> float:
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    parsed = _parse_retry_after(retry_after)
    if parsed is not None:
        return parsed
    return _backoff_delay(config, attempt)


def _parse_retry_after(value: Optional[Any]) -> Optional[float]:
    if value is None:
        return None
    candidate = str(value).strip()
    try:
        parsed = float(candidate)
        return max(0.0, parsed) if math.isfinite(parsed) else None
    except ValueError:
        try:
            moment = parsedate_to_datetime(candidate)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return max(
                0.0,
                (moment - datetime.now(timezone.utc)).total_seconds(),
            )
        except (TypeError, ValueError, OverflowError):
            return None


def _backoff_delay(config: FetchConfig, attempt: int) -> float:
    delay = config.retry_backoff_seconds * (2 ** max(0, attempt - 1))
    return min(delay, config.max_retry_delay_seconds)


def _is_retryable_request_exception(exc: Exception, requests: Any) -> bool:
    return isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
    )


def _concise_exception(exc: BaseException, limit: int = 240) -> str:
    message = " ".join(str(exc).split()) or type(exc).__name__
    if len(message) > limit:
        return message[: limit - 1] + "…"
    return message


def _fetch_error(
    message: str,
    *,
    url: str,
    fetch_method: str,
    status_code: Optional[int] = None,
    cause: Optional[BaseException] = None,
    final_url: Optional[str] = None,
    redirect_chain: Tuple[str, ...] = (),
    attempts: int = 1,
) -> FetchError:
    error = FetchError(
        message,
        url=url,
        method=fetch_method,
        status_code=status_code,
        cause=cause,
        final_url=final_url,
        redirect_chain=redirect_chain,
        attempts=attempts,
    )
    # Alias used by FetchResult and failure serializers that share its wording.
    error.fetch_method = fetch_method
    return error


__all__ = [
    "DEFAULT_USER_AGENT",
    "ROBOTS_USER_AGENT",
    "RESPONSE_HEADER_ALLOWLIST",
    "FetchConfig",
    "FetchResult",
    "FetchableSource",
    "coerce_fetch_config",
    "fetch_source",
]
