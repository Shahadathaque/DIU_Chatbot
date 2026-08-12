# Phase 4 Controlled DIU Scraper Report

Report date: **2026-08-12**  
Primary sample run: `run-20260812T101940534420`  
Supplemental PDF runs: `run-20260812T102306216048`, `run-20260812T102324398213`  
Validation window: **2026-08-12T10:19:40.534420Z–2026-08-12T10:23:27.394072Z**  
Artifact namespace: `data/raw/release-sample/`

## Scope

Phase 4 implements controlled acquisition only. The collector accepts sources from
[`data/source_registry.csv`](../../data/source_registry.csv), processes them
sequentially, and does not discover or crawl links. It preserves raw response bytes
and provenance; it does not clean, normalize, summarize, create rules, chunk for
RAG, generate training data, or implement application AI.

## Architecture

- `models.py`, `registry.py`, and `utils.py` validate the CSV, retain registered
  metadata, canonicalize URLs, reject duplicate IDs/URLs, build stable document
  IDs and safe paths, and compute SHA-256 hashes.
- `fetcher.py` dispatches exactly one registered source. `html_fetcher.py` uses
  bounded `requests`; `playwright_fetcher.py` captures the rendered DOM with
  Chromium; `pdf_fetcher.py` preserves original bytes and requires a valid PDF
  signature.
- `extractor.py` makes a lightweight text view while retaining the raw capture.
  It removes executable elements only. PDF extraction is deferred by default and
  OCR is never attempted.
- `policy.py` records a robots review per selected URL while fetching each origin's
  robots file once per run. `rate_limit.py` provides seeded 2–5 second per-host
  pacing; collection concurrency is one.
- `storage.py` uses a global content-addressed byte store, one provenance record per
  stable document ID/hash, per-run failure records, concise logs, and a run
  manifest. It recomputes hashes, checks existing identities, and never overwrites.
- [`scripts/scrape_diu.py`](../../scripts/scrape_diu.py) provides dry-run, limit,
  source ID, category, priority, URL, optional skip-existing, pacing, timeout,
  retry, seed, and debug options. The CLI is fixed to the audited registry and DIU
  host suffix. One failed source does not prevent later selected sources from running.

The predictable ignored layout is:

```text
data/raw/
├── content/sha256/<content-hash>
├── records/<document-id>/<content-hash>.json
├── failures/<run-id>/
├── runs/
└── logs/
```

## Fetch methods and safety controls

Static HTML uses `requests` with connect/read timeouts, a normal identified user
agent, a 50 MiB response ceiling, bounded paced retries for transient
statuses/errors, non-2xx and unexpected-MIME rejection, and response-header
allowlisting. Redirects outside the exact registered canonical URL are blocked.
Dynamic HTML
uses headless Chromium, `domcontentloaded`, a bounded five-second network-idle
opportunity, a 500 ms settle period, a 30-second navigation timeout, and the same
response ceiling. Third-party browser requests and nonessential image/media/font
requests are blocked; service workers and WebSockets are disabled so they cannot
bypass that boundary, and blocked origins are recorded. Robots responses are
streamed through a fail-closed 1 MiB cap. PDF acquisition is separate, rejects
non-2xx responses, and
requires `%PDF-` within the first 1,024 bytes so an HTML error page cannot be saved
as a PDF.

The measured run used one worker, a seeded randomized 2–5 second host delay, and
zero retries to avoid repeating requests during the first sample. Main-site and
news-site robots files both returned HTTP 200 and allowed the selected paths for
the dedicated collector product token. Unavailable or restrictive robots guidance
fails closed.
Their checks and hashes are in the run manifest. A review of the public site footer
found a `Privacy Statement` label linked only to `#`; no actionable public
collection-terms URL was exposed. Robots guidance is not permission, and absence
of a published terms link is not affirmative permission.

## Measured sample

The primary run attempted the requested dynamic/static/PDF trio. Because its
registered checklist PDF returned 404, two additional high-priority, audited, and
registry-verified PDF URLs were tried one at a time. The following are aggregate
actual counts across those three manifests:

```text
Attempted: 5
Successful: 2
Failed: 3
HTML: 2
Dynamic: 1
PDF: 0
Binary: 0
Skipped: 0
```

| Source | Registered role | Method | Result | Saved bytes | Raw SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| `DIU-ADM-001` | Dynamic admission overview | Playwright | HTTP 200 HTML | 272,045 | `1c99662c01d95b33328d1bace5d17fe050f3b811d8b7f9ce169bc63dc6609c68` |
| `DIU-DOC-001` | Admission checklist PDF | requests PDF | HTTP 404 failure | 0 | — |
| `DIU-NOT-002` | Static Spring 2026 admission notice | requests | HTTP 200 HTML | 37,556 | `2ad56677f3556457492c4c27dbae967b6e0bb3da98740f93096e266127f1ab11` |
| `DIU-ADM-002` | Admission flow-chart PDF | requests PDF | HTTP 404 failure | 0 | — |
| `DIU-WAV-001` | Waiver-policy PDF | requests PDF | HTTP 404 failure | 0 | — |

