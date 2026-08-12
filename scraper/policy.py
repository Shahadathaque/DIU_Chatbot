"""Small, cached robots.txt review used before controlled collection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from scraper.utils import sha256_bytes


ROBOTS_MAX_BYTES = 1024 * 1024
_ROBOTS_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class RobotsReview:
    """Recorded result of checking one origin's published robots guidance."""

    origin: str
    target_url: str
    robots_url: str
    checked_at: str
    status_code: Optional[int]
    allowed: bool
    outcome: str
    content_hash: Optional[str] = None
    message: Optional[str] = None
    final_robots_url: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _OriginPolicy:
    origin: str
    robots_url: str
    checked_at: str
    status_code: Optional[int]
    outcome: str
    content_hash: Optional[str]
    message: Optional[str]
    parser: Optional[RobotFileParser]


class RobotsChecker:
    """Review robots guidance once per origin and cache it for the run."""

    def __init__(self, *, user_agent: str, timeout_seconds: float) -> None:
        if not user_agent.strip():
            raise ValueError("robots user agent must not be blank")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self._reviews: Dict[str, RobotsReview] = {}
        self._origins: Dict[str, _OriginPolicy] = {}
        self._session = requests.Session()
        self.before_request: Optional[Callable[[str], None]] = None
        self.after_request: Optional[Callable[[str], None]] = None

    @property
    def reviews(self) -> Dict[str, RobotsReview]:
        return dict(self._reviews)

    def review(self, url: str) -> RobotsReview:
        cached_review = self._reviews.get(url)
        if cached_review is not None:
            return cached_review

        split = urlsplit(url)
        origin = f"{split.scheme.lower()}://{split.netloc.lower()}"
        policy = self._origins.get(origin)
        if policy is None:
            policy = self._fetch_origin_policy(origin)
            self._origins[origin] = policy

        allowed = (
            policy.parser.can_fetch(self.user_agent, url)
            if policy.parser is not None
            else policy.outcome == "not_published"
        )
        outcome = (
            "allowed" if allowed else "disallowed"
        ) if policy.parser is not None else policy.outcome
        review = RobotsReview(
            origin=policy.origin,
            target_url=url,
            robots_url=policy.robots_url,
            checked_at=policy.checked_at,
            status_code=policy.status_code,
            allowed=allowed,
            outcome=outcome,
            content_hash=policy.content_hash,
            message=policy.message,
            final_robots_url=policy.robots_url,
        )
        self._reviews[url] = review
        return review

    def _fetch_origin_policy(self, origin: str) -> _OriginPolicy:
        robots_url = f"{origin}/robots.txt"
        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        response = None
        attempted = False
        try:
            if self.before_request is not None:
                self.before_request(robots_url)
            attempted = True
            response = self._session.get(
                robots_url,
                headers={"User-Agent": self.user_agent, "Accept": "text/plain,*/*;q=0.1"},
                timeout=self.timeout_seconds,
                allow_redirects=False,
                stream=True,
            )
            status = response.status_code
            content = _read_bounded_content(response, ROBOTS_MAX_BYTES)
            if content is None:
                return _OriginPolicy(
                    origin=origin,
                    robots_url=robots_url,
                    checked_at=checked_at,
                    status_code=status,
                    outcome="too_large",
                    content_hash=None,
                    message="robots.txt exceeds the 1 MiB review limit",
                    parser=None,
                )
            if status == 404:
                return _OriginPolicy(
                    origin=origin,
                    robots_url=robots_url,
                    checked_at=checked_at,
                    status_code=status,
                    outcome="not_published",
                    content_hash=sha256_bytes(content),
                    message=None,
                    parser=None,
                )
            if 200 <= status < 300:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                text = content.decode(response.encoding or "utf-8", errors="replace")
                parser.parse(text.splitlines())
                return _OriginPolicy(
                    origin=origin,
                    robots_url=robots_url,
                    checked_at=checked_at,
                    status_code=status,
                    outcome="published",
                    content_hash=sha256_bytes(content),
                    message=None,
                    parser=parser,
                )
            return _OriginPolicy(
                origin=origin,
                robots_url=robots_url,
                checked_at=checked_at,
                status_code=status,
                outcome="unavailable",
                content_hash=sha256_bytes(content),
                message=f"robots.txt returned HTTP {status}; no rule was inferred",
                parser=None,
            )
        except requests.RequestException as exc:
            return _OriginPolicy(
                origin=origin,
                robots_url=robots_url,
                checked_at=checked_at,
                status_code=None,
                outcome="unavailable",
                content_hash=None,
                message=f"{type(exc).__name__}: {exc}",
                parser=None,
            )
        finally:
            if response is not None:
                response.close()
            if attempted and self.after_request is not None:
                self.after_request(robots_url)

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self._session.close()


def _read_bounded_content(
    response: requests.Response, max_bytes: int
) -> Optional[bytes]:
    """Stream a response up to ``max_bytes`` without buffering excess data."""

    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                return None
        except (TypeError, ValueError):
            # A missing or malformed declaration cannot be trusted; the streamed
            # byte count below remains authoritative.
            pass

    chunks = []
    received = 0
    for chunk in response.iter_content(chunk_size=_ROBOTS_CHUNK_BYTES):
        if not chunk:
            continue
        received += len(chunk)
        if received > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)
