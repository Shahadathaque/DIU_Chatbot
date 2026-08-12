# Raw Dataset v1 Collection Report

Audit and collection date: **2026-08-12**
Frozen dataset root: `data/raw/collection-v1-finalized/`
Dataset version: **v1**
Measured dataset status: **partial**
Integrity status: **passed**

The snapshot is `partial` even though all 18 registered requests succeeded. One
program-specific source (`DIU-PROG-002`) still produces a non-substantive shell
because DIU's own BBA admission API returns HTTP 400, and the dated international
booklet remains manual-review evidence. Raw content has not been cleaned.

## Registry status

| State | Sources |
| --- | ---: |
| Total registered | 18 |
| Active | 16 |
| Manual review | 2 |
| Unavailable | 0 |
| Deprecated | 0 |

The repaired registry has 11 high-priority and 7 medium-priority sources, 12
dynamic pages, 4 PDFs, and 17 rows marked date-sensitive. Source IDs and
canonical URLs are unique. All URLs are HTTPS and remain within DIU-controlled
hosts. Required boolean, state, category, priority, and currency metadata are
validated before selection.

`scrape_status` is now constrained to `active`, `manual_review`, `unavailable`,
or `deprecated`. `currency_status` is constrained to `stable_reference`,
`current_date_sensitive`, `historical`, or `uncertain`.

## Broken source investigation

| Source | Intended evidence | Old URL result | Verified official replacement |
| --- | --- | --- | --- |
| `DIU-DOC-001` | Required admission checklist/documents | Main-host PDF returned HTTP 404 | `https://webbackend.daffodilvarsity.edu.bd/photos/pdf/admission-checklist.pdf` — HTTP 200 PDF, linked by the current admission page |
| `DIU-ADM-002` | Admission process flow chart | Main-host PDF returned HTTP 404 | `https://webbackend.daffodilvarsity.edu.bd/photos/pdf/Admission-Flow-Chart19.pdf` — HTTP 200 PDF, linked by the current admission page |
| `DIU-WAV-001` | Waiver and scholarship policy | Main-host PDF returned HTTP 404 | `https://webbackend.daffodilvarsity.edu.bd/images/download/waiver-policy2025.pdf` — HTTP 200 PDF; the current live file is 8 pages and contains Spring 2026 rules |

The registry notes retain each old URL, the reason for replacement, and the
2026-08-12 verification date. Two related repairs were also made: the official
international booklet moved to the webbackend host, and the scholarship landing
route was replaced by its current client-canonical DIU scholarship article URL.

No third-party mirror or guessed URL was used.

## Dynamic backend investigation

`webbackend.daffodilvarsity.edu.bd` is an official DIU backend used by the
current main-site application code and current admission-page document links.
Its published `robots.txt` allowed public retrieval during the run. Live checks
confirmed the registered public API endpoints returned JSON, except the BBA
admission module described under known gaps.

Access was not granted at hostname scope. Nine registry sources declare 16
exact HTTPS dependency URLs. The browser permits only:

- an exact canonical dependency URL declared on that source;
- `GET` or `HEAD`;
- XHR/fetch resource types; and
- a successful robots review for that exact target.

Sibling paths, POSTs (including the admission subscriber and calculator
calculation endpoints), cross-origin navigation, unregistered origins,
WebSockets, and service workers remain blocked. Client-side navigation is
revalidated after the DOM settles. Open shadow-root content is copied into the
rendered-DOM representation so official article text is preserved, and the
number of materialized roots is recorded.

## Collection results

Run: `run-20260812T114552081796`
Interval: `2026-08-12T11:45:52.081796Z` to `2026-08-12T11:47:25.455492Z`

| Measure | Count |
| --- | ---: |
| Selected | 18 |
| Attempted | 18 |
| Successful acquisitions | 18 |
| Failed acquisitions | 0 |
| Skipped | 0 |
| Static HTML | 2 |
| Dynamic HTML | 12 |
| Total HTML | 14 |
| PDF | 4 |
| Other/binary | 0 |

The snapshot contains 18 content-addressed payloads, 18 provenance records, one
run log, one manifest, and one validation report. No raw content hash is shared
by multiple sources.

Reproducibility fingerprints:

- Registry SHA-256: `54791cbab4eb1da12fb4274ef93ad75f2df1aef13adb7547cd33afb747bd9233`
- Collector-tree SHA-256: `ccecdfa8a415ea5ac6f2ec8d90ba2278bb9df9f5895b1f3c12081da40ef9ba67`
- Requirements SHA-256: `8a95b0e30342896795fef30e5fd607601c3fc1d6f681a7502e69620521284f09`
- Git base revision: `0ae71a166994f86eb78f8aded19c484922cc3a36`
- Worktree at collection: dirty (the collector tree hash fingerprints the executed uncommitted collector bytes)

