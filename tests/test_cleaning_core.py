from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter

from cleaning.filters import annotate_duplicates, filter_admission_only
from cleaning.html_cleaner import clean_html
from cleaning.normalizer import normalize_matrix, normalize_text
from cleaning.pdf_extractor import extract_pdf, reliable_pdf_table
from cleaning.utils import sha256_bytes, sha256_text


def test_html_boilerplate_controls_and_table_cleaning() -> None:
    raw = b"""
    <html><body>
      <nav>DIU News Forum Students</nav>
      <main>
        <h1>Admission Requirements</h1>
        <p>Applicants need GPA 3.00.</p>
        <form><label>Private input</label><input value="Applicant Name"></form>
        <table><tr><th>Program</th><th>Total Fee</th></tr>
          <tr><td>CSE</td><td>100,000 BDT</td></tr></table>
      </main>
      <footer>Visitor Statistics: Loading...</footer>
    </body></html>
    """
    result = clean_html(
        raw,
        title="Admission Requirements",
        category="admission_overview",
        raw_extracted_text="all source text",
        dynamic_page=False,
        source_id="TEST-001",
    )

    assert "Applicants need GPA 3.00." in result.text
    assert "DIU News" not in result.text
    assert "Applicant Name" not in result.text
    assert "Visitor Statistics" not in result.text
    assert result.tables[0].headers == ["Program", "Total Fee"]
    assert result.tables[0].rows == [["CSE", "100,000 BDT"]]


def test_program_catalog_table_is_built_from_official_dependency_response() -> None:
    raw = b"""
    <html><body><main>
      <h1>Programs</h1>
      <p>Default tab content only.</p>
    </main></body></html>
    """
    dependency_responses = {
        "https://webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/programs": (
            '{"data": ['
            '{"id": 1, "faculty_name": "Science and Information Technology"},'
            '{"id": 2, "faculty_name": "Business & Entrepreneurship"}'
            "],"
            '"program_types": ['
            '{"program_type_name": "Undergraduate", "programs": ['
            '{"name": "B. Sc. in Computer Science and Engineering", '
            '"program_short_name": "CSE", "faculty_id": 1, '
            '"department_name": "Computer Science and Engineering", '
            '"department_short_name": "cse", "duration": "4 Years", '
            '"slug": "bse-in-cse"},'
            '{"name": "Bachelor of Business Administration (BBA)", '
            '"program_short_name": "BBA", "faculty_id": 2, '
            '"department_name": "Business Administration", '
            '"department_short_name": "bba", "duration": "4 Years", '
            '"slug": "bachelor-of-business-administration"},'
            '{"name": "Bachelor of Business Administration (BBA)", '
            '"program_short_name": "BBA", "faculty_id": 2, '
            '"department_short_name": "bba", '
            '"slug": "bachelor-of-business-administration"}'
            "]},"
            '{"program_type_name": "Postgraduate", "programs": ['
            '{"name": "Master of Business Administration (MBA)", '
            '"program_short_name": "MBA", "faculty_id": 2, '
            '"department_name": "Business Administration", '
            '"department_short_name": "bba", "duration": "1-2 Years", '
            '"slug": "master-in-business-administration"}'
            "]}]}"
        )
    }

    result = clean_html(
        raw,
        title="Programs",
        category="undergraduate_programs",
        raw_extracted_text="Programs",
        dynamic_page=True,
        source_id="DIU-PROG-001",
        dependency_responses=dependency_responses,
    )

    table = result.tables[0]
    assert table.extraction_method == "official_programs_api"
    assert table.headers == [
        "Full Program Name",
        "Short Tag / Initials",
        "Program Level",
        "Faculty",
        "Department",
        "Duration",
        "Program Page",
    ]
    assert table.rows == [
        [
            "B. Sc. in Computer Science and Engineering",
            "CSE",
            "Undergraduate",
            "Science and Information Technology",
            "Computer Science and Engineering",
            "4 Years",
            "https://daffodilvarsity.edu.bd/department/cse/program/bse-in-cse",
        ],
        [
            "Bachelor of Business Administration (BBA)",
            "BBA",
            "Undergraduate",
            "Business & Entrepreneurship",
            "Business Administration",
            "4 Years",
            "https://daffodilvarsity.edu.bd/department/bba/program/bachelor-of-business-administration",
        ],
        [
            "Master of Business Administration (MBA)",
            "MBA",
            "Postgraduate",
            "Business & Entrepreneurship",
            "Business Administration",
            "1-2 Years",
            "https://daffodilvarsity.edu.bd/department/bba/program/master-in-business-administration",
        ],
    ]


