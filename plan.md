# DIU Admission AI — Execution Plan

## 1. Goal

Complete the **DIU Admission AI** project as quickly as possible while keeping its
core research promise intact: a usable prototype (chat + eligibility + programs +
sources) backed by retrieval over official DIU sources, with honest citations and
clear uncertainty. Research experiments (base vs. fine-tuned × with/without RAG)
are sequenced after the working prototype so the project has a demonstrable product
early.

## 2. Current state (verified by reading the repo)

| Area | Status |
| --- | --- |
| Scraping (Phase 4) | Done — registry-driven, robots/rate-limit respecting, 18 audited sources |
| Cleaning (Phase 5) | Done — traceable cleaned v2 records, validation passes |
| RAG chunking | Done — `rag/chunker.py`, integrity-checked manifest, tables + PDF pages |
| Embeddings | Done — `intfloat/multilingual-e5-base` (768-d) via `rag/embeddings.py` |
| Vector store | Done — pgvector (production) + JSON/in-memory (dev/test) |
| Retrieval | **TASK-DEMO hardened** — domain/authority/dedup plus follow-up program/topic context, program/degree pinning, local-vs-international fee separation, and structured fact compatibility |
| Backend API | **TASK-01 done** — `/api/chat`, `/api/programs`, `/api/sources` live against the existing retriever + local KB; `/api/eligibility` was contract-only until TASK-03 |
| LLM generation | **TASK-02 + TASK-DEMO done** — grounded Qwen generation; deterministic rendering protects tuition-table labels and SSC/HSC waiver rows from small-model unit/column errors |
| Eligibility engine | **TASK-03 done** — `eligibility/` deterministic rule engine (R-001 program registry, R-002 diploma pathway); `POST /api/eligibility` live; returns `insufficient_information` where official evidence cannot establish eligibility |
| Frontend | **TASK-04 + TASK-DEMO done** — real backend wiring plus six-turn chat history in normal and retry payloads; CORS, program-driven eligibility dropdown, backend errors, and mocks retained |
| Fine-tuning | **Not started** (research phase) |
| Evaluation | **M5 done (TASK-05A + M5-B)** — held-out v1 dataset (150 q), deterministic metrics, retrieval Recall@K/Precision@K/MRR, eligibility real+synthetic tiers, base vs base+RAG generation at temperature=0.0; report at `results/evaluation/v1/report.md` |
| Reproducible setup | **TASK-06 done** — one bootstrap command, checksum/provenance artifact checker, offline unit-test default, explicit integration marker, and validation-before-model safeguards |
| Frontend deployment | **TASK-07 done** — environment-based API URL, Vercel build configuration, and Web Analytics integration |
| Backend deployment | **TASK-08 done** — production environment variables, external endpoint settings, PostgreSQL/CORS configuration, and startup validation |
| Request validation | **TASK-09 done** — contract-shaped 422 handling, validation-before-dependency tests, and explicit read-only endpoint semantics |
| Production health | **TASK-10 done** — safe startup diagnostics, production validation logging, detailed `/api/health` checks, and restart/monitoring documentation |
| Vercel CORS | **TASK-11 done** — exact multi-origin parsing, credentials/preflight verification, unauthorized-origin rejection, and deployment troubleshooting documentation |
| Frontend verification | **TASK-12 done** — Vitest, TypeScript, ESLint, production build, dependency audit, clean-install dry run, and dev-server verification |
| Backend verification | **TASK-13 done** — offline unit suite, focused API/core/RAG/eligibility checks, coverage report, model-free validation, and isolated-environment verification |
| Production optimization | **TASK-15 implementation complete** — hosted-generator configuration alignment, SSE chat route, static endpoint TTL caches, optional pooled PostgreSQL, liveness/readiness probes, production rate limiting, optional Sentry hook, and opt-in cross-encoder reranking. Provider deployment, secrets, and pgvector population remain operator actions. |
| v2 artifact recovery | **TASK-16 done** — recollected and validated all 18 registered official sources, restored the 52-row program catalog, rebuilt 264 chunks, and populated the Neon pgvector index. |
| Hosted deployment runtime | **TASK-17 done** — Neon-backed runtime program/source catalogs, hosted OpenAI-compatible embeddings, strict production backend selection, slim container requirements, and Render deployment blueprint. Neon catalog is populated; provider key, hosted-vector rebuild, and external deploy remain operator actions. |

## Deployment Status

### Completed

- TASK-07: Frontend environment setup ✅
- TASK-08: Backend environment configuration ✅
- TASK-09: Request validation (422 responses) ✅
- TASK-10: Production startup and health check ✅
- TASK-11: CORS configuration ✅
- TASK-12: Frontend test verification ✅
- TASK-13: Backend test verification ✅
- TASK-14: Deployment documentation ✅
- TASK-15: Production optimization implementation ✅ (deployment pending)
- TASK-16: Complete v2 knowledge base and Neon pgvector population ✅
- TASK-17: Neon runtime catalog and hosted backend preparation ✅ (provider deployment pending)

### Current

The Neon runtime catalog is populated with 52 programs and 18 official sources.
The lightweight hosted backend is prepared, but chat deployment requires a
provider API key, rebuilding the 264 chunks into the configured hosted embedding
table, and performing the provider deployment.

### Next

Create the hosted-model key, rebuild the hosted embedding table, deploy the
backend from `render.yaml`, set the Vercel API URL/CORS origin, and run the
post-deployment checks before beginning further research work.

### Key gaps blocking a complete product
1. ~~No chat endpoint — the retriever exists but is never called from the API.~~ **Resolved in TASK-01** (`/api/chat` now calls the retriever).
2. ~~No generator — no LLM turns retrieved chunks into an answer.~~ **Resolved in TASK-02** (grounded Qwen generation; evidence-summary remains the fallback).
3. ~~No eligibility rules — contract defines `POST /api/eligibility` but no rule engine exists.~~ **Resolved in TASK-03** (deterministic engine; honest `insufficient_information` where official evidence is missing).
4. ~~No programs/sources endpoints — data exists in cleaned records but is not served.~~ **Resolved in TASK-01** (programs + sources now served).
5. ~~Frontend never talks to the real backend (mock mode default).~~ **Resolved in TASK-04** (real-API mode + CORS + unique program ids).