## Category coverage

| Category | Successful raw documents | Usable now | Notes |
| --- | ---: | ---: | --- |
| Admission overview | 1 | 1 | Includes Fall 2026 admission announcement from the exact approved backend endpoint |
| Admission process | 1 | 1 | Official process-flow PDF |
| Required documents | 1 | 1 | Official checklist PDF |
| Program catalog | 1 | 1 | Rendered current program/faculty listing |
| Program-specific admission | 1 | 0 | BBA shell captured; source remains manual review |
| Local tuition | 1 | 1 | Rendered program-specific fee table |
| Scholarships | 2 | 2 | DIU scholarship article plus financial-aid site |
| Waivers | 2 | 2 | Current policy PDF plus read-only calculator metadata |
| Application process | 1 | 1 | Public blank application form/instructions only |
| Admission contact | 1 | 1 | Current rendered local/international contact listing |
| Notices/current information | 2 | 1 current + 1 historical | General noticeboard plus Spring 2026 historical news item |
| International admission | 4 | 3 current/uncertain + 1 historical | Fees, contact article, policy article, and 2021–2022 booklet |

There is broad raw coverage for admission overview, program discovery, fees,
funding, documents, process, notices, application instructions, contacts, and
international applicants. A dedicated diploma-eligibility source is still not
registered; the public application form only confirms a diploma applicant path.

## Currency status

| Currency state | Count | Sources |
| --- | ---: | --- |
| Current/date-sensitive | 13 | Admission hub, application, contacts, documents, fees, financial aid, international contact, noticeboard, programs, scholarship, waiver policy/calculator |
| Historical | 2 | `DIU-NOT-002` (Spring 2026 notice), `DIU-INT-003` (2021–2022 booklet) |
| Stable reference | 1 | `DIU-ADM-002` admission process flow |
| Uncertain | 2 | `DIU-PROG-002` BBA route, `DIU-INT-002` international policy article |

Retrieval success does not upgrade a historical or uncertain source to current.
Downstream work must preserve these states and use timestamps for every fee,
deadline, scholarship, waiver, notice, contact, or current-program claim.

## Validation results

`scripts/validate_raw_dataset.py` independently checked the frozen manifest and
every manifest-selected artifact. Results:

- all JSON artifacts parsed;
- required record/failure metadata was present;
- all source IDs, source URLs, canonical URLs, and document IDs mapped to the registry;
- every raw SHA-256 and byte count recomputed successfully;
- document IDs were unique;
- duplicate content hashes: none;
- manifest arithmetic was consistent;
- prohibited cookie/auth/session headers were absent;
- secret/token patterns and absolute local user paths were absent from metadata and non-PDF raw payloads;
- suspiciously short non-PDF successes: none.

The public blank online form originally exposed anonymous CSRF values in its DOM.
The final collector blanks security-token field/script values before rendered-DOM
serialization and records both redactions. No applicant entered or submitted data
was collected. The final `DIU-APP-001` record reports
`input:csrf_token` and `script:security-token-assignment` redactions.

The immutable validation result is
`data/raw/collection-v1-finalized/validation/raw-dataset-v1-validation.json`.
All dataset files are ignored by Git under `data/raw/*`.

## Known gaps

- `DIU-PROG-002` is not usable admission evidence. Its current page is a shell;
  the exact official API call returns HTTP 400, and the official BBA menu exposes
  no current admission item. The source remains `uncertain/manual_review`.
- No dedicated, verified diploma admission/eligibility document is registered.
- `DIU-INT-002` returns a policy article, but its applicability and effective date
  for current international admission remain uncertain.
- `DIU-INT-003` is explicitly historical (2021–2022) and must not establish
  current fees, requirements, contacts, or deadlines.
- PDFs are preserved as verified raw bytes; embedded-text extraction/OCR was
  deliberately deferred and must be performed with layout-aware validation.
- The noticeboard is broad DIU content and still needs admission-only selection
  during Phase 5 cleaning.
- The calculator's mutating POST remains intentionally blocked; raw policy
  documents, not generated calculator outputs, are the authoritative waiver evidence.

## Readiness decision

The registry, acquisition controls, provenance, hashes, privacy checks, and broad
category coverage are ready to hand to Phase 5. The snapshot is nevertheless
truthfully `partial`, not complete, because the BBA program-specific source is
unresolved and two sources require explicit currency caution.

Phase 5 may begin only with source-level gates: exclude `manual_review` records
from factual cleaned output, retain currency metadata, visually verify/extract the
four PDFs, and do not infer current claims from historical sources. The BBA and
diploma gaps remain a separate source-research backlog rather than facts to infer.
