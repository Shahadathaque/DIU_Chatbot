"""Sequential, per-host request pacing for ethical collection."""

from __future__ import annotations

import random
import math
import time
from typing import Dict
from urllib.parse import urlsplit


class HostRateLimiter:
    """Apply deterministic randomized delays between requests to one host."""

    def __init__(self, minimum_seconds: float, maximum_seconds: float, seed: int) -> None:
        if (
            not math.isfinite(minimum_seconds)
            or not math.isfinite(maximum_seconds)
            or minimum_seconds < 0
            or maximum_seconds < minimum_seconds
        ):
            raise ValueError("delay must satisfy 0 <= minimum <= maximum")
        self.minimum_seconds = minimum_seconds
        self.maximum_seconds = maximum_seconds
        self.seed = seed
        self._random = random.Random(seed)
        self._last_request: Dict[str, float] = {}

    def wait(self, url: str) -> float:
        """Sleep as needed before the next request and return seconds slept."""

        host = (urlsplit(url).hostname or "").lower()
        previous = self._last_request.get(host)
        if previous is None:
            return 0.0
        target_delay = self._random.uniform(
            self.minimum_seconds, self.maximum_seconds
        )
        elapsed = time.monotonic() - previous
        remaining = max(0.0, target_delay - elapsed)
        if remaining:
            time.sleep(remaining)
        return remaining

    def mark(self, url: str) -> None:
        """Record that a request to the URL's host has completed."""

        host = (urlsplit(url).hostname or "").lower()
        self._last_request[host] = time.monotonic()