## 3. Execution milestones

### M0 — Baseline sanity (done)
- [x] Create venv, `pip install -r requirements.txt`, copy `.env.example` to `.env`.
- [x] Run `pytest` and fix any failures. **Result: 105/105 pass.**
- [ ] Run `python scripts/build_knowledge_base.py --dry-run` against the cleaned snapshot. **BLOCKED: snapshot absent (see M0.5).**
- [x] Decide vector backend: `pgvector` (needs Postgres) or `local` JSON store for dev speed. **Chose `local` (RAG_VECTOR_BACKEND=local) for M1–M4.**

### M0.5 — Data availability (prerequisite, added by audit)
The cleaned dataset is NOT present locally (`data/cleaned/v1` empty; gitignored). The
retriever cannot return evidence until it exists.
- [x] Restore `data/cleaned/v1` from backup OR re-run collection:
  `python scripts/scrape_diu.py` → `python scripts/clean_dataset.py`.
  **Decision (user): re-run collection pipeline. Result: 18/18 sources, 0 failures.**
- [x] Install browser: `playwright install chromium`. **Done.**
- [x] Build the local index: `python scripts/build_knowledge_base.py` (local JSON store). **221 chunks indexed.**
- [x] Verify: `python scripts/search_knowledge.py "What documents are required for DIU admission?"` **Works; Bangla query works; out-of-domain (NSU) correctly rejected; 105 tests pass.**

### M1 — Backend API layer (prototype core)
Deliverable: all four contract endpoints working against the existing retriever + data.
- [x] `POST /api/chat` — domain gate → `Retriever.retrieve()` → format evidence → return `answer/sources/confidence/language`. Initial "answer" can be evidence-summary until M2 adds a real LLM. **Done in TASK-01** (evidence-summary; no LLM yet).
- [ ] `POST /api/eligibility` — deterministic rule engine (see M3) returning `eligible / not_eligible / insufficient_information`. **Deferred to M3 — explicitly out of scope for TASK-01.**
- [x] `GET /api/programs` — serve program list derived from cleaned `undergraduate_programs` records/chunks. **Done in TASK-01.**
- [x] `GET /api/sources` — serve source list from cleaned records. **Done in TASK-01.**
- [x] Error model: stable `{"error": {code, message, details}}` shape per contract; 400/422/500/503 mapping. **Done in TASK-01.**
- [x] Tests for every endpoint (httpx/pytest) matching the contract. **Done in TASK-01: 19 new API tests; full suite 124 passed.**

### M2 — LLM generation
Deliverable: chat returns real generated answers grounded in retrieved evidence.
- [x] `rag/generator.py` — configurable generator interface (protocol), like `embeddings.Embedder`. **Done in TASK-02.**
- [x] Implement a lightweight local adapter (transformers, ~1–4B multilingual, e.g. Qwen-family) **and/or** an OpenAI-compatible API adapter behind the same interface. **Done in TASK-02: `LocalGenerator` (default `Qwen/Qwen2.5-1.5B-Instruct` on Apple MPS, lazy load, chat template, optional LoRA path) + `OpenAICompatibleGenerator` (httpx only), selected by `GENERATOR_BACKEND`.**
- [x] Prompt construction: injected evidence chunks + source citations + "refuse/uncertainty" instructions; Bangla/Banglish handled via prompt + language field. **Done in TASK-02: `build_grounded_messages` in `chat_service.py`.**
- [x] Guardrails: no evidence → answer with low confidence + insufficient-information, per hallucination-control policy. **Done in TASK-02: generator never called without eligible evidence or for out-of-domain queries; sources always from retrieval; empty generated answer falls back to evidence summary; generator failure → 503.**

### M3 — Deterministic eligibility engine
- [x] `eligibility/` package: versioned, source-linked rules (R-001 recognized-program registry, R-002 documented diploma pathway) derived from collected official sources. **Done in TASK-03.**
- [x] Rules must be data-driven (JSON) not hard-coded prose; each rule carries a source URL. **Done in TASK-03** (`rules/eligibility_rules.v1.json` + `rules/programs.v1.json`; every rule/program carries `https://` references).
- [x] Engine returns status + reason + source; LLM may only explain, never override. **Done in TASK-03** (`POST /api/eligibility`, deterministic only; source via registry; additive `rule_matches`/`evidence_gaps`).

### M4 — Frontend integration
- [x] Set `NEXT_PUBLIC_USE_MOCK_API=false` once endpoints are live. **Done in TASK-04** (`frontend/.env.local`, gitignored; `.env.example` stays `true` for dev/tests).
- [x] Verify chat, eligibility form, and programs pages against real API; keep mocks for tests. **Done in TASK-04** — real-API verification for chat (en/bn/banglish), eligibility (recognized + unknown), programs (10 unique ids); mock fixtures + tests retained.
- [x] Frontend unit tests still green (`npm test`). **Done in TASK-04** — 11 passed (mock + new real-mode API-client tests).

### M5 — Baseline evaluation (research)
- [x] Build held-out question set (en/bn/banglish) + golden answers. **Done in TASK-05A** (`data/evaluation/questions.v1.json`, 150 questions, schema-validated, provenance-checked, 226 tests pass).
- [x] Retrieval Recall@K against held-out queries. **Done in M5-B** — offline Recall@1/3/5/10, Precision@K, MRR vs `gold_chunk_ids`; in-domain reported separately from OOD rejection.
- [x] Eligibility correctness over boundary cases. **Done in M5-B** — real tier (v1 non-decisive ruleset, `insufficient_information` honest) + synthetic decisive fixture tier, reported separately.
- [x] Deterministic scoring of base LLM vs base LLM + RAG on correctness, groundedness, hallucination, domain adherence. **Done in M5-B** — same Qwen2.5-1.5B-Instruct, same questions, `temperature=0.0`, deterministic metrics (no LLM judge); `summary.json` + `report.md` in `results/evaluation/v1/`.

