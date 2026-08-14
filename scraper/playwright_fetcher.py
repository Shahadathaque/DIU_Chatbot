"""Rendered DOM acquisition for registry sources classified as dynamic."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Tuple
from urllib.parse import urlsplit

from scraper.exceptions import FetchDependencyError, FetchError
from scraper.fetcher import (
    FetchConfig,
    FetchResult,
    _RETRYABLE_STATUS_CODES,
    _backoff_delay,
    _concise_exception,
    _fetch_error,
    _mime_type,
    _string_headers,
    _validate_public_url,
    coerce_fetch_config,
)
from scraper.utils import canonicalize_url

LOGGER = logging.getLogger(__name__)


def fetch_dynamic_html(
    url: str,
    config: Optional[FetchConfig] = None,
    *,
    approved_dependency_urls: Tuple[str, ...] = (),
) -> FetchResult:
    """Render one dynamic URL in headless Chromium and return the final DOM.

    Navigation waits for ``domcontentloaded`` and then gives network activity a
    short, bounded opportunity to settle.  A network-idle timeout is non-fatal:
    analytics and long polling must not make an otherwise useful page fail.
    """

    resolved = coerce_fetch_config(config)
    candidate = _validate_public_url(url)
    approved_dependencies = tuple(
        dict.fromkeys(
            canonicalize_url(_validate_public_url(value))
            for value in approved_dependency_urls
        )
    )
    sync_playwright, playwright_error, playwright_timeout = _load_playwright()

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except playwright_error as exc:
                raise FetchDependencyError(
                    "Chromium could not start. Install the browser with: "
                    "playwright install chromium"
                ) from exc

            try:
                context = browser.new_context(
                    user_agent=resolved.user_agent,
                    extra_http_headers={
                        "Accept": (
                            "text/html, application/xhtml+xml;q=0.9, "
                            "*/*;q=0.1"
                        )
                    },
                    ignore_https_errors=not resolved.verify_tls,
                    # BrowserContext.route() cannot intercept requests served
                    # by a service worker.  Blocking service workers keeps the
                    # registered-origin route below authoritative.
                    service_workers="block",
                )
                blocked_origins = set()
                observed_dependencies = set()
                context.route(
                    "**/*",
                    lambda route: _route_registered_origin(
                        route,
                        candidate,
                        blocked_origins,
                        frozenset(approved_dependencies),
                        observed_dependencies,
                    ),
                )
                # WebSockets use a separate Playwright routing API and are not
                # needed to capture the rendered admission content.  Block
                # them before creating a page so they cannot bypass the
                # registered-origin HTTP boundary.
                context.route_web_socket(
                    "**/*",
                    lambda web_socket: _block_web_socket(
                        web_socket, blocked_origins
                    ),
                )
                try:
                    return _navigate_with_retries(
                        context,
                        candidate,
                        resolved,
                        playwright_error,
                        playwright_timeout,
                        blocked_origins,
                        getattr(browser, "version", None),
                        approved_dependencies,
                        observed_dependencies,
                    )
                finally:
                    context.close()
            finally:
                browser.close()
    except (FetchError, FetchDependencyError):
        raise
    except playwright_error as exc:
        message = _concise_exception(exc)
        raise _fetch_error(
            f"playwright failed: {message}",
            url=candidate,
            fetch_method="playwright",
            cause=exc,
        ) from exc


def _make_dependency_response_capture(
    approved_dependency_urls: Tuple[str, ...],
    max_response_bytes: int,
) -> Tuple[Any, Dict[str, str]]:
    """Capture bodies of approved read-only JSON dependency responses.

    Approved dependencies are routed to proceed by :func:`_route_registered_origin`,
    so the page listener observes their actual responses. Only GET fetch/XHR
    responses whose canonical URL is in the approved set and whose content type
    is JSON are retained, bounded by the configured byte limit. The decoded
    bodies are returned keyed by canonical URL for downstream provenance.
    """

    approved = frozenset(approved_dependency_urls)
    captured: Dict[str, str] = {}

    def _on_response(response: Any) -> None:
        request = getattr(response, "request", None)
        if request is None:
            return
        try:
            requested_canonical = canonicalize_url(request.url)
        except Exception:
            return
        if requested_canonical not in approved:
            return
        if str(getattr(request, "method", "GET")).upper() != "GET":
            return
        if str(getattr(request, "resource_type", "")) not in {"fetch", "xhr"}:
            return
        content_type = ""
        try:
            content_type = str(
                (response.headers.get("content-type") or "") or ""
            ).lower()
        except Exception:
            content_type = ""
        if "json" not in content_type:
            return
        if requested_canonical in captured:
            return
        try:
            body = response.body()
        except Exception:
            return
        if not isinstance(body, bytes) or len(body) > max_response_bytes:
            return
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            return
        captured[requested_canonical] = decoded

    return _on_response, captured


def _navigate_with_retries(
    context: Any,
    url: str,
    config: FetchConfig,
    playwright_error: Any,
    playwright_timeout: Any,
    blocked_origins: set[str],
    browser_version: Optional[str],
    approved_dependency_urls: Tuple[str, ...],
    observed_dependency_urls: set[str],
) -> FetchResult:
    attempts = config.max_retries + 1

    for attempt in range(1, attempts + 1):
        page = context.new_page()
        page.set_default_timeout(config.playwright_timeout_ms)
        attempted = False
        try:
            if config.before_attempt is not None:
                config.before_attempt(url)
            attempted = True
            dependency_listener, dependency_bodies = _make_dependency_response_capture(
                approved_dependency_urls, config.max_response_bytes
            )
            page.on("response", dependency_listener)
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=config.playwright_timeout_ms,
            )
            status_code = response.status if response is not None else None

            if response is None:
                raise _fetch_error(
                    "playwright did not receive a main-document response",
                    url=url,
                    fetch_method="playwright",
                    attempts=attempt,
                )

            if (
                status_code in _RETRYABLE_STATUS_CODES
                and attempt < attempts
            ):
                delay = _backoff_delay(config, attempt)
                LOGGER.warning(
                    "playwright received HTTP %s; retrying in %.1fs "
                    "(attempt %s/%s)",
                    status_code,
                    delay,
                    attempt,
                    attempts,
                )
                page.close()
                time.sleep(delay)
                continue

            if status_code is not None and not 200 <= status_code < 300:
                raise _fetch_error(
                    f"playwright returned HTTP {status_code}",
                    url=url,
                    fetch_method="playwright",
                    status_code=status_code,
                    final_url=page.url,
                    redirect_chain=_redirect_chain(response),
                    attempts=attempt,
                )

            if canonicalize_url(page.url) != canonicalize_url(url):
                raise _fetch_error(
                    "playwright blocked navigation outside the registered canonical URL",
                    url=url,
                    fetch_method="playwright",
                    status_code=status_code,
                    final_url=page.url,
                    redirect_chain=_redirect_chain(response),
                    attempts=attempt,
                )

            response_headers = _string_headers(response.all_headers())
            mime_type = _mime_type(response_headers.get("content-type"))
            if mime_type not in {"text/html", "application/xhtml+xml"}:
                raise _fetch_error(
                    f"playwright returned unexpected content type: {mime_type or 'unknown'}",
                    url=url,
                    fetch_method="playwright",
                    status_code=status_code,
                    final_url=page.url,
                    redirect_chain=_redirect_chain(response),
                    attempts=attempt,
                )

            _wait_for_stable_dom(page, config, playwright_timeout)
            if canonicalize_url(page.url) != canonicalize_url(url):
                raise _fetch_error(
                    "playwright blocked client-side navigation outside the registered canonical URL",
                    url=url,
                    fetch_method="playwright",
                    status_code=status_code,
                    final_url=page.url,
                    redirect_chain=_redirect_chain(response),
                    attempts=attempt,
                )
            materialized_shadow_roots = _materialize_open_shadow_roots(page)
            redactions = _redact_sensitive_dom_values(page)
            rendered_dom = page.content().encode("utf-8")
            if len(rendered_dom) > config.max_response_bytes:
                raise _fetch_error(
                    "playwright DOM exceeds the "
                    f"{config.max_response_bytes}-byte limit",
                    url=url,
                    fetch_method="playwright",
                    status_code=status_code,
                    final_url=page.url,
                    redirect_chain=_redirect_chain(response),
                    attempts=attempt,
                )

            # The stored body is the rendered DOM, not the compressed network
            # response, so transport length/encoding would be misleading here.
            response_headers.pop("content-encoding", None)
            response_headers.pop("content-length", None)
            return FetchResult(
                body=rendered_dom,
                fetch_method="playwright",
                status_code=status_code,
                final_url=page.url,
                mime_type=mime_type,
                headers=response_headers,
                rendered=True,
                redirect_chain=_redirect_chain(response),
                attempts=attempt,
                blocked_origins=tuple(sorted(blocked_origins)),
                browser_version=browser_version,
                approved_dependency_urls=approved_dependency_urls,
                observed_dependency_urls=tuple(sorted(observed_dependency_urls)),
                dependency_responses=tuple(sorted(dependency_bodies.items())),
                redactions=redactions,
                materialized_shadow_roots=materialized_shadow_roots,
            )
        except FetchError:
            raise
        except (playwright_timeout, playwright_error) as exc:
            if attempt < attempts:
                delay = _backoff_delay(config, attempt)
                LOGGER.warning(
                    "playwright navigation failed; retrying in %.1fs "
                    "(attempt %s/%s)",
                    delay,
                    attempt,
                    attempts,
                )
                time.sleep(delay)
                continue
            message = _concise_exception(exc)
            raise _fetch_error(
                f"playwright navigation failed: {message}",
                url=url,
                fetch_method="playwright",
                cause=exc,
                final_url=page.url,
                attempts=attempt,
            ) from exc
        finally:
            if not page.is_closed():
                page.close()
            if attempted and config.after_attempt is not None:
                config.after_attempt(url)

    raise _fetch_error(
        "playwright navigation exhausted retries",
        url=url,
        fetch_method="playwright",
    )


def _route_registered_origin(
    route: Any,
    registered_url: str,
    blocked_origins: set[str],
    approved_dependency_urls: frozenset[str] = frozenset(),
    observed_dependency_urls: Optional[set[str]] = None,
) -> None:
    request = route.request
    requested_url = request.url
    parts = urlsplit(requested_url)
    if parts.scheme in {"data", "blob", "about"}:
        route.continue_()
        return

    registered = urlsplit(registered_url)
    requested_origin = (parts.scheme.lower(), parts.netloc.lower())
    registered_origin = (registered.scheme.lower(), registered.netloc.lower())
    resource_type = getattr(request, "resource_type", "")
    method = str(getattr(request, "method", "GET")).upper()
    is_navigation = bool(request.is_navigation_request())
    safe_read = method in {"GET", "HEAD"}
    requested_canonical = canonicalize_url(requested_url)
    allowed = requested_origin == registered_origin and safe_read
    if is_navigation:
        allowed = allowed and requested_canonical == canonicalize_url(registered_url)
    elif (
        safe_read
        and resource_type in {"fetch", "xhr"}
        and requested_canonical in approved_dependency_urls
    ):
        allowed = True
        if observed_dependency_urls is not None:
            observed_dependency_urls.add(requested_canonical)
    blocked_nonessential = resource_type in {"image", "media", "font"}
    if blocked_nonessential:
        allowed = False

    if allowed:
        route.continue_()
        return
    if requested_origin != registered_origin:
        origin = (
            f"{parts.scheme.lower()}://{parts.netloc.lower()}"
            if parts.netloc
            else parts.scheme
        )
        blocked_origins.add(origin)
    route.abort()


def _block_web_socket(web_socket: Any, blocked_origins: set[str]) -> None:
    """Block and audit every browser WebSocket without connecting upstream."""

    parts = urlsplit(web_socket.url)
    origin = (
        f"{parts.scheme.lower()}://{parts.netloc.lower()}"
        if parts.netloc
        else parts.scheme.lower()
    )
    if origin:
        blocked_origins.add(origin)
    web_socket.close(
        code=1008,
        reason="WebSockets are disabled during controlled collection",
    )


def _redact_sensitive_dom_values(page: Any) -> Tuple[str, ...]:
    """Blank anonymous security-token values before serializing rendered DOM.

    This is a privacy/safety boundary, not Phase 5 content cleaning. The stored
    capture is already a browser-produced DOM representation rather than wire
    bytes, and each affected field name is recorded in provenance.
    """

    values = page.evaluate(
        r"""
        () => {
          const sensitive = /(^|[_-])(csrf|xsrf|authenticity|nonce|token)($|[_-])/i;
          const redacted = [];
          for (const element of document.querySelectorAll('input, meta')) {
            const identifiers = [
              element.getAttribute('name') || '',
              element.getAttribute('id') || '',
              element.getAttribute('property') || '',
              element.getAttribute('http-equiv') || ''
            ];
            if (!identifiers.some((value) => sensitive.test(value))) continue;
            const attribute = element.tagName === 'META' ? 'content' : 'value';
            if (!element.hasAttribute(attribute)) continue;
            if (element.tagName === 'INPUT') element.value = '';
            element.setAttribute(attribute, '');
            redacted.push(`${element.tagName.toLowerCase()}:${identifiers.find(Boolean) || attribute}`);
          }
          const assignment = /((?:csrf|xsrf|authenticity|access|refresh)[_-]?token\s*[:=]\s*['"])[^'"]+(['"])/gi;
          for (const script of document.querySelectorAll('script')) {
            const before = script.textContent || '';
            const after = before.replace(assignment, '$1$2');
            if (after !== before) {
              script.textContent = after;
              redacted.push('script:security-token-assignment');
            }
          }
          return [...new Set(redacted)].sort();
        }
        """
    )
    if not isinstance(values, list):
        return ()
    return tuple(str(value) for value in values if str(value).strip())


def _materialize_open_shadow_roots(page: Any) -> int:
    """Copy readable open-shadow content into the serialized DOM capture."""

    value = page.evaluate(
        """
        () => {
          let count = 0;
          for (const host of document.querySelectorAll('*')) {
            if (!host.shadowRoot) continue;
            const capture = document.createElement('div');
            capture.setAttribute('data-capture-shadow-root', 'open');
            capture.innerHTML = host.shadowRoot.innerHTML;
            host.appendChild(capture);
            count += 1;
          }
          return count;
        }
        """
    )
    return value if isinstance(value, int) and value >= 0 else 0


def _redirect_chain(response: Any) -> Tuple[str, ...]:
    chain = []
    try:
        request = response.request
        previous = request.redirected_from
        while previous is not None:
            chain.append(request.url)
            request = previous
            previous = request.redirected_from
    except (AttributeError, TypeError):
        return ()
    chain.reverse()
    return tuple(chain)


def _wait_for_stable_dom(
    page: Any, config: FetchConfig, playwright_timeout: Any
) -> None:
    body_timeout = min(config.playwright_timeout_ms, 5_000)
    try:
        page.wait_for_selector("body", state="attached", timeout=body_timeout)
    except playwright_timeout:
        # page.content() may still preserve a useful response (for example an
        # XML-style error document), so absence of <body> is not fatal here.
        LOGGER.debug("Rendered response did not expose a body element")

    if config.playwright_network_idle_timeout_ms:
        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=config.playwright_network_idle_timeout_ms,
            )
        except playwright_timeout:
            LOGGER.debug("Network remained active after the bounded idle wait")

    if config.playwright_settle_ms:
        page.wait_for_timeout(config.playwright_settle_ms)


def _load_playwright() -> Tuple[Any, Any, Any]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchDependencyError(
            "Dynamic fetching requires Playwright; install project "
            "requirements and run: playwright install chromium"
        ) from exc
    return sync_playwright, PlaywrightError, PlaywrightTimeoutError


__all__ = ["fetch_dynamic_html"]
