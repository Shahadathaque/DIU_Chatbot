# DIU Source Audit

Audit date: **2026-08-10**  
Registry: [`data/source_registry.csv`](../../data/source_registry.csv)

## Method and verification meaning

Discovery used DIU’s main sitemap, admission hub, and official pages linked from them. `verified` means the exact URL opened successfully and admission relevance was observed; it does **not** mean every fact is current. `manual_review` means the URL exists but useful content was hidden behind rendering or an older document needs currency review. No mass scraping occurred.

## Totals

- Registered sources: **18**
- Verified URLs: **14**
- Manual-review URLs: **4**
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

The admission hub, programs, department admission page, tuition pages, scholarship page, calculator, online form, noticeboard, admission contact, and international pages are classified dynamic. Static inspection returned sparse shells or `Loading...` on several. Phase 4 should compare raw HTML with a rendered DOM before finalizing selectors.

## Simple extraction candidates

- The financial-aid subdomain returned relevant HTML without interaction.
- The semester-specific DIU news article returned relevant HTML without interaction.
- Direct PDFs include the flow chart, checklist, waiver policy, and international booklet.

PDF text and tables need layout-aware extraction and visual verification; this audit did not collect them into the dataset.

## Known gaps

- Dedicated current undergraduate versus postgraduate catalogs were not clearly exposed in static output.
- Dedicated diploma eligibility and program-specific requirement pages need manual navigation.
- Some sitemap scholarship/international links returned discovery errors despite related official pages existing.
- The admission-contact page did not expose contact data statically.
- The 2021–2022 international booklet cannot establish current costs, deadlines, or policies.
- The noticeboard needs admission-only filtering.
- Department admission routes may show stale/default dates and require change detection.
- Robots guidance and terms must be reviewed immediately before Phase 4.

## Stable behavior versus changing facts

Fine-tuning should teach stable behavior: DIU identity, terminology, clarification, refusal, uncertainty, multilingual response patterns, and evidence-aware structure.

RAG should supply changing facts: tuition, deadlines, notices, requirements, scholarships, waivers, and policy versions. Missing or conflicting current evidence should produce insufficient information and an official verification path.