### M6 — Fine-tuning (research, stretch)
- [ ] Build fine-tuning dataset from cleaned records (QA + refusal + clarification pairs).
- [ ] LoRA/QLoRA on the chosen base model; record revision/seed/hyperparameters.
- [ ] Evaluate four systems: base, fine-tuned, base+RAG, fine-tuned+RAG.
- [ ] Honest positive/negative findings reported.

### M7 — Reporting & wrap-up
- [ ] Update docs: architecture, evaluation report, readiness decisions.
- [ ] Keep plan.md in sync with everything above (see Change log).

## 4. Recommended ASAP path (pick one)

- **Recommended (default): Path A — "Prototype-first, research after."**
  M0 → M1 → M2 (local small LLM) → M3 → M4 → M5 → M6 (if time) → M7.
  Best because: a complete, demonstrable product exists by end of M4; evaluation M5
  gives the research numbers; fine-tuning M6 is the only true long-pole and can be
  cut or run in parallel with reporting.
- **Path B — "Research-first"** (full four-system experiments before any API wiring).
  Higher academic fidelity but slowest to a working product and worst for "ASAP".
- **Path C — "Minimal vertical slice"** (one chat flow + one eligibility rule end-to-end,
  then expand). Fastest demo, but rework risk when generalizing endpoints.

## 5. Key decisions to make at kickoff
1. Vector backend for dev: **local JSON store** (fast, no infra) vs pgvector (production parity). Recommend local for M1–M4, pgvector for M5+.
2. LLM for chat: **local 1–4B open model** (free, offline, matches research) vs hosted API (fastest to wire, but adds cost/network and weaker research control). **RESOLVED in TASK-02: local `Qwen/Qwen2.5-1.5B-Instruct` on Apple MPS behind a configurable `Generator` protocol; OpenAI-compatible httpx adapter available via `GENERATOR_BACKEND=openai`. bitsandbytes is unsupported on Apple Silicon, so M6 fine-tuning uses LoRA/bf16, not QLoRA.**
3. Rule source for eligibility: **RESOLVED in TASK-03** — the collected official DIU sources (programs grid, BBA record, admission notice, waiver policy) do NOT publish minimum GPA, combined GPA, group/subject, or program-specific thresholds. So v1 rules encode only the defensible structural rules (recognized program + documented diploma pathway) and the engine returns `insufficient_information` for anything not provable from official sources. Waiver percentages are financial-aid criteria, not eligibility thresholds, and were NOT converted into rules. Future thresholds (if official sources ever publish them) must enter through the knowledge pipeline, never hard-coded into the LLM.

## 6. Engineering conventions
- Follow existing patterns: dataclasses for models, Protocol for injectable services,
  pydantic settings via env, integrity checks (hash-verification) before mutation.
- Backend owns all decision logic; frontend renders only (per contract + AGENTS.md).
- Never commit `.env`, tokens, DB credentials, weights, or generated datasets.
- Sole developer: no member-ownership boundaries (per AGENTS.md). All files are the
  developer's to modify; the frontend/backend split is architectural, not ownership.
- Every change outside this plan updates the plan's Change log below with the reason.

---

## Change log

_Every time something is changed/added/removed during execution (code, data, config,
scope), record it here with a short reason._

- **2026-08-14** — Plan created from a full repo walkthrough (scraper, cleaning, rag,
  backend, frontend, contracts, docs). Reason: user requested a written plan before
  execution and a running record of all subsequent decisions/changes.
- **2026-08-14** — Current-state audit run (controlled-execution mode). Findings:
  env installed (Python 3.11.16 + venv + pinned deps, 105 tests pass); all data
  directories are empty so the retriever has nothing to index; backend endpoints,
  LLM, eligibility, fine-tuning, evaluation unfinished. Reason for changes: audit
  surfaced a hard data-availability blocker not covered by the original plan and
  AGENTS.md declares a sole developer (member-ownership wording was obsolete).
  Approved actions applied: added M0.5 "Data availability" milestone, rewrote §6,
  marked M0 items done. Data path approved by user: **re-run collection pipeline.**
- **2026-08-14** — M0.5 executed. Collection: 18/18 sources OK (14 HTML, 4 PDFs, 0
  failed; run manifest `data/raw/runs/run-20260813t185230191079.json`). Cleaned v1:
  18 records, 18 structured tables, 0 failed extractions (validated 18/18). Local
  index: 221 chunks stored at `data/chunks/local_knowledge_base.json`. Verified:
  English + Bangla queries return evidence, out-of-domain (NSU) correctly refused,
  105/105 tests still pass. Reason: prerequisite for any backend work; retriever had
  no data before this. Next: TASK-01 (Backend API Foundation) is unblocked.
- **2026-08-14** — TASK-01 (Backend API Foundation) completed. Implemented
  `POST /api/chat` (domain gate → existing `Retriever.retrieve()` → evidence-summary
  response with `answer/sources/confidence/language`, safe insufficient-information
  handling), `GET /api/programs`, `GET /api/sources`, and the contract error model
  (`{"error": {code, message, details}}` with 400/422/500/503 handlers). TASK-01 was
  completed using the **existing retriever and local DIU knowledge base** — no new
  retrieval/RAG code, no LLM, no eligibility rules, no frontend changes, no secrets.
  Tests: 19 new API tests; full suite 124 passed; real-data smoke tests passed.
  Reason: TASK-01 scope was backend API integration only; LLM generation is deferred
  to TASK-02 and eligibility rules to M3.
