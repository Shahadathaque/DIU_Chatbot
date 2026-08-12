"""Loading, validation, deduplication, and filtering for source_registry.csv."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from scraper.exceptions import (
    DuplicateSourceIDError,
    DuplicateSourceURLError,
    RegistryError,
    RegistryValidationError,
)
from scraper.models import REQUIRED_SOURCE_FIELDS, SourceRecord
from scraper.utils import canonicalize_url


DEFAULT_REGISTRY_PATH = Path("data/source_registry.csv")


def _validate_headers(fieldnames: list[str] | None) -> list[str]:
    if fieldnames is None:
        raise RegistryValidationError("CSV file has no header row")
    normalized = [field.strip() for field in fieldnames]
    if any(not field for field in normalized):
        raise RegistryValidationError("CSV contains an empty column name")
    duplicates = sorted({name for name in normalized if normalized.count(name) > 1})
    if duplicates:
        raise RegistryValidationError(
            f"CSV contains duplicate columns: {', '.join(duplicates)}"
        )
    missing = [field for field in REQUIRED_SOURCE_FIELDS if field not in normalized]
    if missing:
        raise RegistryValidationError(
            f"CSV is missing required columns: {', '.join(missing)}"
        )
    return normalized


def validate_unique_sources(sources: Sequence[SourceRecord]) -> None:
    """Reject repeated IDs and URLs after protocol-level canonicalization."""

    ids: dict[str, tuple[int, SourceRecord]] = {}
    urls: dict[str, tuple[int, SourceRecord]] = {}
    for index, source in enumerate(sources, start=2):
        id_key = source.source_id.casefold()
        if id_key in ids:
            first_row, first_source = ids[id_key]
            raise DuplicateSourceIDError(
                f"source ID {source.source_id!r} duplicates row {first_row} "
                f"({first_source.source_id!r})",
                row_number=index,
                field="source_id",
            )
        ids[id_key] = (index, source)

        canonical_url = source.canonical_url
        if canonical_url in urls:
            first_row, first_source = urls[canonical_url]
            raise DuplicateSourceURLError(
                f"canonical URL {canonical_url!r} duplicates row {first_row} "
                f"({first_source.source_id})",
                row_number=index,
                field="url",
            )
        urls[canonical_url] = (index, source)


def load_registry(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    source_id: str | Iterable[str] | None = None,
    category: str | Iterable[str] | None = None,
    priority: str | Iterable[str] | None = None,
    url: str | Iterable[str] | None = None,
    limit: int | None = None,
) -> list[SourceRecord]:
    """Read and validate the complete registry, then apply optional filters."""

    registry_path = Path(path)
    try:
        handle = registry_path.open("r", encoding="utf-8-sig", newline="")
    except OSError as error:
        raise RegistryError(f"Could not read registry {registry_path}: {error}") from error

    with handle:
        reader = csv.DictReader(handle)
        normalized_headers = _validate_headers(reader.fieldnames)
        # DictReader retains its original header strings as mapping keys. Trim them
        # after checking so harmless surrounding whitespace does not lose values.
        original_headers = list(reader.fieldnames or [])
        sources: list[SourceRecord] = []
        for row_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise RegistryValidationError(
                    "row has more values than the CSV header",
                    row_number=row_number,
                )
            row = {
                normalized: raw_row.get(original)
                for original, normalized in zip(original_headers, normalized_headers)
            }
            if not any(value is not None and str(value).strip() for value in row.values()):
                continue
            sources.append(SourceRecord.from_mapping(row, row_number=row_number))

    validate_unique_sources(sources)
    return filter_sources(
        sources,
        source_id=source_id,
        category=category,
        priority=priority,
        url=url,
        limit=limit,
    )


def _normalized_filter_values(value: str | Iterable[str] | None) -> set[str] | None:
    if value is None:
        return None
    values = [value] if isinstance(value, str) else list(value)
    return {str(item).strip().casefold() for item in values}


def _url_filter_values(value: str | Iterable[str] | None) -> set[str] | None:
    if value is None:
        return None
    values = [value] if isinstance(value, str) else list(value)
    return {canonicalize_url(str(item)) for item in values}


def filter_sources(
    sources: Iterable[SourceRecord],
    *,
    source_id: str | Iterable[str] | None = None,
    category: str | Iterable[str] | None = None,
    priority: str | Iterable[str] | None = None,
    url: str | Iterable[str] | None = None,
    limit: int | None = None,
) -> list[SourceRecord]:
    """Filter sources deterministically while preserving registry order."""

    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
        raise TypeError("limit must be an integer or None")
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    if limit == 0:
        return []

    source_ids = _normalized_filter_values(source_id)
    categories = _normalized_filter_values(category)
    priorities = _normalized_filter_values(priority)
    urls = _url_filter_values(url)

    selected: list[SourceRecord] = []
    for source in sources:
        if source_ids is not None and source.source_id.casefold() not in source_ids:
            continue
        if categories is not None and source.category.casefold() not in categories:
            continue
        if priorities is not None and source.priority.casefold() not in priorities:
            continue
        if urls is not None and source.canonical_url not in urls:
            continue
        selected.append(source)
        if limit is not None and len(selected) >= limit:
            break

    return selected


# Concise aliases for existing or exploratory callers.
read_registry = load_registry
filter_registry = filter_sources
