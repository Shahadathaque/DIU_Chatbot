"""Tests for sequential, per-host request pacing."""

from scraper.rate_limit import HostRateLimiter


def test_rate_limiter_does_not_delay_first_request() -> None:
    limiter = HostRateLimiter(2.0, 5.0, seed=1)

    assert limiter.wait("https://example.com/one") == 0.0


def test_rate_limiter_tracks_hosts_independently(monkeypatch) -> None:
    clock = iter([10.0, 10.5])
    sleeps = []
    monkeypatch.setattr("scraper.rate_limit.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("scraper.rate_limit.time.sleep", sleeps.append)
    limiter = HostRateLimiter(2.0, 2.0, seed=1)

    limiter.mark("https://example.com/one")
    assert limiter.wait("https://other.example/two") == 0.0
    assert limiter.wait("https://example.com/three") == 1.5
    assert sleeps == [1.5]
