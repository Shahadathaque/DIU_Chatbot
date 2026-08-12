# Cleaned Dataset v1 Report

Processing date: **2026-08-12**  
Raw input: `data/raw/collection-v1-finalized/`  
Cleaned output: `data/cleaned/v1/`  
Pipeline version: **phase5-1.0**  
Measured status: **partial**  
Integrity validation: **passed**

The cleaned snapshot contains one traceable record for each of the 18 registered
raw sources. The status remains `partial` because the general noticeboard contains
no admission-related notice in the captured entries and the BBA route remains a
non-substantive manual-review shell. Those source limitations are represented as
records and flags rather than being silently discarded.

## 1. Cleaning methodology

The pipeline reads the finalized raw manifest, requires its successful-source set
to match every active or manual-review registry row, verifies safe relative raw
paths, and processes records in source-ID order. It applies deterministic Unicode
NFKC and whitespace normalization without summarizing or rewriting DIU facts.

Each output record retains source/document identity, registered/canonical/final
URLs, raw record and content paths, raw and cleaned SHA-256 hashes, collection and
processing timestamps, retrieval method, status, currency metadata, dynamic-source
provenance, extraction quality, tables, page text, flags, and duplicate
relationships. Generated cleaned data remains ignored by Git under
`data/cleaned/*`.

## 2. HTML cleaning

Fourteen HTML records were processed with Beautiful Soup. Scripts, styles,
templates, embedded frames, navigation, footers, sidebars, social/chat/cookie
elements, repeated quick-link blocks, visitor counters, generic promotional
blocks, and unrelated forms were removed. Consecutive duplicate lines were
collapsed. Page titles, headings, paragraphs, lists, program names, fees,
scholarship and waiver conditions, dates, application paths, required documents,
and admission contacts were retained verbatim apart from normalization.

The public online-application record keeps its five-step process, supported
applicant paths, required-field instruction, and one-hour submission instruction.
Personal-data controls, country/state option dumps, and observed default/test-like
form values were excluded. Its two raw security-value redactions remain recorded
as provenance, but no token value is present in the cleaned record.

## 3. Dynamic-content handling

Verified backend-derived text already materialized in the raw DOM remains part of
the clean source. The records also preserve approved and observed dependency URLs,
shadow-root counts, browser version, and capture representation.

`DIU-FEE-001` and `DIU-FEE-002` retain their substantive fee data but carry
`dynamic_content_incomplete` because their separate notice area said no notices
were available; that absence text is removed from factual content. The same flag
marks `DIU-PROG-002`, whose registered BBA page still has no substantive admission
body.

## 4. PDF extraction

All four official PDFs were processed with `pdfplumber` 0.11.8 using embedded text
only; OCR was disabled. Visual verification used Poppler renders for the two
single-page documents and contact sheets covering all 19 waiver-policy pages and
all 40 historical-booklet pages.

All four PDFs produced embedded text successfully across 61 pages. Page number,
normalized page text, character count, table-candidate count, retained-table count,
and page flags are preserved. Page 40 of the historical international booklet had
no embedded text and is explicitly flagged. The one-page admission flow chart is
readable but spatial/graph ordering is not fully expressible as linear text, so it
carries `pdf_layout_complex`.

## 5. Table preservation

Eighteen reliable structured tables were retained across five records:

| Source | Tables | Content |
| --- | ---: | --- |
| `DIU-DOC-001` | 1 | Program-to-required-document rows |
| `DIU-FEE-001` | 1 | Local program fees |
| `DIU-FEE-002` | 1 | International program fees |
| `DIU-PROG-001` | 1 | Program names and short tags |
| `DIU-WAV-001` | 14 | Waiver/result/SGPA/credit relationships |

HTML tables require explicit headers and consistent multi-column rows. PDF tables
require two or more columns, non-empty headers, rectangular rows, and at least
72% populated cells. Ambiguous PDF layout candidates remain represented in page
text and produce `pdf_table_uncertain`; no missing cell or header is invented.

## 6. Admission-only filtering

The news and notice sources are handled separately from ordinary pages.
`DIU-NOT-002` retains the Spring 2026 admission article and excludes the unrelated
“More News” list. The captured `DIU-NOT-001` entries were examination/academic
notices with no admission match, so its record contains only the source title and
is marked `admission_filter_no_matches`, `empty_section`, `short_content`, and
`partial`.

## 7. Provenance preservation

The validator passed all 18 raw-to-clean record mappings. It independently checks:

- registry source IDs, URLs, document IDs, titles, categories, and status metadata;
- raw record paths and exact raw-byte SHA-256 values;
- response byte counts and collection timestamps;
- cleaned content/file hashes and unique document IDs;
- safe relative paths, HTTP(S) URLs, and UTC timestamps;
- source-token traceability for cleaned text and structured-table cells; and
- absence of local user paths, token values, and known captured form defaults.

The portable raw-tree fingerprint is
`270350af24b14a2c5e1ae3001b016e6ba1a585814176c8e804e8f13ec7936ec2`.
The independent pre/post full-path aggregate raw fingerprint remained
`586867248e3e26eba47ee46af7c2c4c302be97639a124482ecec960f35f54702`,
confirming that Phase 5 did not change a raw file.

## 8. Currency handling

Registry currency states are preserved exactly:

