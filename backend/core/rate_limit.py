"""Minimal production-only in-process rate limiter.

This protects a single free instance without adding a runtime dependency. A
managed multi-instance deployment should move the same policy to its edge or
shared store so limits are global.
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import Request

from backend.core.config import get_settings
from backend.core.errors import ApiError


_WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


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
        bucket = _hits[identity]
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
