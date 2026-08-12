"""Unit tests for stable hashes, URLs, IDs, and filenames."""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from scraper.exceptions import InvalidURLError
from scraper.models import SourceRecord
from scraper.utils import (
    canonicalize_url,
    make_document_id,
    safe_filename,
    safe_identifier,
    sha256_bytes,
    sha256_text,
)


def test_sha256_hashes_exact_bytes_and_utf8_text() -> None:
    payload = "DIU admission — ঢাকা"

    assert sha256_text(payload) == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert sha256_bytes(payload.encode("utf-8")) == sha256_text(payload)
    assert sha256_text(payload + " ") != sha256_text(payload)


def test_canonicalize_url_follows_collection_protocol() -> None:
    value = (
        "HTTPS://Example.COM:443/a/../admission//"
        "?utm_source=test&b=2&a=1#section"
    )

    assert canonicalize_url(value) == "https://example.com/admission?a=1&b=2"
    assert canonicalize_url("https://example.com") == "https://example.com/"
    assert canonicalize_url("https://example.com/%7eapply") == (
        "https://example.com/~apply"
    )


@pytest.mark.parametrize(
    "url",
    ["", "ftp://example.com/file", "https:///missing-host", "https://u:p@example.com"],
)
def test_canonicalize_url_rejects_invalid_or_unsafe_urls(url: str) -> None:
    with pytest.raises(InvalidURLError):
        canonicalize_url(url)


def test_safe_names_cannot_escape_selected_directory() -> None:
    identifier = safe_identifier("../../DIU ADM 001\\capture")
    filename = safe_filename("../../Admission Checklist 2026.PDF")

    assert identifier == "diu-adm-001-capture"
    assert filename == "Admission-Checklist-2026.pdf"
    for result in (identifier, filename):
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result
        assert result not in {"", ".", ".."}


def test_document_id_is_stable_safe_and_uses_canonical_url() -> None:
    first = make_document_id(
        "DIU-ADM-001", "HTTPS://DAFFODILVARSITY.EDU.BD/admission/#top"
    )
    second = make_document_id(
        "DIU-ADM-001",
        "https://daffodilvarsity.edu.bd/admission?utm_campaign=test",
    )

    assert first == second
    assert re.fullmatch(r"diu-adm-001-[0-9a-f]{16}", first)
    assert first != make_document_id(
        "DIU-ADM-002", "https://daffodilvarsity.edu.bd/admission"
    )


def test_source_metadata_is_json_serializable() -> None:
    source = SourceRecord.from_mapping(
        {
            "source_id": "DIU-DOC-001",
            "url": "https://example.com/checklist.PDF?download=1",
            "page_title": "Checklist",
            "category": "documents",
            "program": "",
            "faculty": "",
            "priority": "high",
            "dynamic_page": "false",
            "date_sensitive": "true",
            "custom_column": "kept",
        }
    )

    metadata = source.to_metadata()
    assert source.is_pdf is True
    assert metadata["document_id"] == source.document_id
    assert json.loads(json.dumps(metadata))["extras"] == {"custom_column": "kept"}
