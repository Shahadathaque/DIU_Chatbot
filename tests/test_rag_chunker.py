from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag.chunker import chunk_record, load_cleaned_records
from rag.config import RagSettings
from tests.rag_helpers import cleaned_record, sha256_text, write_cleaned_dataset


def _settings() -> RagSettings:
    return RagSettings(
        _env_file=None,
        rag_chunk_size=300,
        rag_chunk_overlap=30,
        rag_min_chunk_size=20,
    )


def _structured_record():
    content = (
        "Admission Documents\n\n"
        "Applicants must submit verified academic records before admission. "
        "The originals are checked at the admission office.\n\n"
        "Required Checklist\n"
        "1. Original SSC certificate and transcript for verification.\n"
        "2. Original HSC certificate and transcript for verification.\n"
        "3. Passport-size photographs and identity document copies.\n\n"
        "Application Notes\n"
        "Online applicants upload education-board copies before visiting campus."
    )
    tables = [
        {
            "headers": ["Program", "Total Tuition", "Duration"],
            "rows": [
                ["CSE", "1,020,450 BDT", "4 Years"],
                ["BBA", "789,000 BDT", "4 Years"],
            ],
            "extraction_method": "fixture",
            "source_locator": "html-table-1",
            "page_number": None,
        }
    ]
    return cleaned_record(
        content=content,
        category="tuition_and_fees",
        faculty="Faculty of Science and Information Technology",
        quality_flags=["verified", "table_preserved", "verified"],
        tables=tables,
    )


def test_structure_aware_text_and_table_rows_are_atomic() -> None:
    chunks = chunk_record(_structured_record(), settings=_settings())
    text_chunks = [chunk for chunk in chunks if chunk.content_type == "text"]
    table_chunks = [chunk for chunk in chunks if chunk.content_type == "table"]

    assert text_chunks
    assert all(len(chunk.content) <= 300 for chunk in text_chunks)
    checklist = next(chunk for chunk in text_chunks if "Original SSC" in chunk.content)
    assert "Required Checklist" in checklist.content
    assert "Original HSC certificate and transcript" in checklist.content
    assert "Passport-size photographs and identity document copies" in checklist.content

    assert len(table_chunks) == 2
    cse = next(chunk for chunk in table_chunks if chunk.program == "CSE")
    bba = next(chunk for chunk in table_chunks if chunk.program == "BBA")
    assert "Program | Total Tuition | Duration" in cse.content
    assert "CSE | 1,020,450 BDT | 4 Years" in cse.content
    assert "BBA |" not in cse.content
    assert "BBA | 789,000 BDT | 4 Years" in bba.content
    assert "CSE |" not in bba.content


def test_chunk_metadata_source_url_and_hashes_are_preserved() -> None:
    record = _structured_record()
    chunk = next(
        item
        for item in chunk_record(record, settings=_settings())
        if item.content_type == "table" and item.program == "CSE"
    )

    assert chunk.document_id == record["document_id"]
    assert chunk.source_id == record["source_id"]
    assert chunk.source_url == record["source_url"]
    assert chunk.title == record["title"]
    assert chunk.category == record["category"]
    assert chunk.faculty == record["faculty"]
    assert chunk.source_content_type == "html"
    assert chunk.currency_status == "current_date_sensitive"
    assert chunk.date_sensitive is True
    assert chunk.manual_review is False
    assert chunk.retrieved_at == record["retrieved_at"]
    assert chunk.document_hash == record["cleaned_content_hash"]
    assert chunk.source_hash == record["raw_content_hash"]
    assert chunk.content_hash == sha256_text(chunk.content)
    assert chunk.source_locator == "html-table-1-part-1"
    assert chunk.quality_flags == ("table_preserved", "verified")