- **2026-08-14** — TASK-02 (LLM generation) completed. Pre-implementation audit on the
  MacBook Air M4 (16 GB, MPS available) approved a configurable `Generator` protocol
  (`rag/generator.py`) with a local Transformers adapter (`LocalGenerator`, default
  `Qwen/Qwen2.5-1.5B-Instruct`, lazy load, chat template, `torch.inference_mode()`,
  optional LoRA adapter path reserved for M6) and an OpenAI-compatible httpx adapter
  (`OpenAICompatibleGenerator`), selected by `GENERATOR_BACKEND`. `ChatService` now
  injects the generator, builds a grounded prompt (evidence + source info + requested
  language + refusal/uncertainty instructions), never calls the generator without
  eligible evidence or for out-of-domain queries, returns sources from retrieval only,
  and maps generator failures to 503. `.env.example` extended. Tests: 31 new
  (protocol/factory, mocked local + OpenAI-compatible adapters, FakeGenerator chat
  integration); full suite 155 passed. Real-model verification on MPS: grounded English
  answer, no hallucinated URLs, official source returned; Bangla query accepted
  (answered in English — small-model limitation); out-of-domain query did not call the
  generator. Reason: LLM generation was the only remaining core prototype gap; the
  decision preserves the four-system research design (base/fine-tuned × ±RAG) and keeps
  everything free/local.
- **2026-08-14** — TASK-03 (Deterministic Eligibility Engine) completed. Pre-implementation
  audit confirmed the collected official DIU sources (DIU-PROG-001 programs grid,
  DIU-PROG-002 BBA, DIU-NOT-002 admission notice, DIU-WAV-001 waiver policy) publish NO
  minimum SSC/HSC GPA, combined GPA, group/subject, or program-specific thresholds, so
  any GPA/group rules would be invented. Implemented `eligibility/` (pure, no LLM/DB/
  network): `models.py` (status/decision enums, `ProgramRegistry`), `loader.py` (strict
  JSON validation, canonical sha256 content hash, `RulesetLoadError`, versioned paths),
  `engine.py` (evaluators for `program_registry`, `diploma_pathway`, generic
  `numeric_range` used only by test fixtures; decision precedence: decisive fail →
  `not_eligible`, missing input → `insufficient_information`, non-decisive ruleset →
  `insufficient_information`, `eligible` only under a decisive ruleset). Versioned rules:
  `rules/eligibility_rules.v1.json` (`eligibility-rules-v1`, `decisive:false`, R-001
  recognized-program registry, R-002 documented diploma pathway, 7 evidence gaps,
  provenance) + `rules/programs.v1.json` (10 programs). Backend: `POST /api/eligibility`
  with contract `status/reason/source` plus additive `rule_matches`/`evidence_gaps`
  evidence; `EligibilityRequest` validates program/group non-blank, GPA in 0.0–5.0,
  `diploma` required. Because the v1 ruleset is non-decisive, a complete applicant
  (e.g. CSE 5.0/5.0 Science) returns `insufficient_information` honestly; unknown
  programs also return `insufficient_information` (registry is incomplete, so absence
  is not proof). Tests: 35 new (engine unit + API, incl. decisive fixture rulesets);
  full suite 190 passed; endpoints + OpenAPI verified. Reason: TASK-03 scope was the
  deterministic engine only; frontend wiring is M4, research comparisons are M5/M6.
- **2026-08-14** — TASK-04 (Frontend real-API integration) completed. Backend: added
  `CORSMiddleware` (env-configurable `CORS_ORIGINS`, default `http://localhost:3000`;
  GET/POST/OPTIONS; Content-Type) and fixed a genuine contract bug where multiple SWE
  programs received duplicate ids — `ProgramsService._program_id` now derives
  deterministic, unique, registry-aligned ids from the program name (e.g.
  `swe-cyber-security`, `swe-data-science`) instead of duplicating `swe`. Frontend:
  created gitignored `frontend/.env.local` with `NEXT_PUBLIC_USE_MOCK_API=false` (the
  `.env.example` default stays `true` for dev/tests); `EligibilityForm` now loads its
  program dropdown from `GET /api/programs` (id→value, name→label, loading/error
  states, submit disabled until programs load) instead of a hardcoded 8-item list;
  `services/api.ts` now parses the backend `{error:{code,message,details}}` envelope
  and surfaces the backend's message instead of a generic HTTP message. Tests: backend
  6 new (CORS headers + preflight + disallowed origin + unique/stable ids incl. real
  cleaned data) → 196 passed; frontend 7 new real-mode API-client tests (URL, JSON
  body, error-envelope parsing, generic fallback, timeout/abort, reachability) using a
  mocked `fetch` — mocks never require a live server. Real E2E verified via uvicorn +
  `npm run dev`: landing/chat/eligibility/programs all 200; chat grounded in English,
  Bangla, and Banglish with real sources; out-of-domain question safely refused;
  recognized (cse) and unknown (eee) eligibility both return honest
  `insufficient_information`; programs page returns 10 unique ids with no duplicate
  React keys; CORS headers present. `npm test` 11 passed, `typecheck`, `lint`, and
  `build` all clean. Reason: TASK-04 scope was frontend↔backend integration only;
  evaluation (M5) and fine-tuning (M6) remain untouched.
