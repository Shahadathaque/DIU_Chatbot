"""Small process-local TTL cache used for immutable catalog endpoints.

The cache is deliberately bounded to a handful of static responses. It is a
performance optimization, not a source of truth: restarting a process simply
reloads the authoritative cleaned snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Generic, Optional, TypeVar


T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """Thread-safe single-value cache with monotonic-clock expiry."""

    def __init__(self, ttl_seconds: float = 86_400.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._entry: Optional[_Entry[T]] = None
        self._lock = Lock()

    def get(self) -> Optional[T]:
        now = monotonic()
        with self._lock:
            entry = self._entry
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entry = None
                return None
            return entry.value

    def set(self, value: T) -> T:
        with self._lock:
            self._entry = _Entry(value=value, expires_at=monotonic() + self.ttl_seconds)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entry = None


__all__ = ["TTLCache"]