def test_program_catalog_chunk_retains_individual_url_and_metadata() -> None:
    record = cleaned_record(
        source_id="DIU-PROG-001",
        document_id="diu-prog-001",
        category="undergraduate_programs",
        title="Programs",
        content="Official program catalog.",
        tables=[
            {
                "headers": [
                    "Full Program Name",
                    "Short Tag / Initials",
                    "Program Level",
                    "Faculty",
                    "Department",
                    "Duration",
                    "Program Page",
                ],
                "rows": [
                    [
                        "Bachelor of Business Administration (BBA)",
                        "BBA",
                        "Undergraduate",
                        "Business & Entrepreneurship",
                        "Business Administration",
                        "4 Years",
                        "https://daffodilvarsity.edu.bd/department/bba/program/"
                        "bachelor-of-business-administration",
                    ]
                ],
                "extraction_method": "official_programs_api",
                "source_locator": "official-programs-catalog",
            }
        ],
    )

    chunk = next(item for item in chunk_record(record, settings=_settings()) if item.content_type == "table")

    assert chunk.program == "Bachelor of Business Administration (BBA)"
    assert chunk.faculty == "Business & Entrepreneurship"
    assert "Business Administration | 4 Years" in chunk.content
    assert (
        "https://daffodilvarsity.edu.bd/department/bba/program/"
        "bachelor-of-business-administration" in chunk.content
    )


def test_program_catalog_optional_metadata_preserves_existing_chunk_identity() -> None:
    base = cleaned_record(
        source_id="DIU-PROG-001",
        document_id="diu-prog-001",
        category="undergraduate_programs",
        title="Programs",
        content="Official program catalog.",
    )
    legacy = dict(base)
    legacy["tables"] = [
        {
            "headers": [
                "Full Program Name",
                "Short Tag / Initials",
                "Program Level",
                "Faculty",
            ],
            "rows": [
                [
                    "BBA in Finance & Banking",
                    "FINANCE",
                    "Undergraduate",
                    "Business & Entrepreneurship",
                ]
            ],
            "extraction_method": "official_programs_api",
            "source_locator": "official-programs-catalog",
        }
    ]
    enriched = dict(base)
    enriched["tables"] = [
        {
            **legacy["tables"][0],
            "headers": [
                *legacy["tables"][0]["headers"],
                "Department",
                "Duration",
                "Program Page",
            ],
            "rows": [
                [
                    *legacy["tables"][0]["rows"][0],
                    "Finance & Banking",
                    "4 Years",
                    "https://daffodilvarsity.edu.bd/department/finance/program/"
                    "finance-and-banking",
                ]
            ],
        }
    ]

    legacy_chunk = next(
        item for item in chunk_record(legacy, settings=_settings()) if item.content_type == "table"
    )
    enriched_chunk = next(
        item for item in chunk_record(enriched, settings=_settings()) if item.content_type == "table"
    )

    assert enriched_chunk.chunk_id == legacy_chunk.chunk_id
    assert enriched_chunk.content_hash != legacy_chunk.content_hash


def test_chunk_ids_are_stable_but_change_with_content() -> None:
    record = _structured_record()
    first = chunk_record(record, settings=_settings())
    second = chunk_record(record, settings=_settings())
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]

    changed = dict(record)
    changed["cleaned_content"] = record["cleaned_content"].replace(
        "education-board copies", "official education-board copies"
    )
    changed["cleaned_content_hash"] = sha256_text(changed["cleaned_content"])
    updated = chunk_record(changed, settings=_settings())

    assert [chunk.chunk_id for chunk in first if chunk.content_type == "table"] == [
        chunk.chunk_id for chunk in updated if chunk.content_type == "table"
    ]
    assert [chunk.chunk_id for chunk in first if chunk.content_type == "text"] != [
        chunk.chunk_id for chunk in updated if chunk.content_type == "text"
    ]


def test_manifest_controls_loading_and_detects_record_tampering(tmp_path: Path) -> None:
    root = write_cleaned_dataset(tmp_path / "cleaned", [_structured_record()])
    unlisted = root / "records" / "stale.json"
    unlisted.write_text("{}", encoding="utf-8")

    loaded = load_cleaned_records(root)
    assert [record["source_id"] for record in loaded] == ["DIU-TEST-001"]

    record_path = root / "records" / "record-01.json"
    value = json.loads(record_path.read_text(encoding="utf-8"))
    value["title"] = "Tampered title"
    record_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="record_file_hash mismatch"):
        load_cleaned_records(root)


