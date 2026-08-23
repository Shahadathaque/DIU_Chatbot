# DIU Source Audit

Audit date: **2026-08-23**
Registry: [`data/source_registry.csv`](../../data/source_registry.csv)

## Method and verification meaning

Discovery used DIU’s main sitemap, admission hub, current application code, and
official pages linked from them. Phase 4.1 replaced the earlier free-form
`verified` state with validated `active`, `manual_review`, `unavailable`, and
`deprecated` states. An `active` response still does **not** mean every fact is
current; currency is recorded separately.

## Totals

- Registered sources: **24**
- Active sources: **22**
- Manual-review sources: **2**
- Unavailable sources: **0**
- Deprecated sources: **0**
- High priority: **15**
- Medium priority: **9**
- Dynamic pages: **14**
- Date-sensitive sources: **23**
- Static PDF candidates: **5**

## Sources by category

| Category | Count |
| --- | ---: |
| Admission overview | 1 |
| Admission process | 1 |
| Required admission documents | 1 |
| Undergraduate programs | 1 |
| Program-specific admission | 1 |
| Tuition and fees | 1 |
| Scholarships | 2 |
| Waivers | 2 |
| Admission/application process | 1 |
| Admission notices | 1 |
| Current admission information | 1 |
| Admission contact information | 1 |
| International admission | 4 |
| Admission test result | 1 |
| Credit transfer guidelines | 1 |
| Guardian guidelines | 1 |
| Payment guidelines | 1 |
| International scholarships | 1 |
| Waiver calculator | 1 |
| Financial aid | 1 |
| Life insurance | 1 |

Postgraduate programs and diploma admission currently appear inside broader
admission/program/policy materials rather than reliable dedicated pages, so they
remain gaps instead of invented entries. The current sitemap exposes no separate
substantive seat-plan page; queries use the official admission/result destinations
and must report unavailable current information when those pages contain no plan.

## High-priority sources

- Central admission hub and official checklist/process PDFs.
- Local and international tuition pages.
- Local and international scholarship pages, waiver-policy PDF, financial-aid
  portal, and calculator.
- Online application instructions.
- Current-semester admission notice.
- Program directory.
- Admission result, credit-transfer, guardian-guidance, payment-guideline, and
  life-insurance destinations.

These contain direct applicant facts or paths to them. Fees, deadlines, requirements, and funding rules are volatile RAG evidence, not fine-tuning facts.

## Dynamic and Playwright candidates

The admission hub, programs, department admission page, tuition pages,
scholarship page, calculator, online form, noticeboard, admission contact,
admission result, and international pages are classified dynamic. Nine sources
declare 16 exact, read-only webbackend dependency URLs. Shadow-root article
content is materialized into the rendered-DOM capture with provenance;
unrestricted cross-origin access remains blocked.

## Simple extraction candidates

- The financial-aid, credit-transfer, guardian-guidance, and life-insurance
  destinations returned HTML without interaction.
- The semester-specific DIU news article returned relevant HTML without interaction.
- Direct PDFs include the flow chart, checklist, waiver policy, payment guide,
  and international booklet.

All five PDFs were acquired successfully in the 2026-08-23 refresh. PDF text and
tables still require layout-aware extraction and visual verification.

The complete refresh fetched **24/24** registered sources, validated **24** cleaned
records, and atomically published **317** chunks. It reused 299 unchanged embeddings,
embedded 18 changed/new chunks, added six source records, and retained the 52-program
runtime catalog.

The 2026-08-23 post-repair audit checked all 21 admission-menu sections against
the live 317-chunk pgvector index and passed 21/21. Query-understanding coverage
also tests at least four phrasings per section across English, Bangla, Banglish,
short forms, and representative misspellings. The local tuition-table audit
resolved 211/211 harmless query variants across all 50/50 fee-bearing catalog
programs to their exact canonical rows. A separate audience audit passed 45/45
checks across all nine international USD rows, including local-only,
international-only, and explicit comparison requests.

The final SQA pass expanded the admission retrieval audit from one primary query
per section to all 84 variants and added a separate adversarial query-quality
audit. The deterministic 84-query admission audit, 51-query adversarial audit,
and both cleaned-table tuition audits pass locally. The current sandbox could not resolve the configured
PostgreSQL host, and approval to run the expanded live retrieval audit outside
the sandbox timed out; therefore the earlier 21/21 live result remains historical
evidence, not a claim that the expanded 84-query live audit ran successfully.

Public API smoke checks confirmed exact canonical retrieval for ITM, BBA in
Finance & Banking, MDS, M. A in English, and MSS in Journalism, Media and
Communication, plus representative CSE, MPH, undergraduate JMC, LLM, and Tourism
queries. They also showed that the deployed revision predates the local fixes for
generator omission in multi-program tuition answers and universal-scholarship
claim compatibility. Those fixes require a separately reviewed deployment.

## Known gaps

- The BBA program-specific admission route remains a shell; its official API
  returns HTTP 400 and the current BBA menu lists no admission item.
- Dedicated diploma eligibility and program-specific requirement pages need manual navigation.
- The current credit-transfer, guardian-guidance, and life-insurance article
  routes expose only their titles after boilerplate removal. They are retained as
  partial official-link evidence; the assistant must state that substantive
  current information is unavailable instead of generating details.
- The admission noticeboard currently contains no matching admission notice, and
  the result destination contains no substantive current result/seat-plan data.
- The 2021–2022 international booklet cannot establish current costs, deadlines, or policies.
- The noticeboard needs admission-only filtering.
- The international policy article has uncertain current-admission applicability.
- Department admission routes may show stale/default dates and require change detection.
- No retrieval system can truthfully answer facts absent from the collected
  official pages. Such questions intentionally return insufficient information
  (and a verified official link when available) rather than a semantically similar
  but incompatible answer.

## Stable behavior versus changing facts

Fine-tuning should teach stable behavior: DIU identity, terminology, clarification, refusal, uncertainty, multilingual response patterns, and evidence-aware structure.

RAG should supply changing facts: tuition, deadlines, notices, requirements, scholarships, waivers, and policy versions. Missing or conflicting current evidence should produce insufficient information and an official verification path.