| Currency state | Records |
| --- | ---: |
| `current_date_sensitive` | 13 |
| `historical` | 2 |
| `uncertain` | 2 |
| `stable_reference` | 1 |

Historical records (`DIU-NOT-002`, `DIU-INT-003`) carry an explicit `historical`
flag. Uncertain records (`DIU-INT-002`, `DIU-PROG-002`) carry
`uncertain_currency`. Retrieval and cleaning do not promote either state to
current. Both registry manual-review states are also preserved.

## 9. Duplicate detection

Exact duplicates are detected by cleaned-content SHA-256. Near duplicates are
detected at a 0.92 threshold using five-token-shingle overlap after case and
whitespace normalization, with a length-ratio gate. Separate records and
provenance would be retained and cross-linked when a match is found.

Measured result: **0 exact duplicate pairs and 0 near-duplicate pairs**.

## 10. Quality flags

Material source-level flags are:

- `manual_review`: `DIU-INT-003`, `DIU-PROG-002`;
- `historical`: `DIU-INT-003`, `DIU-NOT-002`;
- `uncertain_currency`: `DIU-INT-002`, `DIU-PROG-002`;
- `dynamic_content_incomplete`: `DIU-FEE-001`, `DIU-FEE-002`, `DIU-PROG-002`;
- `empty_section`: `DIU-NOT-001`, `DIU-PROG-002`;
- `pdf_table_uncertain`: `DIU-INT-003`, `DIU-WAV-001`;
- `pdf_pages_without_embedded_text`: `DIU-INT-003`; and
- `pdf_layout_complex`: `DIU-ADM-002`.

Complete per-record flags and counts are in `quality_report.json`.

## 11. Dataset statistics

| Measure | Value |
| --- | ---: |
| Total raw documents | 18 |
| Total cleaned documents | 18 |
| HTML documents | 14 |
| PDF documents | 4 |
| Successful extractions | 16 |
| Partial extractions | 2 |
| Failed extractions | 0 |
| Current/date-sensitive records | 13 |
| Historical records | 2 |
| Uncertain records | 2 |
| Stable-reference records | 1 |
| Manual-review records | 2 |
| Records containing structured tables | 5 |
| Structured tables | 18 |
| Exact duplicate pairs | 0 |
| Near-duplicate pairs | 0 |
| Average source text length | 13,507.89 characters |
| Average cleaned text length | 7,849.61 characters |
| Mean per-document text removed | 42.59% |

“Source text length” means the raw collector's extracted text for HTML and the
pre-normalization embedded-text extraction for PDFs; it is not the raw response
byte size. Percentage removed is calculated per record and then averaged.

Documents by category:

| Category | Count |
| --- | ---: |
| Admission application process | 1 |
| Admission contact information | 1 |
| Admission notices | 1 |
| Admission overview | 1 |
| Admission process | 1 |
| Current admission information | 1 |
| International admission | 4 |
| Program-specific admission | 1 |
| Required admission documents | 1 |
| Scholarships | 2 |
| Tuition and fees | 1 |
| Undergraduate programs | 1 |
| Waivers | 2 |

## 12. Known limitations

- The dataset is correctly `partial`: two retained source records are not usable
  as complete factual sections.
- PDF embedded text preserves evidence but cannot fully encode flow-chart geometry
  or every complex table layout. No OCR or invented reconstruction was used.
- The historical international booklet includes a visually non-text final page and
  broad international-student information beyond admission alone.
- Dynamic fee records have complete captured fee rows but an unavailable notice
  subsection.
- Cleaning removes obvious chrome deterministically; Phase 6 should still profile
  vocabulary and section balance before any later chunking decision.

## 13. Manual-review records

`DIU-PROG-002` is uncertain and partial because the BBA route has only a shell.
`DIU-INT-003` extracted successfully, but it remains manual review and historical
because the booklet is explicitly from 2021–2022. Neither may be silently treated
as current factual evidence.

## 14. Missing BBA coverage

No substantive BBA admission requirements were recovered. The cleaned BBA record
preserves title/provenance and explicit partial/manual-review flags; it does not
infer requirements from other programs.

## 15. Missing dedicated diploma eligibility source

Registry v1 still has no dedicated, verified diploma eligibility source. The
application form confirms a diploma application path and the checklist/waiver
documents contain diploma-related material, but these do not justify inventing a
complete eligibility rule set.

## 16. Historical and uncertain information

The Spring 2026 admission news and 2021–2022 international booklet are historical.
The international exchange-policy article and BBA shell are uncertain. These
states, timestamps, and flags must become mandatory filters in any downstream
analysis or evidence selection.

## 17. Research implications

Cleaned v1 is integrity-valid and suitable for Phase 6 exploratory data analysis,
provided analysis treats partial, historical, uncertain, and manual-review records
as separate cohorts. It is not yet a RAG corpus, training set, eligibility engine,
or evidence that every admission topic has complete current coverage.

Reproducibility fingerprints are recorded in `manifest.json`, including raw and
registry hashes, the ten-file cleaning-pipeline fingerprint
`b07b46cb4a05c8ea9ab8de091b20002ab6976c2d13733cfab9b6ab51ce588d7a`,
dependency versions, Git base revision, dirty-worktree state, record-file hashes,
and cleaned-content hashes.
