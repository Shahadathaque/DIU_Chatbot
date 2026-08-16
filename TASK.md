# TASK — Retrieval quality, evidence validation, deployment sync, and public verification

Status: Blocked — local implementation and verification complete; Neon rebuild
and Render/Vercel deployment are waiting for external-action approval capacity.

## Objective

Fix the retrieval layer so the product answers broad, short, paraphrased, Bangla, and Banglish questions using verified DIU evidence, while preserving strict refusal behavior for unsupported questions.

This is the active task. It replaces the earlier optimization task and must be executed in full.

## Scope

1. Improve semantic retrieval quality for:
   - broad questions
   - short questions
   - paraphrased questions
   - Bangla questions
   - Banglish questions
2. Fix all displayed example questions so each example retrieves verified evidence.
3. Add query normalization, intent detection, and synonym/query expansion.
4. Calibrate retrieval thresholds using tests—not arbitrary lowering.
5. Preserve refusal for unsupported questions.
6. Add regression tests for common questions and citations.
7. Rebuild/sync Neon vectors, redeploy Render/Vercel, and verify publicly.

## Rules

- Only use verified DIU official sources as retrieval evidence.
- Do not invent facts, fees, deadlines, scholarship rules, or eligibility rules.
- If evidence is missing or insufficient, answer with an appropriate unknown/insufficient-information response.
- Deterministic eligibility decisions must remain in the rule engine, not the LLM.
- The LLM may explain the rule-engine result but may not override it.
- Do not commit secrets, API keys, .env files, tokens, or model weights.
- Keep raw scraped data immutable.
- Maintain provenance for all retrieved knowledge.
- Do not hide failing retrieval cases behind broader matching and do not lower thresholds without test evidence.

## Required implementation

### 1) Retrieval improvements

Implement or improve the retrieval pipeline with:
- query normalization
- intent detection
- synonym and reformulation expansion
- abbreviated/broad query handling
- Bangla and Banglish normalization
- paraphrase-aware matching
- evidence scoring that prefers exact verified source matches
- citation-aware answer generation

The system must retrieve evidence for common admissions questions, including likely phrasing variants such as:
- "what is the admission fee?"
- "admission cost"
- "what is the total fee?"
- "admission requirement"
- "eligible for CSE?"
- "am i eligible for bsc in cse?"
- "BSc in CSE eligibility"
- "এডমিশন ফি কত?"
- "admission fee bangla"
- "CSE eligibility 2025?"
- "what are the requirements for computer science?"
- "programs for bba"
- "kono course er eligibility ki?"
- "CSE ar admission condition"

### 2) Example-question cleanup

Fix all example or demo questions shown in the product or docs so that each one is backed by actual verified evidence.

Do not leave examples that are vague, ungrounded, or not retrievable from the knowledge base.

Examples of invalid demo questions must be replaced with verified ones, such as questions whose answers are directly supported by the current knowledge base and source registry.

### 3) Retrieval threshold calibration

Calibrate retrieval thresholds using failing tests and evaluation results.

Do not lower thresholds arbitrarily to make a question pass. Any change to retrieval threshold must be justified by:
- a failing regression case
- a reproducible test
- a measurable improvement in retrieved evidence quality

This includes broad, short, paraphrased, Bangla, and Banglish queries.

### 4) Refusal preservation

Unsupported questions must still be refused or answered as insufficient information when the system lacks verified source evidence.

Examples of unsupported questions:
- unsupported external policies
- made-up deadlines or scholarship claims
- fake fee values not present in the source set
- personal application status not verifiable from official sources

The model must not fabricate or answer from speculation.

### 5) Citation and regression tests

Add tests covering:
- common short questions
- broad queries
- paraphrased questions
- Bangla queries
- Banglish queries
- unsupported questions that must refuse
- citation presence and exact source grounding
- evidence retrieval quality
- examples shown in UI/docs or mock prompts

The tests must assert that the retrieved chunks or citations correspond to the actual evidence set, not just model text.

## Acceptance criteria

- Semantic retrieval works well for broad, short, paraphrased, Bangla, and Banglish questions.
- Example questions in the UI and docs are all evidence-backed and verified.
- Query normalization, intent detection, synonym expansion, and retrieval expansion are implemented and tested.
- Retrieval thresholds are calibrated by test results, not guesswork.
- Unsupported questions are refused or marked unknown appropriately.
- Regression tests cover common questions and citations.
- Neon vectors are rebuilt or synchronized with the current source data.
- Render backend is redeployed with the updated retrieval logic.
- Vercel frontend is redeployed with the updated app behavior.
- Public deployment is verified by making live requests and confirming the app responds correctly.
- No secrets are committed or exposed.

## Required execution steps

1. Inspect the current retrieval pipeline and identify failure cases.
2. Add failing regression tests for retrieval quality and evidence grounding.
3. Implement query normalization, intent detection, and expansion.
4. Adjust retrieval logic and thresholds using test evidence.
5. Verify refusal behavior remains strict for unsupported questions.
6. Fix all example questions shown to users.
7. Rebuild or sync the Neon vector index.
8. Redeploy the backend to Render.
9. Redeploy the frontend to Vercel.
10. Test the public URLs and verify the live application works.
11. Summarize results and any remaining limitations.

## Deliverables

- Updated retrieval logic
- Regression tests for common questions and citations
- Cleaned example prompts/questions
- Public deployment verification notes
- Any required config updates without exposing secrets

## Constraints

- Do not change the eligibility engine or rule logic unless the task explicitly requires it.
- Do not fabricate DIU facts.
- Do not lower retrieval thresholds without test evidence.
- Do not keep unsupported example prompts in the UI.
- Do not deploy secrets to Git or chat logs.
- Stop only after this task is executed and verified.

## Execution note

This task is the active task. It supersedes older task files and should be treated as the single working specification.
