# DIU Admission AI

DIU Admission AI is a university research project investigating a domain-specific, fine-tuned language model with retrieval-augmented generation for Daffodil International University admission assistance. The system is a research prototype, not an official source of admission decisions.

## Research architecture

```text
DIU official website
  -> data collection and cleaning
  -> DIU admission dataset
  -> fine-tuned LLM + RAG vector database + eligibility rule engine
  -> FastAPI backend
  -> Next.js frontend
```

Later experiments will compare a base LLM, fine-tuned LLM, base LLM with RAG, and fine-tuned LLM with RAG. Phase 2 creates scaffolding only; it does not implement those systems or include admission data.

## Ownership

Member 1 owns:

- `backend/`
- `scraper/`
- `rag/`
- `training/`
- `evaluation/`
- `data/`
- `results/`
- `scripts/`
- `notebooks/`
- `tests/`
- `docs/backend/`
- `contracts/` (coordinated shared contract)

Member 2 owns `frontend/` and `docs/frontend/`. **Member 1 must not modify frontend implementation files.** Cross-boundary integration must follow [`contracts/api-contract.md`](contracts/api-contract.md).

## Directory structure

```text
backend/          FastAPI application, configuration, services, and models
contracts/        Shared frontend/backend API contract
data/             Raw, cleaned, chunked, fine-tuning, and evaluation data
docs/             Member-specific documentation
evaluation/       Evaluation code (later phase)
frontend/         Next.js client owned by Member 2
notebooks/        Research notebooks (later phase)
rag/              Retrieval pipeline (later phase)
results/          Generated research outputs (later phase)
scraper/          Data collection code (later phase)
scripts/          Project utilities (later phase)
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

Phase 4 controlled collection is implemented. The scraper processes only validated
entries in `data/source_registry.csv`, stores append-only raw captures under
`data/raw/`, and supports static HTML, Playwright-rendered HTML, and original PDF
bytes. Chat, eligibility, program, and source endpoints remain intentionally
unimplemented; cleaning, RAG, embeddings, training, and evaluation have not begun.

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

See [`docs/backend/scraper_report.md`](docs/backend/scraper_report.md) for the
measured Phase 4 sample and limitations. Generated raw artifacts are ignored by
Git; retain them in backed-up research storage together with their run manifest.
