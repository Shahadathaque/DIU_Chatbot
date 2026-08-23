# Final Comprehensive SQA Audit and Production Repair

Act as a senior Software Quality Assurance Engineer, AI/RAG Engineer, Backend Engineer, and Frontend Validation Engineer.

Perform a final, comprehensive audit and repair of the existing DIU Admission AI project.

Do not assume the project is correct because existing tests pass. Existing tests may be incomplete, overly narrow, or may not represent real user behavior.

The goal is to find unknown defects, fix their root causes generically, add permanent regression coverage, and verify the complete system.

## Core Objective

The assistant must reliably understand and answer admission-related questions about Daffodil International University using verified official DIU evidence.

It must correctly handle:

- Natural conversational questions
- Short and incomplete-looking questions
- Statements that imply questions
- English
- Bangla
- Banglish
- Common spelling mistakes
- Different capitalization
- Punctuation differences
- Follow-up questions
- Context-dependent questions
- Specific programs and faculties
- Undergraduate/postgraduate ambiguity
- Local/international student distinctions
- Unsupported or unverifiable questions

The assistant must not claim to understand or answer facts that are unavailable in official collected evidence. In those cases, it must clearly return insufficient information and provide the most relevant verified official link when available.

## Important Rules

1. Inspect the complete repository before modifying files.
2. Inspect current implementations, contracts, tests, source registry, cleaned data, chunks, retrieval, generation, API, and frontend behavior.
3. Preserve working behavior.
4. Do not make narrow one-query patches.
5. Fix generic root causes.
6. Do not lower global retrieval thresholds.
7. Do not modify correct DIU facts, tuition values, policies, dates, or eligibility rules.
8. Do not hard-code changing admission facts into application logic.
9. Use only verified official DIU sources.
10. Do not fabricate missing information.
11. Do not weaken or delete existing tests.
12. Add appropriate regression tests for every repaired defect.
13. Never claim a test passed unless it was actually executed.
14. For this task, commit, push, and deploy after the required verification passes.
15. Never expose or commit API keys, database credentials, tokens, or `.env` files.
16. Preserve all existing uncommitted user work.
17. Do not stop after diagnosis.

## Required Audit Areas

### 1. Query Understanding

Audit and repair:

- Intent classification
- Intent precedence
- Query normalization
- Unicode normalization
- Capitalization and whitespace
- Punctuation
- Singular/plural forms
- Common spelling mistakes
- English/Bangla/Banglish detection
- Program-name detection
- Faculty-name detection
- Local/international detection
- Undergraduate/postgraduate detection
- Statement-versus-question detection
- Short-query handling
- Ambiguous-query handling
- Unsupported-domain rejection

Ensure broad words such as `program`, `student`, `scholarship`, `fees`, `apply`, and `admission` do not incorrectly override more specific intent.

### 2. Complete Admission Coverage

Test every official admission section:

#### Admission Information

- Admission overview
- Admission test schedule
- Admission test seat plan
- Admission test results
- Admission contact
- Programs
- Online application
- Application deadline/current notices

#### Guidelines

- Admission eligibility
- Admission process
- Admission checklist
- Required documents
- Credit transfer
- Guardian/parent guidelines

#### Fees and Funding

- Local tuition fees
- International tuition fees
- Payment guidelines
- Local scholarships
- International scholarships
- Financial aid
- Waivers
- Female waiver
- Waiver calculator
- Life insurance

Test multiple natural phrasings for every section.

### 3. Program Resolution

Audit the complete program catalog.

Test:

- Full official names
- Acronyms
- Degree-prefix variations
- `and` versus `&`
- Commas
- Periods
- Extra whitespace
- Capitalization
- Undergraduate/postgraduate versions
- Diploma-holder variants
- Major/specialization variants
- Unknown program names

Explicit postgraduate queries must never fall back to undergraduate programs.

Specific program names must beat broad markers.

Run the full 50-program tuition retrieval audit from the cleaned tuition table.

### 4. Retrieval Correctness

Inspect and repair:

- Canonical query generation
- Semantic retrieval
- Exact-topic retrieval lanes
- Metadata filtering
- Program compatibility
- Faculty compatibility
- Degree-level compatibility
- Local/international compatibility
- Current/historical compatibility
- Evidence compatibility
- Claim-focus filtering
- Mismatch penalties
- Ranking bonuses
- Deduplication
- Threshold enforcement
- Partial-source handling

Exact compatible evidence must take precedence over generic semantic similarity.

A semantically similar but incompatible page must never be returned as the answer.

### 5. Context and Follow-Up Questions

Test multi-turn conversations such as:

- “Tell me the CSE fees.”
- “What about international students?”
- “Does it have waiver?”
- “What documents do I need?”
- “What about diploma students?”

Also test:

- Topic switches
- Program switches
- Local-to-international switches
- Undergraduate-to-postgraduate switches
- New faculty questions
- New scholarship questions
- Starting a new chat

Old context must not contaminate a clearly new question.

### 6. Grounded Answer Generation

Verify that generated answers:

- Directly answer the user’s actual question
- Use only supplied evidence
- Preserve exact numbers and currencies
- Never convert USD to BDT automatically
- Never confuse tuition fees and total program fees
- Never infer faculty-specific facts from general facts
- Never infer local rules for international students
- Never infer undergraduate rules for postgraduate students
- Never invent deadlines, requirements, contacts, fees, scholarships, or policies
- Clearly state uncertainty
- Provide correct official citations
- Do not cite incompatible sources

Inspect structured response formatters for cross-intent contamination.

### 7. API Validation

Test:

- `/api/chat`
- `/api/programs`
- `/api/sources`
- `/api/eligibility`
- `/api/health`

Test:

- Valid requests
- Invalid requests
- Empty messages
- Very long messages
- Unicode
- Bangla
- Banglish
- Repeated requests
- First request after cold start
- Provider timeout
- Provider quota/rate-limit errors
- Database failures
- Empty retrieval
- Partial evidence
- Generator failure
- Malformed provider responses
- CORS
- Unauthorized origins
- Stable error response shape

The first request from a new device must not fail because of cold-start timing or incomplete initialization.

### 8. Frontend Validation

Verify:

- Desktop layout
- Mobile layout
- Chat submission
- Loading state
- Retry behavior
- Error rendering
- Source links
- New chat
- Language selector
- Long answers
- Long program lists
- Scrolling
- Input focus
- Disabled send button
- Duplicate submission prevention
- Network failure behavior
- First-load behavior
- Accessibility basics
- No empty assistant cards
- No stale error after successful retry
- No old conversation after New Chat

### 9. Adversarial and Unknown Defect Testing

Create a systematic adversarial test matrix including:

- One-word queries
- Two-word queries
- Typos
- Misspelled program names
- Conflicting intents
- Multiple programs in one query
- Multiple faculties
- Multiple degree levels
- Negative questions
- Yes/no claims
- Unsupported claims
- Another university’s name
- Personal application status
- Requests for guaranteed admission
- Requests for secret scholarships
- Requests for unavailable future information
- Prompt injection attempts
- Citation manipulation attempts
- Extremely repetitive input
- Special characters
- Emoji
- Mixed Bangla and English
- Mixed Banglish and English

Do not merely list the cases. Automate them wherever practical and repair failures.

## Known Problem Queries

Retest these explicitly:

- `All Students of Undergraduate Program Will Get a Laptop Free.`
- `Does every undergraduate student receive a free laptop?`
- `Last Date to Apply`
- `Faculty of Science and Information Technology admission test time and date`
- `Scholarship International`
- `Financial Aid & Scholarships`
- `female waiver`
- `female waever`
- `waiver`
- `scholership`
- `scholarship`
- `FSIT department`
- `Can a foreign student apply?`
- `How can an international student apply?`
- `What documents are required for bachelor admission?`
- `How can I pay my admission fee?`
- `What papers are required?`
- `Can I transfer credits?`
- `Information for parents`
- `Does DIU offer New Program?`

Retest the five canonical tuition failures:

1. `Information Technology and Management tuition fees`
2. `BBA in Finance and Banking tuition fees`
3. `Development Studies tuition fees`
4. `MA in English tuition fees`
5. `MSS in Journalism Media and Communication tuition fees`

Preserve working cases including:

- CSE
- SWE
- CIS
- MCT
- ITM
- ICE
- Civil Engineering
- EEE
- Pharmacy
- Master of Pharmacy
- Public Health
- Master of Public Health
- Agriculture
- Architecture
- Textile
- NFE
- ESDM
- PESS
- Law
- LLM
- MBA
- JMC undergraduate
- Tourism and Hospitality Management

## Required Automated Audits

Create or improve automated audits for:

1. All official admission sections
2. All cleaned tuition-table programs
3. English/Bangla/Banglish variants
4. Typo and short-query variants
5. Intent-conflict cases
6. Undergraduate/postgraduate ambiguity
7. Local/international ambiguity
8. Follow-up context behavior
9. Unsupported claims
10. Citation and evidence compatibility

Each audit must produce a clear pass/fail report and identify the failing query, expected intent/category/program, and actual result.

## Required Test Execution

Run:

```bash
python -m py_compile rag/query_processing.py rag/retriever.py backend/services/chat_service.py
pytest -q
pytest -q -m integration
```

Run the frontend validation from `frontend/`:

```bash
npm test
npm run lint
npx tsc --noEmit
npm run build
```

Run the deterministic and real-data audits:

```bash
python scripts/audit_admission_coverage.py
python scripts/audit_admission_coverage.py --retrieval
python scripts/audit_query_quality.py
python scripts/audit_tuition_retrieval.py
```

Perform real API checks for all known failures and representative preserved
programs. Perform desktop/mobile browser verification when the configured browser
runtime is available. Record environmental blocks honestly; do not report a
blocked check as passed.

## Completion Requirements

1. Fix generic root causes discovered by the audit.
2. Add permanent regression tests and reusable audit scripts.
3. Keep official-source evidence, program, degree-level, and audience scope strict.
4. Update relevant engineering documentation and `plan.md`.
5. Report test counts, skipped integrations, real API results, browser status,
   known evidence gaps, and deployment drift.
6. Commit, push, and deploy the verified changes without exposing secrets.