The two successful hashes were independently recomputed from saved bytes and
matched the filenames, records, and manifest. Their extracted-text hashes also
recomputed correctly. Both successful final URLs matched their registered source
URLs. No duplicate content or duplicate record occurred in this sample.

## Dynamic-page findings

`DIU-ADM-001` rendered successfully with Chromium `139.0.7258.5` and exposed
admission sections and interactive controls. Third-party requests to Central AI,
Google Tag Manager, cdnjs, and the unregistered DIU backend host were blocked and
recorded. Consequently some third-party-fed fields showed loading/no-notice states.
In particular, `webbackend.daffodilvarsity.edu.bd` is DIU-controlled but was not
the registered page origin, so it remained blocked and the captured Important
Notices area showed no notices. Future collection should allow such a dependency
only after explicitly registering/reviewing its origin and robots policy, not by
broadly relaxing the browser boundary.
The raw DOM and lightly extracted view still contain navigation, footer,
notification controls, and country codes. That is acceptable for raw Phase 4
preservation; it is explicit input for Phase 5 cleaning rather than a claim of
clean main content. The registry
title differs from the generic observed HTML `<title>`, so both values are retained
without inventing a correction.

## PDF handling

`DIU-DOC-001`, `DIU-ADM-002`, and `DIU-WAV-001` all currently return HTTP 404 at
their registered URLs. The collector stored only concise failure records; it did
not misclassify or retain any response as a PDF. The live admission page points to
a similarly named checklist file on an unregistered
`webbackend.daffodilvarsity.edu.bd` URL. The scraper did not substitute that URL,
because it must be audited and added to the registry before collection. Therefore
PDF acquisition and signature checks are unit-tested but not yet validated by a
successful live PDF in this sample. Embedded-text extraction remains deferred.

## Raw-data and privacy validation

Successful records retain document/source IDs, original/canonical/final URLs,
registry metadata, UTC attempt/retrieval times, status, MIME/content type, method,
capture representation, attempts, redirect chain, raw and
extracted SHA-256 hashes, byte count, safe response headers, collector version,
run ID, and raw path. Failure metadata retains the corresponding source identity,
timestamp, method, status, and concise error. JSON parsing and manifest arithmetic
passed. Scans found no cookie, session, authorization, bearer/API token, submitted
applicant name, submitted email, or submitted phone data. Public page text such as
official contacts and blank form labels remains part of the raw source.

## Limitations

- This is a deliberately small three-source sample, not the 18-source collection.
- Registry drift must be resolved for the three failed verified PDF entries before
  the full run; no unregistered replacement was followed.
- `DIU-NOT-002` describes Spring 2026 and was retrieved in August 2026; downstream
  currency checks must not present it as current merely because collection worked.
- Lightweight extraction retains noisy visible page components by design.
- Dynamic captures can omit content supplied by blocked cross-origin dependencies;
  the measured admission DOM's no-notices state must not be treated as a factual
  claim that DIU had no notices.
- The sample manifest records commit `a2bd071d3bb4d5335b592cc4a41058d0499f9257`,
  but the Phase 4 implementation was an uncommitted working-tree change during
  execution. It additionally records the exact current collector-tree hash
  `799462859a9e5a3c39366f610d8957f6bab40960631542369aac4037b385b58f`;
  a post-commit full run is still recommended for commit-addressable provenance.
- The local Python 3.9.6 runtime emitted an `urllib3` LibreSSL compatibility warning.
  Project setup recommends Python 3.11.
- Raw artifacts are excluded from Git. They need backed-up research storage with
  their records and run manifests.
- Counts in this report aggregate the three manifests under
  `data/raw/release-sample/`. Earlier immutable engineering runs remain in other
  ignored `data/raw/` namespaces and are not part of these measurements.

## Manual setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

Chromium `139.0.7258.5` (Playwright build `1181`) was installed and used
successfully for this sample. A fresh environment still needs the browser command.
PDF text extraction is deferred in Phase 4; original PDF bytes remain the
authoritative capture. OCR remains disabled.

## Recommendations for the full collection run

1. Re-audit the three failed PDF entries and any candidate replacement URL; update
   the registry only after DIU ownership, robots guidance, relevance, and currency
   are verified.
2. Commit the Phase 4 implementation, then run a new dry-run and another small PDF
   validation before attempting all registered sources.
3. Back up `data/raw/release-sample/` outside Git with its manifest; use the saved
   registry, requirements, raw-content, and extracted-content hashes for change
   detection.
4. Keep sequential 2–5 second pacing initially. Review any authentication, CAPTCHA,
   policy, or rate-limit signal rather than bypassing it.
5. Inspect all failures and date-sensitive content before Phase 5; do not interpret
   a successful response as proof that admission facts are current.

## Research impact

Content-addressed immutable captures and source-level provenance make later
transformations auditable: a cleaned record can point to exact source bytes, an
update can be detected by hash, duplicate payloads can share storage without losing
source identity, and stale or conflicting evidence can be reviewed rather than
silently reconciled. Run-level registry/configuration/environment metadata separates
an implemented pipeline from an executed collection and supports reproducible
dataset versions for later baseline, fine-tuning, and RAG comparisons.
