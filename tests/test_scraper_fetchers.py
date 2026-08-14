"""Unit tests for controlled fetch dispatch and raw extraction.

All network and browser objects are local fakes.  Live DIU checks belong in the
documented sample run, not in the default unit-test suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pytest

from scraper.exceptions import FetchError
from scraper.extractor import extract_fetch_result, extract_html, extract_pdf
from scraper.fetcher import FetchConfig, FetchResult, fetch_source
from scraper.html_fetcher import fetch_html
from scraper.pdf_fetcher import fetch_pdf
from scraper.playwright_fetcher import (
    _make_dependency_response_capture,
    _route_registered_origin,
    fetch_dynamic_html,
)


class FakeRequestException(Exception):
    pass


class FakeConnectionError(FakeRequestException):
    pass


class FakeTimeout(FakeRequestException):
    pass


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes = b"<html><body>Admission</body></html>",
        headers: Optional[Dict[str, str]] = None,
        url: str = "https://example.test/final",
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.url = url
        self.closed = False

    def iter_content(self, chunk_size: int) -> Iterable[bytes]:
        del chunk_size
        yield self.body

    def close(self) -> None:
        self.closed = True


class FakeRequests:
    exceptions = SimpleNamespace(
        RequestException=FakeRequestException,
        ConnectionError=FakeConnectionError,
        Timeout=FakeTimeout,
    )

    def __init__(self, outcomes: List[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@dataclass
class FakeSource:
    url: str
    dynamic_page: bool = False
    approved_dependency_urls: Tuple[str, ...] = ()

    @property
    def is_pdf(self) -> bool:
        return self.url.lower().endswith(".pdf")


def test_static_fetch_preserves_bytes_and_allowlists_headers(monkeypatch: Any) -> None:
    response = FakeResponse(
        body=b"<html>raw bytes</html>",
        headers={
            "Content-Type": "text/html; charset=UTF-8",
            "ETag": '"capture-1"',
            "Set-Cookie": "do-not-persist=private",
            "X-Internal": "not-provenance",
        },
    )
    requests = FakeRequests([response])
    monkeypatch.setattr("scraper.fetcher._load_requests", lambda: requests)

    result = fetch_html("https://example.test/source", FetchConfig(max_retries=0))

    assert result.body == b"<html>raw bytes</html>"
    assert result.fetch_method == "requests"
    assert result.status_code == 200
    assert result.final_url == "https://example.test/source"
    assert result.mime_type == "text/html"
    assert result.headers == {
        "content-type": "text/html; charset=UTF-8",
        "etag": '"capture-1"',
    }
    assert result.rendered is False
    assert response.closed is True


def test_static_fetch_retries_only_within_bound(monkeypatch: Any) -> None:
    requests = FakeRequests(
        [
            FakeResponse(status_code=503),
            FakeResponse(status_code=200, body=b"eventual success"),
        ]
    )
    sleeps = []
    monkeypatch.setattr("scraper.fetcher._load_requests", lambda: requests)
    monkeypatch.setattr("scraper.fetcher.time.sleep", sleeps.append)

    result = fetch_html(
        "https://example.test/source",
        FetchConfig(max_retries=1, retry_backoff_seconds=0.25),
    )

    assert result.body == b"eventual success"
    assert len(requests.calls) == 2
    assert sleeps == [0.25]


def test_static_fetch_rejects_non_success_status(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "scraper.fetcher._load_requests",
        lambda: FakeRequests([FakeResponse(status_code=404)]),
    )

    with pytest.raises(FetchError, match="HTTP 404") as caught:
        fetch_html(
            "https://example.test/missing",
            FetchConfig(max_retries=0),
        )

    assert caught.value.status_code == 404
    assert caught.value.method == "requests"


def test_static_fetch_blocks_redirect_outside_registered_url(monkeypatch: Any) -> None:
    response = FakeResponse(
        status_code=302,
        headers={
            "Content-Type": "text/html",
            "Location": "https://third-party.example/collect",
        },
    )
    requests = FakeRequests([response])
    monkeypatch.setattr("scraper.fetcher._load_requests", lambda: requests)

    with pytest.raises(FetchError, match="outside the registered"):
        fetch_html("https://example.test/source", FetchConfig(max_retries=0))

    assert len(requests.calls) == 1


def test_static_fetch_rejects_unexpected_binary_payload(monkeypatch: Any) -> None:
    response = FakeResponse(
        body=b"\x89PNG\r\n",
        headers={"Content-Type": "image/png"},
    )
    monkeypatch.setattr(
        "scraper.fetcher._load_requests", lambda: FakeRequests([response])
    )

    with pytest.raises(FetchError, match="unexpected HTML content type"):
        fetch_html("https://example.test/source", FetchConfig(max_retries=0))


def test_retry_after_is_not_shortened(monkeypatch: Any) -> None:
    response = FakeResponse(
        status_code=503,
        headers={"Content-Type": "text/html", "Retry-After": "120"},
    )
    monkeypatch.setattr(
        "scraper.fetcher._load_requests", lambda: FakeRequests([response])
    )

    with pytest.raises(FetchError, match="retry deferred"):
        fetch_html(
            "https://example.test/source",
            FetchConfig(max_retries=1, max_retry_delay_seconds=10),
        )


def test_http_body_limit_is_enforced_while_streaming(monkeypatch: Any) -> None:
    response = FakeResponse(
        body=b"12345",
        headers={"Content-Type": "text/html"},
    )
    monkeypatch.setattr(
        "scraper.fetcher._load_requests", lambda: FakeRequests([response])
    )

    with pytest.raises(FetchError, match="4-byte limit"):
        fetch_html(
            "https://example.test/large",
            FetchConfig(max_retries=0, max_response_bytes=4),
        )


def test_pdf_fetch_preserves_original_pdf_bytes(monkeypatch: Any) -> None:
    raw_pdf = b"%PDF-1.7\nraw original bytes"
    response = FakeResponse(
        body=raw_pdf,
        headers={"Content-Type": "application/pdf"},
    )
    monkeypatch.setattr(
        "scraper.fetcher._load_requests", lambda: FakeRequests([response])
    )

    result = fetch_pdf(
        "https://example.test/document.pdf",
        FetchConfig(max_retries=0),
    )

    assert result.body == raw_pdf
    assert result.fetch_method == "requests_pdf"
    assert result.mime_type == "application/pdf"


def test_pdf_fetch_rejects_html_error_payload(monkeypatch: Any) -> None:
    response = FakeResponse(
        body=b"<html><title>Not found</title></html>",
        headers={"Content-Type": "text/html"},
    )
    monkeypatch.setattr(
        "scraper.fetcher._load_requests", lambda: FakeRequests([response])
    )

    with pytest.raises(FetchError, match="PDF signature"):
        fetch_pdf(
            "https://example.test/not-really.pdf",
            FetchConfig(max_retries=0),
        )


def test_source_dispatch_uses_registry_classification(monkeypatch: Any) -> None:
    calls = []
    sentinel = FetchResult(
        body=b"x",
        fetch_method="test",
        status_code=200,
        final_url="https://example.test/",
        mime_type="text/plain",
        headers={},
    )

    monkeypatch.setattr(
        "scraper.pdf_fetcher.fetch_pdf",
        lambda url, config: calls.append(("pdf", url, config)) or sentinel,
    )
    monkeypatch.setattr(
        "scraper.playwright_fetcher.fetch_dynamic_html",
        lambda url, config, **kwargs: calls.append(
            ("dynamic", url, config, kwargs)
        )
        or sentinel,
    )
    monkeypatch.setattr(
        "scraper.html_fetcher.fetch_html",
        lambda url, config: calls.append(("static", url, config)) or sentinel,
    )

    assert fetch_source(FakeSource("https://example.test/file.pdf", True)) is sentinel
    assert fetch_source(FakeSource("https://example.test/app", True)) is sentinel
    assert fetch_source(FakeSource("https://example.test/page", False)) is sentinel
    assert [call[0] for call in calls] == ["pdf", "dynamic", "static"]


class FakeRoutedRequest:
    def __init__(
        self,
        url: str,
        *,
        method: str = "GET",
        resource_type: str = "xhr",
        navigation: bool = False,
    ) -> None:
        self.url = url
        self.method = method
        self.resource_type = resource_type
        self._navigation = navigation

    def is_navigation_request(self) -> bool:
        return self._navigation


class FakeRoute:
    def __init__(self, request: FakeRoutedRequest) -> None:
        self.request = request
        self.action = None

    def continue_(self) -> None:
        self.action = "continued"

    def abort(self) -> None:
        self.action = "aborted"


@pytest.mark.parametrize(
    ("url", "method", "resource_type", "navigation", "expected"),
    [
        ("https://api.example.test/v1/notices", "GET", "xhr", False, "continued"),
        ("https://api.example.test/v1/other", "GET", "xhr", False, "aborted"),
        ("https://api.example.test/v1/notices", "POST", "xhr", False, "aborted"),
        ("https://api.example.test/v1/notices", "GET", "document", True, "aborted"),
    ],
)
def test_dynamic_dependency_boundary_is_exact_read_only_and_non_navigation(
    url: str,
    method: str,
    resource_type: str,
    navigation: bool,
    expected: str,
) -> None:
    approved = frozenset({"https://api.example.test/v1/notices"})
    observed = set()
    blocked = set()
    route = FakeRoute(
        FakeRoutedRequest(
            url,
            method=method,
            resource_type=resource_type,
            navigation=navigation,
        )
    )

    _route_registered_origin(
        route,
        "https://example.test/app",
        blocked,
        approved,
        observed,
    )

    assert route.action == expected
    assert observed == (
        {"https://api.example.test/v1/notices"}
        if expected == "continued"
        else set()
    )


class FakePlaywrightTimeout(Exception):
    pass


class FakePlaywrightError(Exception):
    pass


class FakeDependencyResponse:
    def __init__(
        self,
        url: str,
        *,
        body: bytes,
        content_type: str = "application/json",
        method: str = "GET",
        resource_type: str = "fetch",
    ) -> None:
        self.request = SimpleNamespace(
            url=url, method=method, resource_type=resource_type
        )
        self.headers = {"content-type": content_type}
        self._body = body

    def body(self) -> bytes:
        return self._body


def test_dependency_response_capture_keeps_only_approved_json() -> None:
    approved = (
        "https://webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/programs",
    )
    listener, captured = _make_dependency_response_capture(approved, max_response_bytes=10_000)

    listener(
        FakeDependencyResponse(
            "https://webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/programs",
            body=b'{"program_types": []}',
        )
    )
    listener(
        FakeDependencyResponse(
            "https://webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/faculties",
            body=b'{"data": []}',
        )
    )
    listener(
        FakeDependencyResponse(
            "https://webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/programs",
            body=b'{"unapproved": true}',
            method="POST",
        )
    )

    assert captured == {
        "https://webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/programs": (
            '{"program_types": []}'
        )
    }


def test_dependency_response_capture_skips_oversized_and_non_utf8() -> None:
    listener, captured = _make_dependency_response_capture(
        ("https://api.example.test/v1/items",), max_response_bytes=4
    )
    listener(
        FakeDependencyResponse("https://api.example.test/v1/items", body=b"toolargebody")
    )
    listener(
        FakeDependencyResponse(
            "https://api.example.test/v1/items", body=b"\xff\xfe binary"
        )
    )
    assert captured == {}


class FakeNavigationResponse:
    status = 200
    request = SimpleNamespace(redirected_from=None)

    def all_headers(self) -> Dict[str, str]:
        return {
            "content-type": "text/html; charset=utf-8",
            "set-cookie": "excluded=yes",
        }


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test/app"
        self.closed = False
        self.timeouts = []
        self.event_handlers: Dict[str, list] = {}

    def on(self, event: str, handler: Any) -> None:
        self.event_handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, *args: Any) -> None:
        for handler in self.event_handlers.get(event, []):
            handler(*args)

    def set_default_timeout(self, timeout: int) -> None:
        self.default_timeout = timeout

    def goto(self, url: str, **kwargs: Any) -> FakeNavigationResponse:
        self.goto_call = (url, kwargs)
        return FakeNavigationResponse()

    def wait_for_selector(self, *args: Any, **kwargs: Any) -> None:
        self.selector_wait = (args, kwargs)

    def wait_for_load_state(self, *args: Any, **kwargs: Any) -> None:
        raise FakePlaywrightTimeout("long polling never became idle")

    def wait_for_timeout(self, timeout: int) -> None:
        self.timeouts.append(timeout)

    def content(self) -> str:
        return "<html><body>Rendered admission content</body></html>"

    def evaluate(self, script: str) -> List[str]:
        self.evaluate_script = script
        if "data-capture-shadow-root" in script:
            return 1  # type: ignore[return-value]
        return ["input:csrf_token"]

    def close(self) -> None:
        self.closed = True

    def is_closed(self) -> bool:
        return self.closed


class FakeBrowserContext:
    def __init__(self) -> None:
        self.page = FakePage()

    def new_page(self) -> FakePage:
        return self.page

    def route(self, pattern: str, handler: Any) -> None:
        self.route_call = (pattern, handler)

    def route_web_socket(self, pattern: str, handler: Any) -> None:
        self.web_socket_route_call = (pattern, handler)

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    version = "139.0-test"
    def __init__(self) -> None:
        self.context = FakeBrowserContext()

    def new_context(self, **kwargs: Any) -> FakeBrowserContext:
        self.context_options = kwargs
        return self.context

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self) -> None:
        self.browser = FakeBrowser()

    def launch(self, *, headless: bool) -> FakeBrowser:
        self.headless = headless
        return self.browser


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()


class FakePlaywrightManager:
    def __init__(self, playwright: FakePlaywright) -> None:
        self.playwright = playwright

    def __enter__(self) -> FakePlaywright:
        return self.playwright

    def __exit__(self, *args: Any) -> None:
        return None


def test_dynamic_fetch_captures_rendered_dom_with_bounded_idle_wait(
    monkeypatch: Any,
) -> None:
    playwright = FakePlaywright()
    monkeypatch.setattr(
        "scraper.playwright_fetcher._load_playwright",
        lambda: (
            lambda: FakePlaywrightManager(playwright),
            FakePlaywrightError,
            FakePlaywrightTimeout,
        ),
    )

    result = fetch_dynamic_html(
        "https://example.test/app",
        FetchConfig(
            max_retries=0,
            playwright_network_idle_timeout_ms=250,
            playwright_settle_ms=50,
        ),
    )

    page = playwright.chromium.browser.context.page
    assert result.body == b"<html><body>Rendered admission content</body></html>"
    assert result.rendered is True
    assert result.fetch_method == "playwright"
    assert result.status_code == 200
    assert result.final_url == "https://example.test/app"
    assert result.headers == {"content-type": "text/html; charset=utf-8"}
    assert page.timeouts == [50]
    assert page.closed is True
    assert result.browser_version == "139.0-test"
    assert result.redactions == ("input:csrf_token",)
    assert result.materialized_shadow_roots == 1
    browser = playwright.chromium.browser
    assert browser.context_options["service_workers"] == "block"

    class FakeWebSocketRoute:
        url = "wss://tracking.example/socket"

        def close(self, **kwargs: Any) -> None:
            self.close_options = kwargs

    pattern, handler = browser.context.web_socket_route_call
    web_socket = FakeWebSocketRoute()
    handler(web_socket)
    assert pattern == "**/*"
    assert web_socket.close_options["code"] == 1008


def test_dynamic_fetch_rejects_client_side_navigation_after_settle(
    monkeypatch: Any,
) -> None:
    playwright = FakePlaywright()
    page = playwright.chromium.browser.context.page

    def change_client_url(timeout: int) -> None:
        page.timeouts.append(timeout)
        page.url = "https://example.test/unregistered-client-route"

    page.wait_for_timeout = change_client_url  # type: ignore[method-assign]
    monkeypatch.setattr(
        "scraper.playwright_fetcher._load_playwright",
        lambda: (
            lambda: FakePlaywrightManager(playwright),
            FakePlaywrightError,
            FakePlaywrightTimeout,
        ),
    )

    with pytest.raises(FetchError, match="client-side navigation"):
        fetch_dynamic_html(
            "https://example.test/app",
            FetchConfig(max_retries=0, playwright_settle_ms=1),
        )


def test_html_extraction_is_lightweight_and_keeps_document_sections() -> None:
    pytest.importorskip("bs4")
    extracted = extract_html(
        """
        <html><head><title> DIU Admission </title><style>.x{}</style></head>
        <body><nav>Programs</nav><main><h1>Apply</h1>
        <table><tr><td>Deadline</td><td>August 30</td></tr></table>
        <script>privateCode()</script></main><footer>Official contact</footer></body>
        </html>
        """
    )

    assert extracted.title == "DIU Admission"
    assert extracted.text == (
        "Programs\nApply\nDeadline\nAugust 30\nOfficial contact"
    )
    assert extracted.extraction_method == "beautifulsoup_html_parser"


def test_pdf_extraction_gracefully_skips_unpinned_optional_dependency(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "scraper.extractor._load_pypdf", lambda strict_dependency: None
    )

    extracted = extract_pdf(b"%PDF-1.4\ncontent")

    assert extracted.text is None
    assert extracted.extraction_method == "none"
    assert "pypdf" in extracted.warnings[0]


def test_fetch_result_defers_pdf_extraction_by_default() -> None:
    result = FetchResult(
        body=b"%PDF-1.7\nraw bytes",
        fetch_method="requests_pdf",
        status_code=200,
        final_url="https://example.test/file.pdf",
        mime_type="application/pdf",
        headers={},
    )

    extracted = extract_fetch_result(result)

    assert extracted.text is None
    assert extracted.extraction_method == "none"
    assert "deferred" in extracted.warnings[0]


def test_pdf_parser_failure_does_not_block_raw_capture(monkeypatch: Any) -> None:
    def broken_reader(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise ValueError("damaged cross-reference table")

    monkeypatch.setattr(
        "scraper.extractor._load_pypdf",
        lambda strict_dependency: broken_reader,
    )

    extracted = extract_pdf(b"%PDF-1.4\nraw content")

    assert extracted.text is None
    assert extracted.extraction_method == "none"
    assert "raw bytes preserved" in extracted.warnings[0]


def test_pdf_without_embedded_text_is_not_ocrd(monkeypatch: Any) -> None:
    class PageWithoutText:
        def extract_text(self) -> str:
            return ""

    class ReaderWithoutText:
        metadata = None
        pages = [PageWithoutText()]

    monkeypatch.setattr(
        "scraper.extractor._load_pypdf",
        lambda strict_dependency: lambda *args, **kwargs: ReaderWithoutText(),
    )

    extracted = extract_pdf(b"%PDF-1.4\nraw content")

    assert extracted.text is None
    assert extracted.page_count == 1
    assert "OCR was not attempted" in extracted.warnings[0]


def test_fetch_result_selects_plain_text_without_cleaning() -> None:
    result = FetchResult(
        body="Line one\n  Line two".encode(),
        fetch_method="requests",
        status_code=200,
        final_url="https://example.test/data.txt",
        mime_type="text/plain",
        headers={},
    )

    extracted = extract_fetch_result(result)

    assert extracted.text == "Line one\n  Line two"
    assert extracted.extraction_method == "plain_text_decode"