- **2026-08-14** — TASK-05A (M5 held-out evaluation dataset) completed. Created
  `evaluation/schema.py` (dataclasses `EvalQuestion`/`EvalDataset`, strict loader +
  validator, deterministic canonical sha256 `content_hash`, provenance checks against
  `data/cleaned/v1/manifest.json` + KB chunks, per-language duplicate-text detection,
  and the M6 anti-reuse mechanism `question_hashes()` /
  `assert_no_overlap_with_finetuning()`) plus `evaluation/__init__.py` and
  `tests/test_eval_schema.py` (30 tests). Authored `data/evaluation/questions.v1.json`
  (150 questions, schema_version 1.0, version 1.0.0, `held_out:true`,
  `dataset_usage:"held_out_eval"`): 40 in-domain English + 40 natural Bangla + 40
  natural Banglish (human-authored, not machine-translated) across 10 KB categories
  (waivers, tuition_and_fees, international_admission, undergraduate_programs,
  scholarships, required_admission_documents, admission_overview,
  admission_contact_information, admission_process, admission_application_process);
  10 out-of-domain/refusal (NSU/BRAC/EWU/IUB/UIU/Dhaka Univ + non-admission topics,
  no sources, `expected_outcome:refuse`); 10 real eligibility cases (all
  `insufficient_information` per the non-decisive v1 ruleset); 10 synthetic
  eligibility fixture cases clearly marked `is_synthetic:true` with
  `SYNTHETIC-FIXTURE` source, never presented as real DIU policy. Every in-domain
  golden answer is grounded in verified KB chunks (default-eligible only:
  `current_date_sensitive`/`stable_reference`, extraction success, no manual_review);
  the only non-eligible chunk originally drafted (`74e45667` outbound exchange,
  `uncertain`) was replaced with an eligible international-contact chunk
  (`f6ac206d`). Tests: `pytest -q tests/test_eval_schema.py` 30 passed; full suite
  `pytest -q` 226 passed. Reason: TASK-05A scope is the held-out dataset + its schema
  only; metrics, retrieval/generation/eligibility evaluation, and report generation
  are M5-B, and the dataset is deliberately excluded from M6 fine-tuning.
- **2026-08-14** — M5-B (M5 baseline evaluation harness) completed. Implemented the
  deterministic evaluation infrastructure only — no production behavior or frontend
  changes: `evaluation/metrics.py` (normalized exact match, token F1, ROUGE-1/2/L,
  verbatim snippet containment, groundedness proxy, hallucination n-gram proxy,
  fabricated-citation check, refusal/domain-adherence, language-adherence proxy,
  latency helpers, Recall@K/Precision@K/MRR); `evaluation/retrieval_eval.py` (offline
  retrieval vs local KB, in-domain vs OOD reported separately);
  `evaluation/eligibility_eval.py` (real v1 tier + decisive synthetic fixture tier,
  reported separately); `evaluation/generation_eval.py` (condition=base = plain
  prompt without evidence; condition=rag = Retriever →
  `ChatService.build_grounded_messages` → Generator; same Qwen/Qwen2.5-1.5B-Instruct,
  same questions, `temperature=0.0`); `evaluation/report.py` (`summary.json` +
  `report.md`); `evaluation/run_all.py` (one-command driver). Tests:
  `tests/test_eval_metrics.py` (metrics), `tests/test_eval_eligibility.py`,
  `tests/test_eval_generation.py` (fake retriever/generator; no model downloads);
  `pytest -q tests/test_eval_schema.py` + `pytest -q tests/test_eval_metrics.py`
  green; full suite 293 passed. Full evaluation executed on MPS
  (`python -m evaluation.run_all --max-new-tokens 192`): retrieval Recall@1 .336 /
  @3 .533 / @5 .605 / @10 .648, MRR .455, OOD rejection 0.70; eligibility real 10/10
  (insufficient_information honest), synthetic 9/10 (elig-syn-09 is a documented
  dataset annotation gap: its machine-readable `fixture_rule`+input cannot express
  the second numeric rule its question text names — reported, NOT silently fixed);
  base vs rag at temperature=0.0: RAG improved token F1 .174→.240, ROUGE-L .141→.196,
  verbatim containment .029→.079, groundedness 0→.153, hallucination proxy 1.0→.847,
  domain adherence .758→.867, but **hurt Bangla language adherence .963→0** because
  the evidence is English-only and the 1.5B model follows the evidence language;
  base OOD refusal 0.6 vs rag 0.7; 1 fabricated citation in rag (en-37, DIU root URL
  not among retrieved sources). Honest findings recorded in
  `results/evaluation/v1/report.md`; no questions.v1.json or gold_chunk_ids changed;
  no LLM judge or paid API used. Reason: M5-B scope is the deterministic evaluation
  harness only; fine-tuning (M6) and the four-system comparison remain untouched.- **2026-08-14** — Product readiness fixes for the functional demo (NO M6/research).
  Audit of the RAG chat pipeline for answerable questions (waiver/tuition/admission
  process/required documents/scholarships) found three root causes: (1) the frontend
  15s `REQUEST_TIMEOUT_MS` was shorter than local Qwen2.5-1.5B generation (11–34s on
  MPS), causing user-facing timeouts; (2) for structured-data questions (waivers,
  tuition, scholarships) the retriever ranked jumbled raw `text` PDF page-fragments
  above the reliable `table` extracts — the cleanest chunk stating "GPA-5 both in SSC
  and in HSC | 25% | 3.00" was suppressed entirely by similarity/`jaccard` dedup, so
  the 1.5B model received messy evidence and either refused or hallucinated (e.g. it
  invented CAT/JEE and claimed "no GPA-based waiver"); (3) the grounded prompt did not
  force concise exact-value extraction, so rambling output inflated latency and
  variance (the waiver answer flip-flopped between rows at temperature=0.3). Fixes
  applied: `frontend/services/api.ts` `REQUEST_TIMEOUT_MS` 15s → 90s (exported;
  timeout test updated to use it); `rag/retriever.py` `_metadata_bonus` now gives
  `content_type=="table"` chunks a +0.05 preference when the query has structured-data
  intent (waiver/scholarship/tuition/fee/cost, incl. Bangla) so clean evidence
  outranks jumbled fragments (waiver top-5 is now all clean table chunks); grounded
  prompt in `backend/services/chat_service.py` now asks for concise, direct use of the
  exact values in the evidence while keeping the test-asserted substrings; default
  `generator_temperature` 0.3 → 0.0 (greedy) for deterministic, grounded demo answers,
  consistent with the M5 evaluation methodology (tests + `.env.example` updated).
  Regression tests added: `tests/test_rag_retrieval.py::test_waiver_query_ranks_clean_table_chunks_above_messy_text_fragments`
  and `tests/test_api_chat_generated.py::test_generated_waiver_chat_uses_concise_extraction_prompt`.
  Verification: backend suite 295 passed; frontend vitest 11 passed; live
  `uvicorn` + curl through the real local Qwen generator across en/bn/banglish —
  waiver ("50% for Golden GPA-5 both SSC and HSC"), tuition (B.Sc. CSE international
  Total Tuition $7,847; M.Sc. CSE international Total Program $1,869 — both figures
  present in the KB), required documents (grounded), admission process (grounded,
  Aug 24 2026 deadline + Aug 28 2026 test date verified in evidence), scholarships
  (honest "insufficient" — evidence exists but 1.5B cannot list accurately without
  hallucinating; a "list scholarships" prompt variant fabricated a Talent Hunt
  Scholarship and wrong quota associations, so it was NOT adopted). Known limitations:
  the 1.5B model still cannot reliably distinguish Golden vs regular GPA-5 or pick
  the single best row for ambiguous banglish waiver wording; answers remain grounded
  in evidence rows. Deterministic eligibility engine, rules, evaluation harness, and
  M6 fine-tuning were untouched. Reason: demo-day product reliability, explicitly out
  of M6 scope.
