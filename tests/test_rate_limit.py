"""Production chat rate-limit regression tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request

import backend.core.rate_limit as rate_limit
from backend.core.errors import ApiError


def _request(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": [],
            "client": (host, 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


@pytest.fixture(autouse=True)
def _clear_rate_limit_state(monkeypatch):
    rate_limit._hits.clear()
    monkeypatch.setattr(rate_limit, "_last_sweep", 0.0)
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: SimpleNamespace(app_env="production", rate_limit_per_minute=2),
    )


def test_rate_limit_blocks_only_after_configured_capacity(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "monotonic", lambda: 10.0)
    request = _request("192.0.2.1")

    rate_limit.enforce_chat_rate_limit(request)
    rate_limit.enforce_chat_rate_limit(request)

    with pytest.raises(ApiError) as error:
        rate_limit.enforce_chat_rate_limit(request)
    assert error.value.status_code == 429


def test_rate_limit_identity_map_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "_MAX_IDENTITIES", 3)
    monkeypatch.setattr(rate_limit, "monotonic", lambda: 10.0)

    for index in range(5):
        rate_limit.enforce_chat_rate_limit(_request(f"192.0.2.{index}"))

    assert len(rate_limit._hits) == 3
    assert list(rate_limit._hits) == ["192.0.2.2", "192.0.2.3", "192.0.2.4"]


def test_rate_limit_sweep_removes_expired_identities(monkeypatch) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr(rate_limit, "monotonic", lambda: now["value"])
    rate_limit.enforce_chat_rate_limit(_request("192.0.2.1"))

    now["value"] = 71.0
    rate_limit.enforce_chat_rate_limit(_request("192.0.2.2"))

    assert list(rate_limit._hits) == ["192.0.2.2"]