def test_program_catalog_does_not_guess_invalid_url_or_duration() -> None:
    dependency_responses = {
        "https://webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/programs": (
            '{"data": [{"id": 4, "faculty_name": "Engineering"}], '
            '"program_types": [{"program_type_name": "Postgraduate", '
            '"programs": [{"name": "Diploma Holder Program", '
            '"program_short_name": "CE", "faculty_id": 4, '
            '"department_name": "Civil Engineering", '
            '"department_short_name": "../ce", "duration": "10", '
            '"slug": "bsc-in-ce-diploma-holder"}]}]}'
        )
    }

    result = clean_html(
        b"<html><body><main><h1>Programs</h1></main></body></html>",
        title="Programs",
        category="undergraduate_programs",
        raw_extracted_text="Programs",
        dynamic_page=True,
        source_id="DIU-PROG-001",
        dependency_responses=dependency_responses,
    )

    assert result.tables[0].rows[0][-2:] == ["", ""]


def test_program_catalog_table_falls_back_to_dom_grid_without_dependency() -> None:
    raw = b"""
    <html><body><main>
      <div>
        <div>
          <h3>Full Program Name</h3>
        </div>
        <ul>
          <li><div>B. Sc. in Computer Science and Engineering</div><div>CSE</div></li>
        </ul>
      </div>
    </main></body></html>
    """
    result = clean_html(
        raw,
        title="Programs",
        category="undergraduate_programs",
        raw_extracted_text="Programs",
        dynamic_page=True,
        source_id="DIU-PROG-001",
    )

    table = result.tables[0]
    assert table.extraction_method == "beautifulsoup_program_grid"
    assert table.rows == [["B. Sc. in Computer Science and Engineering", "CSE"]]


def test_normalization_preserves_facts_and_repairs_layout_noise() -> None:
    value = "Fee\u00a0Details\r\naccommoda-\n tion\n\n\n•  50% waiver"
    assert normalize_text(value) == "Fee Details\naccommodation\n\n• 50% waiver"


def test_hashing_is_sha256_and_deterministic() -> None:
    assert sha256_text("DIU") == sha256_bytes(b"DIU")
    assert sha256_text("DIU") == "e6d860f795a3d8d7c333d35bc6dcc3656bb456c116c981c79747f896c38bbc59"


def test_table_normalization_removes_only_empty_rows_and_columns() -> None:
    matrix = normalize_matrix(
        [[" Program ", "", " Fee  "], ["CSE", "", " 10,000 "], ["", "", ""]]
    )
    assert matrix == [["Program", "Fee"], ["CSE", "10,000"]]


def test_pdf_table_helper_is_conservative() -> None:
    reliable = reliable_pdf_table(
        [["Program", "Fee"], ["CSE", "$100"]], page_number=2, table_index=1
    )
    uncertain = reliable_pdf_table(
        [["", "Fee"], ["CSE", "$100"]], page_number=2, table_index=2
    )
    assert reliable is not None
    assert reliable.page_number == 2
    assert uncertain is None


def test_pdf_extraction_helper_does_not_ocr_blank_page() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    payload = BytesIO()
    writer.write(payload)

    result = extract_pdf(payload.getvalue())

    assert result.extraction_method == "pdfplumber_embedded_text"
    assert result.extraction_status == "failed"
    assert result.pages[0].quality_flags == ["no_embedded_text"]
    assert "pdf_pages_without_embedded_text" in result.quality_flags


def test_notice_filter_drops_unrelated_news() -> None:
    text = "Notice Board\nCSE Midterm Examination\nSports day"
    filtered, flags = filter_admission_only(
        text, title="DIU Noticeboard", category="admission_notices"
    )
    assert filtered == "DIU Noticeboard"
    assert "admission_filter_no_matches" in flags


def test_exact_and_near_duplicates_are_annotated_not_deleted() -> None:
    base = " ".join(["admission scholarship requirement program"] * 30)
    records = [
        _duplicate_record("doc-a", "A", base, "same"),
        _duplicate_record("doc-b", "B", base, "same"),
        _duplicate_record("doc-c", "C", base + " deadline", "different"),
    ]
    result = annotate_duplicates(records, near_threshold=0.90)

    assert len(records) == 3
    assert len(result["exact_pairs"]) == 1
    assert result["near_pairs"]
    assert "duplicate_content" in records[0]["quality_flags"]
    assert "near_duplicate" in records[2]["quality_flags"]


def _duplicate_record(document_id: str, source_id: str, text: str, digest: str):
    return {
        "document_id": document_id,
        "source_id": source_id,
        "cleaned_content": text,
        "cleaned_content_hash": digest,
        "quality_flags": [],
        "related_documents": [],
    }
