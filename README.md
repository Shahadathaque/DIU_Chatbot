# DIU Admission AI

DIU Admission AI is a university research project investigating a domain-specific, fine-tuned language model with retrieval-augmented generation for Daffodil International University admission assistance. The system is a research prototype, not an official source of admission decisions.

## Research architecture

```text
DIU official website
  -> data collection and cleaning
  -> DIU admission dataset
  -> verified chunks + multilingual embeddings + pgvector retrieval
  -> later LLM generation and eligibility logic
  -> FastAPI backend
  -> Next.js frontend
```

Later experiments will compare a base LLM, fine-tuned LLM, base LLM with RAG,
and fine-tuned LLM with RAG. Retrieval, the FastAPI backend, grounded local-LLM
generation, the deterministic eligibility engine, and the Next.js frontend are
implemented; evaluation and fine-tuning remain future work.

## Ownership

This is a single-developer project (see `AGENTS.md`). All directories belong to
the developer; the `frontend/`/`backend/` split is architectural, not an
ownership boundary. Cross-boundary integration follows
[`contracts/api-contract.md`](contracts/api-contract.md).

## Directory structure

```text
backend/          FastAPI application, configuration, services, and models
contracts/        Shared frontend/backend API contract
data/             Raw, cleaned, chunked, fine-tuning, and evaluation data
docs/             Member-specific documentation
evaluation/       Evaluation code (later phase)
frontend/         Next.js client owned by Member 2
notebooks/        Research notebooks (later phase)
rag/              Knowledge-base chunking, embeddings, storage, and retrieval
results/          Generated research outputs (later phase)
scraper/          Controlled web collection code
scripts/          Project CLI utilities
tests/            Backend tests
training/         Model training code (later phase)
```

## Member 1 setup

Python 3.11 is recommended. Dependencies are managed with the pinned root `requirements.txt`.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload
```

Verify the service at `GET http://127.0.0.1:8000/health` or run tests:

```bash
pytest
```

## Environment

Copy `.env.example` to `.env` and set local values as later phases require. Never commit `.env`, Hugging Face tokens, database credentials, model weights, or generated datasets.

## Current status

Phase 5 cleaning and normalization is implemented. The immutable raw v1 snapshot
feeds 18 traceable cleaned records under `data/cleaned/v1/`; embedded PDF text,
reliable tables, source currency states, manual-review states, hashes, and complete
raw lineage are preserved. Validation passes, while the cleaned dataset remains
truthfully partial because the BBA page is a non-substantive shell and the captured
noticeboard has no admission-related entry.

The retrieval layer converts that snapshot into traceable, structure-aware evidence
chunks with authority-gated semantic retrieval (production: PostgreSQL + pgvector; a
local JSON store for development). The FastAPI backend exposes `GET /health`,
`POST /api/chat` (retrieval + grounded local Qwen generation), `POST /api/eligibility`
(deterministic rule engine), `GET /api/programs`, and `GET /api/sources`, and the
Next.js frontend runs against the real API (mock fixtures retained for tests).

Research evaluation (base vs. fine-tuned × with/without RAG) and fine-tuning have not
begun.

Run a no-network selection check or a small controlled collection with:

```bash
python scripts/scrape_diu.py --dry-run
python scripts/scrape_diu.py --limit 3
python scripts/scrape_diu.py --source-id DIU-ADM-001
```

Dynamic sources require Chromium after installing the Python dependencies:

```bash
playwright install chromium
```

Validate the finalized Phase 5 output with the second command below. A reproducibility
build must use a separate empty target, for example:

```bash
python scripts/clean_dataset.py --output-root /tmp/diu-cleaned-v1-check
python scripts/validate_clean_dataset.py --cleaned-root /tmp/diu-cleaned-v1-check
python scripts/validate_clean_dataset.py
```

See [`docs/backend/scraper_report.md`](docs/backend/scraper_report.md) for the
measured Phase 4 sample and
[`docs/backend/raw_dataset_v1_report.md`](docs/backend/raw_dataset_v1_report.md)
for the Phase 4.1 registry repair, expanded v1 collection, validation results, and
remaining gaps. See
[`docs/backend/clean_dataset_v1_report.md`](docs/backend/clean_dataset_v1_report.md)
for the Phase 5 method, measured statistics, flags, and readiness decision.
Generated raw and cleaned artifacts are ignored by Git; retain them in backed-up
research storage together with their manifests.

Build or search the retrieval index after completing the PostgreSQL setup in
[`docs/backend/rag_retrieval.md`](docs/backend/rag_retrieval.md):

```bash
python scripts/build_knowledge_base.py --dry-run
python scripts/build_knowledge_base.py
python scripts/search_knowledge.py "What documents are required for DIU admission?"
```
