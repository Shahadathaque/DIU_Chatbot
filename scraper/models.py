"""Core data models for the controlled source registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Mapping

from scraper.exceptions import RegistryValidationError
from scraper.utils import canonicalize_url, is_pdf_url, make_document_id


REQUIRED_SOURCE_FIELDS = (
    "source_id",
    "url",
    "page_title",
    "category",
    "priority",
    "dynamic_page",
    "date_sensitive",
)

SOURCE_FIELDS = (
    "source_id",
    "url",
    "page_title",
    "category",
    "program",
    "faculty",
    "priority",
    "dynamic_page",
    "date_sensitive",
    "scrape_status",
    "last_checked",
    "notes",
)

SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


def parse_registry_bool(
    value: object,
    *,
    field_name: str,
    row_number: int | None = None,
) -> bool:
    """Parse the registry's explicit ``true``/``false`` boolean format."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise RegistryValidationError(
        "must be either 'true' or 'false'",
        row_number=row_number,
        field=field_name,
    )


def _required_text(
    row: Mapping[str, object],
    field_name: str,
    row_number: int | None,
) -> str:
    value = row.get(field_name)
    if value is None or not str(value).strip():
        raise RegistryValidationError(
            "required value is missing",
            row_number=row_number,
            field=field_name,
        )
    return str(value).strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class SourceRecord:
    """A validated registry source with all known and extra CSV metadata."""

    source_id: str
    url: str
    page_title: str
    category: str
    priority: str
    dynamic_page: bool
    date_sensitive: bool
    program: str | None = None
    faculty: str | None = None
    scrape_status: str | None = None
    last_checked: str | None = None
    notes: str | None = None
    extras: dict[str, str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("source_id", "url", "page_title", "category", "priority"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise RegistryValidationError(
                    "required value is missing", field=field_name
                )
            setattr(self, field_name, value.strip())

        if not SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise RegistryValidationError(
                "must contain only letters, digits, and single hyphen-separated segments",
                field="source_id",
            )

        self.dynamic_page = parse_registry_bool(
            self.dynamic_page, field_name="dynamic_page"
        )
        self.date_sensitive = parse_registry_bool(
            self.date_sensitive, field_name="date_sensitive"
        )
        # Validate without replacing the provenance URL supplied by the registry.
        canonicalize_url(self.url)

        for field_name in (
            "program",
            "faculty",
            "scrape_status",
            "last_checked",
            "notes",
        ):
            setattr(self, field_name, _optional_text(getattr(self, field_name)))
        self.extras = {
            str(key): _optional_text(value) for key, value in dict(self.extras).items()
        }

    @classmethod
    def from_mapping(
        cls,
        row: Mapping[str, Any],
        *,
        row_number: int | None = None,
    ) -> "SourceRecord":
        """Build a source from one CSV-like mapping and retain unknown columns."""

        if not isinstance(row, Mapping):
            raise TypeError("row must be a mapping")
        known = set(SOURCE_FIELDS)
        extras = {
            str(key): _optional_text(value)
            for key, value in row.items()
            if key is not None and key not in known
        }
        try:
            return cls(
                source_id=_required_text(row, "source_id", row_number),
                url=_required_text(row, "url", row_number),
                page_title=_required_text(row, "page_title", row_number),
                category=_required_text(row, "category", row_number),
                program=_optional_text(row.get("program")),
                faculty=_optional_text(row.get("faculty")),
                priority=_required_text(row, "priority", row_number),
                dynamic_page=parse_registry_bool(
                    row.get("dynamic_page"),
                    field_name="dynamic_page",
                    row_number=row_number,
                ),
                date_sensitive=parse_registry_bool(
                    row.get("date_sensitive"),
                    field_name="date_sensitive",
                    row_number=row_number,
                ),
                scrape_status=_optional_text(row.get("scrape_status")),
                last_checked=_optional_text(row.get("last_checked")),
                notes=_optional_text(row.get("notes")),
                extras=extras,
            )
        except RegistryValidationError as error:
            # URL validation occurs in __post_init__, where the source row is not
            # otherwise available. Add the row number while preserving the type.
            if row_number is not None and error.row_number is None:
                raise type(error)(
                    error.message,
                    row_number=row_number,
                    field=error.field,
                ) from error
            raise

    @property
    def canonical_url(self) -> str:
        """Canonical URL used for deduplication and stable identifiers."""

        return canonicalize_url(self.url)

    @property
    def document_id(self) -> str:
        """Stable ID independent of retrieval time and response content."""

        return make_document_id(self.source_id, self.canonical_url)

    @property
    def is_pdf(self) -> bool:
        """Whether the registered URL path has a PDF suffix."""

        return is_pdf_url(self.url)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation without computed fields."""

        return asdict(self)

    def to_metadata(self) -> dict[str, Any]:
        """Return serializable metadata including canonical identity fields."""

        metadata = self.to_dict()
        metadata["canonical_url"] = self.canonical_url
        metadata["document_id"] = self.document_id
        metadata["is_pdf"] = self.is_pdf
        return metadata