- **2026-08-14** — Programs-catalog demo fix (NO M6/research, NO eligibility-engine
  changes). Root cause: the chatbot could only answer Science & IT program questions
  because the Playwright capture of the faculty-tabbed `/programs` page only rendered
  the default SIT tab (9 programs), so BBA/Law/Pharmacy/etc. existed nowhere in the
  pipeline. Fixes:
  (1) Scraper now captures approved dependency-fetch JSON bodies via
  `page.on("response")` and persists them as `dependency_responses` on raw records
  (`scraper/fetcher.py`, `scraper/playwright_fetcher.py`, `scraper/runner.py`).
  (2) The already-approved official programs API
  (`webbackend.daffodilvarsity.edu.bd/api/v1/public/academic/programs`, 7 faculties,
  52 programs) is now cleaned into a full program-catalog table (name/tag/level/
  faculty) with DOM fallback (`cleaning/html_cleaner.py`; pipeline version
  `phase5-2.0`), and the traceability validator accepts decoded JSON dependency
  strings (`cleaning/validator.py`).
  (3) Re-collected DIU-PROG-001 → `data/raw/collection-v2-finalized` (18 records),
  regenerated `data/cleaned/v2` (52-row catalog; raw + clean validation pass), rebuilt
  KB (264 chunks, one chunk per program incl. faculty metadata), `rag/config.py`,
  `.env`, and script defaults now point at v2.
  (4) `backend/services/programs_service.py`: ordered `_DEGREE_RULES` map and a
  faculty column; `GET /api/programs` now returns all 53 unique-stable programs
  (e.g. `bba`, `cse`, `te`, `law-hons`, `pharmacy-b-pharm`) with faculty + degree.
  (5) Retrieval: short existence queries ("Does DIU have BBA/Law/Pharmacy/Textile?")
  and program-list queries now use a program-phrase/catalog candidate lane plus
  expanded `_PROGRAM_QUERY_MARKERS` (incl. Bangla বিবিএ/আইন/ফার্মেসি), an MBA-vs-BBA
  master/bachelor signal, and an engineering-faculty exclusion for "outside
  engineering" (`rag/retriever.py`, `rag/chunker.py` per-row faculty).
  (6) Eval dataset `data/evaluation/questions.v1.json` gold chunk IDs updated to the
  equivalent new catalog chunk IDs (facts unchanged; content hashes moved with the
  table rebuild) — content_hash recomputed.
  Verification: backend 302 passed; frontend vitest 11 passed + typecheck/lint clean;
  live retrieval + real local Qwen answers confirm BBA, Pharmacy, Textile, Law,
  MBA, Bangla/Banglish existence questions and the program overview all answer
  correctly (e.g. "Yes, DIU offers a Bachelor of Business Administration (BBA)
  program under its Business & Entrepreneurship faculty."). Known limitation: the
  1.5B model gives a poor answer for the Banglish list phrasing "DIU te ki ki program
  ache?" (comprehension, not retrieval — context is correct); "Does DIU have Law?"
  surfaces the LL.B. chunk at rank 4 but answers correctly. Deterministic eligibility
  engine and M6 fine-tuning untouched.
- **2026-08-14** — TASK-DEMO (admission-chat demo hardening) completed. Preserved
  the existing architecture, local KB, Qwen2.5-1.5B model, eligibility engine, M5
  evaluation artifacts, and all raw data. Backend follow-up resolution now tracks
  the latest user-supplied program and topic independently, so unit-only follow-ups
  (`in BDT`), program switches (CSE → BBA → Law), and later program-sensitive
  questions retain only the relevant context. Retrieval now rejects incompatible
  fact/category/program/degree/currency evidence: local tuition excludes USD and
  catalog rows; named-program tuition cannot fall back to another program; LL.B.
  admission-GPA questions cannot consume waiver-maintenance SGPA; undergraduate
  document questions exclude master/diploma checklists; admission-process questions
  use the official flowchart rather than waiver/application fragments. Structured
  table preference now covers GPA, percentage, deadline, requirement, tuition, fee,
  waiver, and scholarship wording. Because the 1.5B model mislabeled CSE average
  semester fees as yearly fees and crossed from SSC/HSC waiver rows into English-
  medium columns during live testing, `ChatService` now deterministically formats
  those two table shapes from retrieved labels/values; no changing values are
  hard-coded. A grade-based waiver without a program asks for the program/faculty.
  Frontend request construction preserves the six most recent turns and reuses the
  exact failed history on retry. Regression coverage added for history, program and
  degree pinning, BDT-vs-USD, missing BBA/Law tuition, LL.B. GPA safety, process and
  document category pinning, exact tuition labels, ambiguous waiver clarification,
  SSC/HSC waiver-row selection, and explicit scholarship-name extraction from the
  official browse block. Verification: backend `317 passed` in cached-
  model offline mode; frontend Vitest `14 passed`, typecheck and lint clean. Real
  `/api/chat` verification confirmed local CSE values (BDT 61,750 admission,
  85,000 average semester, 782,250 total tuition, 1,020,450 total program), safe
  insufficient responses for absent BBA/Law tuition and LL.B. admission GPA, direct
  BBA and LL.B. existence, program clarification for ambiguous waiver, CSE GPA-5
  row 15%/SGPA 3.00, three explicitly named (non-exhaustive) scholarships,
  undergraduate documents, and the admission flowchart. No M6, training,
  fine-tuning, eligibility, or research-result work was performed.
- **2026-08-14** — TASK-CATALOG (official program-catalog completion and demo
  validation) completed. Compared the live dynamic programs API used by the
  authoritative DIU catalog with the existing cleaned table before editing: both
  contained the same 52 unique program names, with no additions, removals, or
  duplicate live names. The generic API cleaner now retains the source-provided
  department, unit-bearing duration, and individual program route derived from
  the catalog's `department_short_name` + `slug`; malformed route segments and
  ambiguous unitless durations remain blank (for example, the source value `10`
  for Civil Engineering (Diploma Holder) was not relabeled or inferred). Exact
  normalized program names are deduplicated. Traceability validation now includes
  raw provenance/dependency URLs, and the structured row identity remains based
  on the original name/tag/level/faculty columns so optional enrichment updates
  existing chunks without invalidating protected M5 gold chunk IDs. The programs
  service exposes the individual page as `admission_url` and merges the separate
  unambiguous short-name `BBA` shell into the official full BBA catalog entry;
  `/api/programs` now returns 52 unique names, 52 unique IDs, and 52 linked entries
  (9 Business & Entrepreneurship, 9 Engineering), rather than 53 with duplicate
  BBA semantics. Retrieval now prefers exact full catalog phrases over broader
  acronyms (fixing Finance & Banking vs generic BBA), recognizes Civil Engineering,
  excludes unrequested diploma-holder variants, resolves explicit faculty-list
  intent using source-derived faculty metadata, and exhaustively enumerates
  authoritative structured catalog rows after that constraint. `ChatService`
  deterministically renders complete faculty lists or a concise all-catalog
  faculty/count overview, preventing Qwen/top-K omission while direct program and
  follow-up answers remain Qwen-generated. Rebuilt/validated `data/cleaned/v2` and
  the cached-model local KB: 18 clean records pass with zero errors/warnings; 264
  unique chunks include 52 unique structured catalog rows and 52 individual
  official links. Regression coverage includes extraction/link safety,
  deduplication, programs API links, stable enriched chunk identity, exact program
  specificity, exhaustive faculty rows below the normal similarity threshold, and
  complete structured list responses. Verification: full backend suite `324
  passed` with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`; M5 schema/eligibility
  compatibility `40 passed`; representative official BBA, Finance, EEE, and Civil
  links returned HTTP 200; real local Qwen answered Civil existence, Finance &
  Banking duration/link, BBA faculty follow-up, and BBA page-link follow-up from the
  correct single program evidence. Complete structured responses returned all 9
  Business and all 9 Engineering programs. No frontend, eligibility-engine, M5
  artifact/result, M6, fine-tuning, training, model download, or paid API work was
  performed.
- **2026-08-14** — TASK-PUBLISH completed. Refreshed `origin/main` and confirmed
  `0/0` divergence before publication. Audited the complete 81-file commit
  candidate: `.env`, credentials, raw/cleaned datasets, local KB/vector data,
  evaluation results, model weights, frontend build caches, and large generated
  artifacts remained ignored; staged secret-pattern, prohibited-path, >1 MB file,
  and whitespace checks were clean. Reverified the frontend immediately before
  publication: Vitest 14 passed, TypeScript typecheck passed, ESLint passed; the
  final backend suite from TASK-CATALOG was 324 passed in cached-model offline
  mode. Pushed `b5ce6d6` (`feat: complete DIU admission assistant demo`) normally
  to `origin/main` with no force or history rewrite. This publication performed no
  feature, eligibility, M5-result, M6, training, or fine-tuning work.
- **2026-08-15** — TASK-FRONTEND-VIVA-NOTE completed (documentation only). Added
  `frontendNote.md`, a concise viva-ready description of the implemented frontend:
  stack and responsibilities, App Router pages, component/service structure, typed
  mock/real API integration, chat persistence and bounded history, backend-owned
  eligibility flow, responsive/accessibility behavior, focused test coverage, short
  viva questions, current limitation, and a one-minute summary. All statements were
  checked against the current frontend, API contract, configuration, and tests.
  Frontend Vitest: 27 passed. No application functionality or research result changed.
- **2026-08-16** — TASK-06 completed. Added `scripts/bootstrap.sh` as the single
  repeatable setup command and `scripts/artifacts.py` as a no-network artifact
  checker. Raw/cleaned manifests, local KB metadata/entries, and held-out
  evaluation provenance are validated before use; recovery commands explicitly
  use the existing checksum/provenance validators. Added the `integration` pytest
  marker with an offline unit-test default, skipped artifact-dependent tests with
  actionable recovery guidance, ignored supported virtual-environment names, and
  prevented invalid chat requests from constructing retriever/generator services.
  Missing cleaned data now returns a contract-shaped 503 with recovery details.
  Updated README, API contract, evaluation manifest path, and this plan. No
  admission facts, rules, model weights, datasets, or research results changed.
- **2026-08-16** — TASK-07 completed. Added Vercel's supported Next.js deployment
  settings under `frontend/vercel.json`, made `NEXT_PUBLIC_API_URL` and mock mode
  explicit build-time configuration in `next.config.ts`, hardened API URL
  normalization, and documented local versus Vercel environment values. Added
  the official `@vercel/analytics` component to the root layout; Web Analytics
  still requires enabling the project in the Vercel dashboard. Existing mock mode,
  API contracts, admission logic, RAG behavior, and model code were unchanged.
- **2026-08-16** — TASK-08 completed. Added backend deployment settings for
  PostgreSQL, OpenAI-compatible model endpoints, model/embedding names, HF tokens,
  and comma-separated production CORS origins. Added startup validation that stops
  production when `DATABASE_URL`, `OPENAI_API_BASE`, or `CORS_ORIGINS` is missing;
  development remains permissive. Added `backend/.env.example`, CORS credentials,
  README deployment instructions, and focused configuration tests. Admission
  logic, eligibility rules, RAG behavior, model code, and secrets were unchanged.
- **2026-08-16** — TASK-09 completed. Verified FastAPI validates chat and
  eligibility request bodies before resolving model-backed dependencies, normalized
  validation field names in the shared error envelope, and added comprehensive
  422/no-initialization tests. Documented that programs and sources are bodyless
  GET endpoints, so unsupported methods return 405 rather than inventing required
  fields or changing the API contract. No admission, eligibility, or RAG behavior
  was changed.
- **2026-08-16** — TASK-10 completed. Added safe startup diagnostics for
  environment, CORS, database, model endpoint, RAG backend, and UTC timestamp;
  production validation now logs the specific missing setting before failing.
  Expanded `/api/health` (with `/health` compatibility) to return liveness,
  environment, timestamp, and bounded database/model/RAG dependency checks.
  Documented production startup, verification, common configuration errors,
  monitoring, and restart procedures. Added focused health and startup-log
  coverage. No admission logic, eligibility rules, RAG behavior, model code,
  credentials, or secrets were changed.
- **2026-08-16** — TASK-11 completed. Verified the existing restrictive CORS
  middleware accepts comma-separated exact origins, allows `GET`, `POST`, and
  `OPTIONS`, enables credentials, and rejects unauthorized origins without an
  allow-origin header. Added dedicated preflight, header, method, credential,
  and multi-origin parsing tests; documented localhost, Vercel/custom-domain
  deployment values, restart steps, and troubleshooting. No backend origin was
  exposed in frontend code and wildcard production CORS was not enabled.
- **2026-08-16** — TASK-12 completed. Frontend Vitest (14 tests), TypeScript
  typecheck, ESLint, and the Next.js 16.3.0 production build all passed. npm
  audit found zero vulnerabilities and `npm ci --dry-run` succeeded. The
  already-running development server served the root page on localhost:3000;
  a second server was not started because port 3000 was occupied. The build
  root was scoped to the frontend project to remove an unrelated parent
  lockfile warning. No frontend behavior or backend/admission logic was changed.
- **2026-08-16** — TASK-13 completed. Offline backend verification passed with
  320 unit tests and 41 integration tests deselected; API, core, eligibility,
  RAG, cleaning, invalid-request, and admission-integrity subsets all passed.
  Added health dependency-path tests so backend API coverage is 87%; core is
  100%, eligibility is 90%, and RAG is 77%. Isolated execution with model/cache
  variables unset passed, and no secrets appeared in test output. Coverage
  tooling was installed only in the local virtual environment; no dependency
  manifest or application behavior changed.
- **2026-08-16** — TASK-14 completed. Added complete Vercel/backend deployment
  instructions, an operator checklist, environment-variable reference,
  troubleshooting guide, and deployment summary. Verified ignore rules cover
  environment files, keys, certificates, virtual environments, caches, and
  generated frontend artifacts. Marked the project ready for provider
  deployment; no real credentials or external deployment state were added.
- **2026-08-16** — TASK-16 completed. Recollected all 18 registered official DIU
  sources into a new immutable v2 raw snapshot (18 successful, zero failures),
  with raw integrity validation passing without errors, warnings, duplicate
  hashes, or privacy findings. Fixed the cleaner's stale v1-only manifest
  selector by adding explicit dataset-version selection and regression coverage.
  Cleaned v2 validation passed for all 18 records; the dynamic programs source
  produced 52 official catalog rows and chunking produced 264 chunks. Rebuilt the
  configured Neon pgvector index atomically to 264 rows and verified Textile
  Engineering retrieval plus `/api/programs` returning 52 programs. Full offline
  backend suite: 329 passed, 41 integration tests deselected. Generated data and
  credentials remain ignored; no admission facts, rules, eligibility logic, or
  model code changed.
- **2026-08-16** — TASK-17 completed. Added an idempotent, transactional Neon
  runtime catalog with program/source provenance and dataset metadata, plus a
  validated synchronization command. Synchronized and independently verified 52
  programs and 18 official sources in Neon; local development now uses the
  database catalog while production is prohibited from silently reading local
  cleaned files. Added an OpenAI-compatible hosted embedding adapter shared by
  indexing and retrieval, strict model/dimension metadata compatibility, and
  production validation requiring Neon catalogs, pgvector, hosted generation,
  and hosted embeddings. Added a slim `requirements-deploy.txt`, Dockerfile,
  `.dockerignore`, and Render blueprint without local model/scraper/training
  dependencies, plus updated environment/deployment documentation and tests.
  Verification: 346 backend tests passed offline (41 integrations deselected),
  frontend Vitest 15 passed, TypeScript/ESLint/build passed, Neon catalog API
  smoke test returned 52 programs and 18 sources, and dependency/compile/diff
  checks passed. Actual hosted-vector creation and provider deployment remain
  manual because no hosted-model key or authorized backend-provider session was
  supplied. No admission facts, eligibility rules, research results, credentials,
  or generated datasets were committed.
