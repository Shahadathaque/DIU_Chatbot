"""Tests for bounded robots guidance review and per-origin caching."""

import pytest

from scraper.policy import ROBOTS_MAX_BYTES, RobotsChecker


class FakeResponse:
    status_code = 200
    body = b"User-agent: *\nDisallow: /private/\nAllow: /admission\n"
    encoding = "utf-8"
    headers = {"Content-Length": str(len(body))}

    @property
    def content(self):
        raise AssertionError("robots review must never buffer response.content")

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]

    def close(self) -> None:
        return None


def test_robots_checker_caches_origin_and_applies_rules(monkeypatch) -> None:
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    checker = RobotsChecker(user_agent="ResearchCollector", timeout_seconds=5)
    monkeypatch.setattr(checker._session, "get", fake_get)

    allowed = checker.review("https://example.com/admission")
    disallowed = checker.review("https://example.com/private/data")
    cached = checker.review("https://example.com/admission")

    assert allowed.allowed is True
    assert disallowed.allowed is False
    assert cached is allowed
    assert len(calls) == 1
    assert len(checker.reviews) == 2
    assert allowed.content_hash is not None


def test_robots_uses_collector_token_and_fails_closed_on_unavailable(monkeypatch) -> None:
    class CollectorRules(FakeResponse):
        body = (
            b"User-agent: DIU-Admission-Research-Collector\nDisallow: /private\n"
            b"User-agent: *\nAllow: /\n"
        )
        headers = {"Content-Length": str(len(body))}

    checker = RobotsChecker(
        user_agent="DIU-Admission-Research-Collector", timeout_seconds=5
    )
    monkeypatch.setattr(checker._session, "get", lambda *args, **kwargs: CollectorRules())
    assert checker.review("https://example.com/private").allowed is False

    class RateLimited(FakeResponse):
        status_code = 429

    unavailable = RobotsChecker(user_agent="Collector", timeout_seconds=5)
    monkeypatch.setattr(unavailable._session, "get", lambda *args, **kwargs: RateLimited())
    review = unavailable.review("https://rate.example/admission")
    assert review.allowed is False
    assert review.outcome == "unavailable"


@pytest.mark.parametrize("headers", [{}, {"Content-Length": "1"}])
def test_robots_stream_limit_fails_closed_with_untrusted_length(
    monkeypatch, headers
) -> None:
    response_headers = headers

    class OversizedResponse(FakeResponse):
        headers = response_headers

        def __init__(self) -> None:
            self.closed = False
            self.chunks_requested = 0

        def iter_content(self, chunk_size: int):
            assert chunk_size <= ROBOTS_MAX_BYTES
            self.chunks_requested += 1
            yield b"x" * ROBOTS_MAX_BYTES
            self.chunks_requested += 1
            yield b"x"
            raise AssertionError("streaming must stop immediately above the limit")

        def close(self) -> None:
            self.closed = True

    response = OversizedResponse()
    checker = RobotsChecker(user_agent="Collector", timeout_seconds=5)
    monkeypatch.setattr(checker._session, "get", lambda *args, **kwargs: response)

    review = checker.review("https://oversized.example/admission")

    assert review.allowed is False
    assert review.outcome == "too_large"
    assert review.content_hash is None
    assert review.message == "robots.txt exceeds the 1 MiB review limit"
    assert response.chunks_requested == 2
    assert response.closed is True