def test_overlap_does_not_copy_an_oversized_previous_unit() -> None:
    content = (
        "Admission Rules\n\n"
        + ("Alpha evidence " * 18).strip()
        + "\n\n"
        + ("Beta details " * 18).strip()
    )
    settings = RagSettings(
        _env_file=None,
        rag_chunk_size=300,
        rag_chunk_overlap=50,
        rag_min_chunk_size=20,
    )
    chunks = [
        chunk
        for chunk in chunk_record(cleaned_record(content=content), settings=settings)
        if chunk.content_type == "text"
    ]

    assert len(chunks) == 2
    assert "Alpha evidence" in chunks[0].content
    assert "Alpha evidence" not in chunks[1].content
    assert "Beta details" in chunks[1].content
    assert all(len(chunk.content) <= 300 for chunk in chunks)


def test_table_context_uses_nearest_heading_and_prior_page_scope() -> None:
    pages = [
        {
            "page_number": 1,
            "text": (
                "m) Player Quota:\n"
                "Qualified players will enjoy waiver in following ways effective "
                "from Spring 2024 semester:"
            ),
        },
        {
            "page_number": 2,
            "text": (
                "Category Waiver rate SGPA\n"
                "National player Full free studentship 2.00"
            ),
        },
        {
            "page_number": 3,
            "text": (
                "p) Sibling/Spouse Quota:\nSibling details.\n"
                "q) Waiver for son/daughter of current students’ quota:\n"
                "Son/daughter of ongoing students will get waiver in the following way:\n"
                "Category Waiver SGPA\n"
                "Son/daughter of current students’ quota 20% 3.00"
            ),
        },
    ]
    tables = [
        {
            "headers": ["Category", "Waiver rate", "SGPA"],
            "rows": [["National player", "Full free studentship", "2.00"]],
            "extraction_method": "fixture",
            "source_locator": "page-2-table-1",
            "page_number": 2,
        },
        {
            "headers": ["Category", "Waiver", "SGPA"],
            "rows": [["Son/daughter of current students’ quota", "20%", "3.00"]],
            "extraction_method": "fixture",
            "source_locator": "page-3-table-1",
            "page_number": 3,
        },
    ]
    record = cleaned_record(
        content="Synthetic PDF aggregate",
        content_type="pdf",
        pages=pages,
        tables=tables,
    )
    by_locator = {
        chunk.source_locator: chunk
        for chunk in chunk_record(record, settings=_settings())
        if chunk.content_type == "table"
    }

    player = by_locator["page-2-table-1-part-1"].content
    child = by_locator["page-3-table-1-part-1"].content
    assert "Section: m) Player Quota" in player
    assert "effective from Spring 2024" in player
    assert "Section: q) Waiver for son/daughter" in child
    assert "Sibling/Spouse Quota" not in child


def test_repeated_same_page_tables_keep_distinct_section_contexts() -> None:
    page_text = (
        "For English Medium Background Students:\n"
        "English medium eligibility details.\n"
        "Result | Waiver | SGPA\n"
        "Five A grades | 100% | 3.25\n"
        "Condition one.\nCondition two.\nCondition three.\nCondition four.\n"
        "f) B.Pharm waiver program:\n"
        "B.Pharm eligibility details.\n"
        "Result | Waiver | SGPA\n"
        "Golden GPA | 50% | 3.00\n"
        "Condition five.\nCondition six.\nCondition seven.\nCondition eight.\n"
        "g) CSE waiver program:\n"
        "CSE eligibility details.\n"
        "Result | Waiver | SGPA\n"
        "Top score | 40% | 3.00"
    )
    rows = (
        ["Five A grades", "100%", "3.25"],
        ["Golden GPA", "50%", "3.00"],
        ["Top score", "40%", "3.00"],
    )
    tables = [
        {
            "headers": ["Result", "Waiver", "SGPA"],
            "rows": [row],
            "extraction_method": "fixture",
            "source_locator": f"page-3-table-{index}",
            "page_number": 3,
        }
        for index, row in enumerate(rows, start=1)
    ]
    record = cleaned_record(
        content="Synthetic PDF aggregate",
        content_type="pdf",
        pages=[{"page_number": 3, "text": page_text}],
        tables=tables,
    )

    contexts = [
        chunk.content.splitlines()[1]
        for chunk in chunk_record(record, settings=_settings())
        if chunk.content_type == "table"
    ]

    assert contexts == [
        "Section: For English Medium Background Students:",
        "Section: f) B.Pharm waiver program:",
        "Section: g) CSE waiver program:",
    ]
