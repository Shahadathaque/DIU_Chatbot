"""Controlled, registry-driven DIU admission source collection."""

from scraper.exceptions import (
    DuplicateSourceIDError,
    DuplicateSourceURLError,
    ExtractionError,
    FetchDependencyError,
    FetchError,
    InvalidURLError,
    RegistryError,
    RegistryValidationError,
    ScraperError,
    StorageError,
)
from scraper.models import SourceRecord
from scraper.registry import DEFAULT_REGISTRY_PATH, filter_sources, load_registry
from scraper.utils import (
    canonicalize_url,
    make_document_id,
    safe_filename,
    safe_identifier,
    sha256_bytes,
    sha256_text,
)

__all__ = [
    "DEFAULT_REGISTRY_PATH",
    "DuplicateSourceIDError",
    "DuplicateSourceURLError",
    "ExtractionError",
    "FetchDependencyError",
    "FetchError",
    "InvalidURLError",
    "RegistryError",
    "RegistryValidationError",
    "ScraperError",
    "StorageError",
    "SourceRecord",
    "canonicalize_url",
    "filter_sources",
    "load_registry",
    "make_document_id",
    "safe_filename",
    "safe_identifier",
    "sha256_bytes",
    "sha256_text",
]
