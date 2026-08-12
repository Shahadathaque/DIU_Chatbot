# Data Collection Protocol

## 1. Research data scope

Collect only DIU admission content needed for programs, requirements, processes, documents, fees, funding, notices, deadlines, diploma pathways, international applicants, and contacts.

## 2. Authoritative-source policy

The primary authority is `https://daffodilvarsity.edu.bd/`. DIU-controlled subdomains may be used when the main site links to them and they are necessary for admission, including online application, financial-aid, news, and document hosts. Third parties cannot establish facts.

## 3. Page-selection criteria

A page must provide direct admission facts, an official application/contact path, a relevant program list, or a DIU-linked source document. Register its canonical URL, purpose, priority, rendering strategy, volatility, and verification state before collection.

## 4. Exclusion criteria

Exclude biographies, publications, alumni content, student portals, registration support, unrelated news/events, marketing without useful admission facts, and duplicate mirrors unless a mirror is the only official artifact.

## 5. Dynamic-page strategy

Use simple HTTP extraction for pages classified `false`. Use Playwright when useful content is JavaScript-loaded, static HTML is only a shell, or controls reveal content. `unknown` pages require manual comparison of raw and rendered output.

Cross-origin browser dependencies must be declared as exact HTTPS URLs in the
registry. Only read-only `GET`/`HEAD` XHR or fetch requests to those URLs may be
allowed after their own robots review. An approved endpoint does not authorize
sibling paths, writes, cross-origin navigation, WebSockets, service workers, or
a hostname wildcard.

## 6. Date-sensitive-information strategy

Fees, deadlines, current-semester notices, requirements, scholarships, and waiver rules receive retrieval timestamps and shorter refresh intervals. They remain RAG evidence rather than fine-tuning facts.

Every registry row also carries one explicit currency state:

- `stable_reference`: process/reference content not expected to change frequently;
- `current_date_sensitive`: volatile content that requires the retrieval date;
- `historical`: valid dated evidence that must not be presented as current; or
- `uncertain`: currency or rendered completeness still needs human review.

Historical sources remain registered; downstream stages must use this state
rather than treating a successful HTTP response as proof of currency.

## 7. Provenance requirements

Retain document ID, source ID, canonical URL, title, category, program, faculty, UTC retrieval time, HTTP status, content type, exposed update date, collector version, and content hash.

## 8. Duplicate handling

Normalize host, scheme, path, and irrelevant query parameters. Detect exact duplicates by hash and near-duplicates during cleaning. Preserve aliases and provenance while designating one canonical record.

## 9. Content-hash strategy

Compute SHA-256 for exact response bytes and separately for normalized extracted content. Store the algorithm and collector version. Raw hashes prove capture identity; normalized hashes support duplicate and change detection.

## 10. Failed-page handling

Log time, URL, attempt, status/exception, redirect, and rendering method. Retry transient failures with bounded exponential backoff. Policy/authentication blocks and repeated failures require review, not circumvention.

## 11. Stale-information detection

Compare hashes, exposed dates, semester labels, and internal dates. Flag expired deadlines, contradictory dates, default dates, and older linked documents. A successful response alone does not prove currency.

## 12. Update strategy

Check high-priority volatile sources most frequently and stable process documents less often. Raw runs are append-only. Changed hashes trigger downstream cleaning/re-indexing; unchanged captures need not create duplicate cleaned records.

## 13. Ethical scraping principles

Identify the research client where practical, collect public information only, minimize load and personal data, do not bypass controls, and stop when site behavior indicates restriction or harm.

## 14. Rate limiting

Start with one conservative worker per host, a host-level budget, and bounded retries. Subdomains have independent limits but must not evade a main-host restriction.

## 15. Reasonable request delays

Start with randomized delays of about 2–5 seconds per host and increase after errors or rate-limit signals. Phase 4 must make these configurable.

## 16. Robots/site-policy consideration

Review `robots.txt`, terms, and relevant notices immediately before collection and record the review time. Robots guidance does not grant permission; explicit restrictions and applicable law take precedence.

## 17. Raw-data preservation policy

Never edit raw captures. Store response bytes and metadata under versioned run IDs outside Git when large. Corrections occur only in derived data with lineage to raw hashes.

Broader research snapshots carry a `raw_dataset_version` and a measured status:
`complete` only when every selected source succeeds or is deliberately reused,
`partial` when at least one succeeds and at least one fails, and `incomplete`
when no selected source succeeds.

## 18. Data-cleaning separation

Cleaning is a distinct reproducible step. It may remove repeated navigation/footer content and normalize whitespace while preserving headings, lists, tables, dates, conditions, programs, fees, and provenance.

## 19. Research reproducibility

Version the registry, configuration, code revision, dependencies, run manifest, exclusions, failures, and hashes. Use UTC and deterministic transformations. Distinguish checked URLs from candidates and implemented pipelines from executed collection.
