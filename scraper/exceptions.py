"""Exceptions raised by the controlled DIU scraper.

Keeping scraper failures in a small hierarchy lets the command-line runner report a
concise error while tests and callers can still distinguish invalid registry data
from network/fetching failures.
"""

from __future__ import annotations


class ScraperError(Exception):
    """Base class for expected scraper errors."""


class RegistryError(ScraperError):
    """Base class for source-registry errors."""


class RegistryValidationError(RegistryError, ValueError):
    """Raised when a registry row or schema is invalid."""

    def __init__(
        self,
        message: str,
        *,
        row_number: int | None = None,
        field: str | None = None,
    ) -> None:
        self.message = message
        self.row_number = row_number
        self.field = field

        context: list[str] = []
        if row_number is not None:
            context.append(f"row {row_number}")
        if field is not None:
            context.append(f"field {field!r}")
        prefix = f"Registry {' / '.join(context)}: " if context else "Registry: "
        super().__init__(prefix + message)


class DuplicateSourceURLError(RegistryValidationError):
    """Raised when two registry rows resolve to the same canonical URL."""


class DuplicateSourceIDError(RegistryValidationError):
    """Raised when a source identifier is repeated."""


class InvalidURLError(RegistryValidationError):
    """Raised when a source URL is not a public HTTP(S) URL."""


class FetchError(ScraperError):
    """Raised when a registered source cannot be fetched."""

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        method: str | None = None,
        status_code: int | None = None,
        cause: BaseException | None = None,
        final_url: str | None = None,
        redirect_chain: tuple[str, ...] = (),
        attempts: int = 1,
    ) -> None:
        self.message = message
        self.url = url
        self.method = method
        self.status_code = status_code
        self.cause = cause
        self.final_url = final_url
        self.redirect_chain = redirect_chain
        self.attempts = attempts
        super().__init__(message)


class FetchDependencyError(FetchError):
    """Raised when an optional fetcher runtime dependency is unavailable."""


class ExtractionError(ScraperError):
    """Raised when fetched content cannot be represented as a raw record."""


class StorageError(ScraperError):
    """Raised when immutable raw data cannot be stored safely."""
