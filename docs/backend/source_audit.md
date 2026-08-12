# DIU Source Audit

Audit date: **2026-08-12**
Registry: [`data/source_registry.csv`](../../data/source_registry.csv)

## Method and verification meaning

Discovery used DIU’s main sitemap, admission hub, current application code, and
official pages linked from them. Phase 4.1 replaced the earlier free-form
`verified` state with validated `active`, `manual_review`, `unavailable`, and
`deprecated` states. An `active` response still does **not** mean every fact is
current; currency is recorded separately.

## Totals

- Registered sources: **18**
- Active sources: **16**
- Manual-review sources: **2**
- Unavailable sources: **0**
- Deprecated sources: **0**
- High priority: **11**
- Medium priority: **7**
- Dynamic pages: **12**
- Date-sensitive sources: **17**
- Simple HTML candidates: **2**
- Static PDF candidates: **4**

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

Postgraduate programs and diploma admission currently appear inside broader admission/program/policy materials rather than reliable dedicated pages, so they remain gaps instead of invented entries.

## High-priority sources

- Central admission hub and official checklist/process PDFs.
- Local and international tuition pages.
- Local scholarship page, waiver-policy PDF, and calculator.
- Online application instructions.
- Current-semester admission notice.
- Program directory.

These contain direct applicant facts or paths to them. Fees, deadlines, requirements, and funding rules are volatile RAG evidence, not fine-tuning facts.

## Dynamic and Playwright candidates

The admission hub, programs, department admission page, tuition pages,
scholarship page, calculator, online form, noticeboard, admission contact, and
international pages are classified dynamic. Nine sources now declare 16 exact,
read-only webbackend dependency URLs. Shadow-root article content is materialized
into the rendered-DOM capture with provenance; unrestricted cross-origin access
remains blocked.

## Simple extraction candidates

- The financial-aid subdomain returned relevant HTML without interaction.
- The semester-specific DIU news article returned relevant HTML without interaction.
- Direct PDFs include the flow chart, checklist, waiver policy, and international booklet.

All four PDFs were acquired successfully in raw dataset v1. PDF text and tables
still require layout-aware extraction and visual verification.

## Known gaps

- The BBA program-specific admission route remains a shell; its official API
  returns HTTP 400 and the current BBA menu lists no admission item.
- Dedicated diploma eligibility and program-specific requirement pages need manual navigation.
- The 2021–2022 international booklet cannot establish current costs, deadlines, or policies.
- The noticeboard needs admission-only filtering.
- The international policy article has uncertain current-admission applicability.
- Department admission routes may show stale/default dates and require change detection.

## Stable behavior versus changing facts

Fine-tuning should teach stable behavior: DIU identity, terminology, clarification, refusal, uncertainty, multilingual response patterns, and evidence-aware structure.

RAG should supply changing facts: tuition, deadlines, notices, requirements, scholarships, waivers, and policy versions. Missing or conflicting current evidence should produce insufficient information and an official verification path.
