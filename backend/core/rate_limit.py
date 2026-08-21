"""Minimal production-only in-process rate limiter.

This protects a single free instance without adding a runtime dependency. A
managed multi-instance deployment should move the same policy to its edge or
shared store so limits are global.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from threading import Lock
from time import monotonic

from fastapi import Request

from backend.core.config import get_settings
from backend.core.errors import ApiError


_WINDOW_SECONDS = 60.0
_MAX_IDENTITIES = 10_000
_hits: "OrderedDict[str, deque[float]]" = OrderedDict()
_last_sweep = 0.0
_lock = Lock()


def _sweep_expired(now: float) -> None:
    """Bound identity state without scanning the map on every request."""

    global _last_sweep
    if now - _last_sweep < _WINDOW_SECONDS:
        return
    cutoff = now - _WINDOW_SECONDS
    expired = [
        identity
        for identity, bucket in _hits.items()
        if not bucket or bucket[-1] <= cutoff
    ]
    for identity in expired:
        _hits.pop(identity, None)
    _last_sweep = now


def enforce_chat_rate_limit(request: Request) -> None:
    """Allow development traffic freely and cap production chat abuse."""

    settings = get_settings()
    if settings.app_env.strip().lower() != "production":
        return
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    identity = request.client.host if request.client else "unknown"
    now = monotonic()
    with _lock:
        _sweep_expired(now)
        bucket = _hits.get(identity)
        if bucket is None:
            while len(_hits) >= _MAX_IDENTITIES:
                _hits.popitem(last=False)
            bucket = deque()
            _hits[identity] = bucket
        else:
            _hits.move_to_end(identity)
        while bucket and bucket[0] <= now - _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= limit:
            raise ApiError(
                status_code=429,
                code="rate_limited",
                message="Too many chat requests. Please try again shortly.",
                details=[{"field": "retry_after", "message": "60 seconds"}],
            )
        bucket.append(now)


__all__ = ["enforce_chat_rate_limit"]
