# DIU Admission AI — Backend File Guide

## My part

My part is the Python/FastAPI backend. It receives requests from the Next.js frontend, validates them, runs the required service, and returns JSON responses. It also connects the frontend to the RAG pipeline and deterministic eligibility engine.

## Main backend files

| File | What it does |
| --- | --- |
| `backend/main.py` | Creates the FastAPI app, enables CORS, registers error handlers, and connects all API routes. |
| `backend/core/config.py` | Reads backend settings from environment variables and `.env`. |
| `backend/core/errors.py` | Converts validation, service, and unexpected errors into one safe JSON format. |
| `backend/core/logging.py` | Configures backend logging. |

## API route files

| File | What it does |
| --- | --- |
| `backend/api/health.py` | Implements `GET /health` to confirm that the API is running. |
| `backend/api/chat.py` | Implements `POST /api/chat` and creates/caches the retriever, generator, and chat service. |
| `backend/api/eligibility.py` | Implements `POST /api/eligibility` and sends applicant data to the eligibility service. |
| `backend/api/programs.py` | Implements `GET /api/programs` and returns programs found in cleaned DIU data. |
| `backend/api/sources.py` | Implements `GET /api/sources` and returns official sources used by the system. |

## Request and response models

| File | What it does |
| --- | --- |
| `backend/models/chat.py` | Validates the chat message, language, history, answer, sources, and confidence. |
| `backend/models/eligibility.py` | Validates program, GPA, group, diploma pathway, decision, matched rules, and evidence gaps. |
| `backend/models/programs.py` | Defines the JSON structure for programs. |
| `backend/models/sources.py` | Defines the JSON structure for official source information. |
| `backend/models/errors.py` | Defines the common JSON error structure. |

## Service files

| File | What it does |
| --- | --- |
| `backend/services/chat_service.py` | Controls chat: resolves follow-ups, retrieves evidence, builds grounded prompts, calls the generator, and returns citations/confidence. |
| `backend/services/eligibility_service.py` | Converts API input into eligibility-engine input and maps the result back to the API response. |
| `backend/services/programs_service.py` | Reads program tables from cleaned data, removes duplicates, and creates stable IDs. |
| `backend/services/sources_service.py` | Reads and sorts official source records from cleaned data. |

## Eligibility files

| File | What it does |
| --- | --- |
| `eligibility/engine.py` | Evaluates eligibility using deterministic rules; the LLM never makes the decision. |
| `eligibility/loader.py` | Loads, validates, and hashes versioned rule/program JSON files. |
| `eligibility/models.py` | Defines internal rules, inputs, matches, decisions, and source references. |
| `rules/eligibility_rules.v1.json` | Stores source-backed eligibility rules and known evidence gaps. |
| `rules/programs.v1.json` | Stores the source-backed program registry. |

The current rules are intentionally non-decisive because official sources do not contain every GPA, subject, and program threshold. Returning `insufficient_information` is safer than inventing a decision.

## RAG files used by the backend

| File | What it does |
| --- | --- |
| `rag/config.py` | Reads embedding, vector-store, chunking, and generator settings. |
| `rag/models.py` | Defines chunks, vector matches, filters, and search results. |
| `rag/chunker.py` | Converts cleaned records and tables into small traceable chunks. |
| `rag/embeddings.py` | Uses multilingual E5 to create vectors for English, Bangla, and Banglish. |
| `rag/vector_store.py` | Stores/searches vectors using PostgreSQL + pgvector or local JSON. |
| `rag/retriever.py` | Embeds questions, searches chunks, filters weak/outdated evidence, and reranks results. |
| `rag/generator.py` | Defines the generator interface and selects the configured generator. |
| `rag/generators/local.py` | Loads and runs the local Qwen model. |
| `rag/generators/openai_compatible.py` | Calls an OpenAI-compatible local or hosted model API. |

## Scraping files — pipeline overview

