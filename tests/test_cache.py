"""Tests for the bounded static-response TTL cache."""

from __future__ import annotations

from backend.core.cache import TTLCache


def test_ttl_cache_returns_and_clears_values(monkeypatch) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr("backend.core.cache.monotonic", lambda: now["value"])
    cache = TTLCache[str](ttl_seconds=5)

    assert cache.get() is None
    cache.set("catalog")
    assert cache.get() == "catalog"
    now["value"] = 15.0
    assert cache.get() is None


def test_ttl_cache_can_be_explicitly_cleared() -> None:
    cache = TTLCache[str]()
    cache.set("catalog")
    cache.clear()
    assert cache.get() is None
