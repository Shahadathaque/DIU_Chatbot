# Research Specification

## 1. Project title

**DIU Admission AI: A Domain-Specific Fine-Tuned LLM with Retrieval-Augmented Generation for Daffodil International University Admission**

## 2. Problem statement

DIU admission information is distributed across central pages, department pages, PDFs, notices, and official subdomains. Prospective students need concise answers, but a general-purpose model can return outdated, unsupported, or out-of-domain information. This project investigates whether domain adaptation, retrieval, and deterministic rules can improve admission assistance while retaining evidence and uncertainty.

## 3. Main research question

To what extent do domain-specific fine-tuning and retrieval-augmented generation, separately and together, improve correctness, relevance, groundedness, multilingual performance, and domain adherence for DIU admission questions compared with a base open-source instruction model?

## 4. Research objectives

- Build a provenance-preserving corpus from official DIU-controlled sources.
- Establish a reproducible base-model benchmark before training.
- Fine-tune domain behavior with LoRA/QLoRA without memorizing volatile facts.
- Retrieve current DIU evidence through RAG and cite official sources.
- Evaluate deterministic eligibility separately from LLM explanation.
- Compare English, Bangla, and Banglish behavior across four systems.

## 5. Research hypotheses

- RAG will improve correctness and groundedness and reduce hallucination on evidence-backed questions.
- Domain fine-tuning will improve DIU identity, structure, clarification, uncertainty, and out-of-domain refusal.
- Fine-tuning plus RAG will provide the strongest combined behavior and evidence use, although experiments may reject this hypothesis.
- Deterministic rules will be more reliable than free-form generation for eligibility when rules and inputs are complete.

## 6. Scope

The domain is DIU admission: programs, requirements, application steps, documents, fees, scholarships, waivers, notices, deadlines, international admission, diploma pathways, contacts, and program facts relevant to applicants.

## 7. Out of scope

Other universities, general advising, course registration, student-portal support, faculty biographies, alumni services, unrelated news, and official admission decisions are excluded. The prototype does not replace DIU staff or official pages.

## 8. Proposed solution

FastAPI coordinates domain checking, official-source retrieval, a deterministic eligibility engine when applicable, and a configurable multilingual open-source instruction model. Next.js displays answers, uncertainty, and citations. Out-of-domain questions are refused or redirected.

## 9. Dataset methodology

Register sources before controlled collection. Keep raw captures immutable. Cleaned records preserve document ID, URL, title, category, program, faculty, retrieval time, visible content, content hash, and source update date when available. Cleaning removes repeated navigation noise without summarizing away requirements, dates, tables, or conditions. Splits prevent duplicate and source leakage.

## 10. Fine-tuning methodology

Use a configurable multilingual 1B–4B instruction model, preferably Qwen-family if hardware and baseline evidence support it. LoRA/QLoRA teaches identity, terminology, response format, clarification, refusal, uncertainty, evidence use, and multilingual interaction. Volatile facts are not deliberately memorized. Record model revision, dataset version, seed, hyperparameters, software, and hardware. Evaluate the base model before training.

## 11. RAG methodology

Chunk cleaned documents while retaining provenance and headings. Generate versioned embeddings, store vectors and metadata in PostgreSQL with pgvector, and evaluate Recall@K on held-out queries. Pass evidence explicitly to generation; qualify or refuse unsupported answers.

## 12. Eligibility-engine methodology

Represent verified admission rules as deterministic, source-linked, versioned rules. Return `eligible`, `not_eligible`, or `insufficient_information` with a reason and source. The LLM may explain but never override the result. Test boundaries, missing inputs, diploma pathways, and program-specific subjects.

## 13. Multilingual strategy

- **English:** primary benchmark and official-source baseline.
- **Bangla:** native-script prompts and answers evaluated for meaning, correctness, and script quality.
- **Banglish:** Latin-script Bangla with spelling variation; normalization must retain intent.

Comparable evaluation sets should not assume literal translation is always natural.

## 14. Experimental systems

1. Base LLM
2. Fine-tuned LLM
3. Base LLM + RAG
4. Fine-tuned LLM + RAG

Use a fixed held-out set and recorded inference configuration. Report eligibility accuracy separately.

## 15. Evaluation metrics

Factual correctness, relevance, groundedness, hallucination rate, citation support, domain adherence, refusal accuracy, clarification quality, English/Bangla/Banglish performance, retrieval Recall@K, inference latency, and eligibility correctness. Version rubrics and measures; report no number without an executed experiment.

## 16. Source-provenance policy

Only DIU-controlled sources are authoritative. Every factual record retains its URL, retrieval timestamp, content hash, and category. Official subdomains are allowed only when DIU ownership and admission relevance are documented. Third parties cannot establish facts.

## 17. Hallucination-control policy

Prefer retrieved evidence, distinguish evidence from inference, expose sources, return insufficient information when evidence or inputs are missing, constrain the domain, and test refusals. Flag conflicting or stale sources for review rather than silently resolving them.

## 18. Reproducibility requirements

Version registries, datasets, prompts, evaluation sets, configurations, model revisions, seeds, dependencies, and outputs. Preserve raw data, log exclusions and failures, and separate “pipeline implemented” from “experiment executed.” Keep large artifacts outside Git with documented storage.

## 19. Ethical considerations

Respect policies, robots guidance, rate limits, and personal-data minimization. Do not collect applicant records. Label the prototype, communicate uncertainty, avoid discriminatory eligibility behavior, and provide official verification paths.

## 20. Limitations

DIU pages may be dynamic, incomplete, inconsistent, or silently updated. Banglish has no fixed spelling. Free compute limits model size and repetitions. Evidence can become stale, and human evaluation can be subjective.

## 21. Definition of project success

Success requires a reproducible official-source dataset, executed baseline and four-system comparison, honestly reported positive or negative findings, supported citations, strong domain behavior in three language modes, tested deterministic eligibility, and a usable prototype that never presents itself as DIU’s final authority.