| File | What it does |
| --- | --- |
| `data/source_registry.csv` | Allowlist of official DIU URLs, categories, priorities, page types, and evidence status. |
| `scripts/scrape_diu.py` | Command-line entry point for controlled collection. |
| `scraper/registry.py` | Loads/validates the registry and rejects duplicate or invalid sources. |
| `scraper/runner.py` | Coordinates a complete scraping run. |
| `scraper/fetcher.py` | Chooses static HTML, dynamic HTML, or PDF fetching. |
| `scraper/html_fetcher.py` | Downloads registered static pages with `requests`. |
| `scraper/playwright_fetcher.py` | Renders JavaScript pages with Playwright/Chromium. |
| `scraper/pdf_fetcher.py` | Downloads official PDFs and verifies their signatures. |
| `scraper/policy.py` | Reviews and records `robots.txt`. |
| `scraper/rate_limit.py` | Adds safe per-host request delays. |
| `scraper/extractor.py` | Creates a text view while preserving original raw bytes. |
| `scraper/storage.py` | Saves immutable raw files, metadata, failures, hashes, logs, and manifests. |
| `scraper/utils.py` | Provides URL normalization, IDs, timestamps, safe paths, and SHA-256 hashing. |

## Cleaning files — pipeline overview

| File | What it does |
| --- | --- |
| `scripts/clean_dataset.py` | Runs the raw-to-clean dataset pipeline. |
| `scripts/validate_raw_dataset.py` | Checks raw hashes, paths, metadata, and manifest integrity. |
| `scripts/validate_clean_dataset.py` | Checks cleaned records, hashes, tables, and provenance. |
| `cleaning/html_cleaner.py` | Removes scripts, navigation, footer, forms, and repeated website noise. |
| `cleaning/pdf_extractor.py` | Extracts embedded PDF text and reliable tables with `pdfplumber`. |
| `cleaning/normalizer.py` | Normalizes Unicode, whitespace, lines, and table cells. |
| `cleaning/filters.py` | Filters unrelated content and detects duplicates. |
| `cleaning/models.py` | Defines cleaned records, tables, and PDF page objects. |
| `cleaning/validator.py` | Verifies cleaned-dataset integrity and provenance. |

## Knowledge-base and shared files

| File | What it does |
| --- | --- |
| `scripts/build_knowledge_base.py` | Creates chunks/embeddings and writes them to the vector store. |
| `scripts/search_knowledge.py` | Tests retrieval from the terminal. |
| `data/chunks/local_knowledge_base.json` | Local development vector index. |
| `contracts/api-contract.md` | Shared frontend/backend request, response, endpoint, and error contract. |
| `.env.example` | Documents backend, database, RAG, model, and CORS settings. |
| `requirements.txt` | Lists pinned Python dependencies. |
| `tests/test_api_*.py` | Tests backend endpoints and API contracts. |
| `tests/test_eligibility_engine.py` | Tests deterministic eligibility behavior. |
| `tests/test_rag_*.py` | Tests chunking, embeddings, storage, and retrieval. |
| `tests/test_scraper_*.py` | Tests scraping and collection controls. |

## Chat flow

```text
Frontend
 -> backend/api/chat.py
 -> backend/models/chat.py validates input
 -> backend/services/chat_service.py
 -> rag/retriever.py finds official DIU evidence
 -> rag/generators/local.py generates a grounded answer
 -> JSON response with answer, confidence, and official sources
```

## Eligibility flow

```text
Frontend form
 -> backend/api/eligibility.py
 -> backend/models/eligibility.py validates input
 -> backend/services/eligibility_service.py
 -> eligibility/loader.py loads rules
 -> eligibility/engine.py evaluates rules
 -> JSON decision with rule matches and evidence gaps
```

## One-sentence viva answer

> My backend uses FastAPI and Pydantic to expose validated APIs, connects chat requests to an official-source RAG pipeline, returns citations from retrieved evidence, and uses a separate deterministic rule engine for eligibility so the LLM cannot invent admission decisions.
