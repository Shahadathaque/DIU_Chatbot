# DIU Admission AI

DIU Admission AI is a university research project investigating a domain-specific, fine-tuned language model with retrieval-augmented generation for Daffodil International University admission assistance. The system is a research prototype, not an official source of admission decisions.

## Research architecture

```text
DIU official website
  -> data collection and cleaning
  -> DIU admission dataset
  -> verified chunks + multilingual embeddings + pgvector retrieval
  -> grounded LLM generation and deterministic eligibility logic
  -> FastAPI backend
  -> Next.js frontend
```

Later experiments compare a base LLM, fine-tuned LLM, base LLM with RAG, and
fine-tuned LLM with RAG. Retrieval, the FastAPI backend, grounded local-LLM
generation, the deterministic eligibility engine, and the Next.js frontend are
implemented. Baseline held-out evaluation infrastructure and results are retained
locally; fine-tuning remains future research work.

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
evaluation/       Held-out dataset schema and research evaluation code
frontend/         Next.js client
notebooks/        Research notebooks (later phase)
rag/              Knowledge-base chunking, embeddings, storage, and retrieval
results/          Generated research outputs (later phase)
scraper/          Controlled web collection code
scripts/          Project CLI utilities
tests/            Backend tests
training/         Model training code (later phase)
```

## Reproducible local setup

Python 3.11 is recommended. The single bootstrap command creates or reuses an
ignored virtual environment, installs the pinned root dependencies, creates a
local `.env` from `.env.example` when needed, and verifies private artifacts
without loading models or making network requests:

```bash
bash scripts/bootstrap.sh
```

Set `PYTHON_BIN` or `VENV_DIR` when your local names differ, for example
`VENV_DIR=.venv311 bash scripts/bootstrap.sh`. The command exits non-zero and
prints recovery steps when private raw, cleaned, knowledge-base, or held-out
evaluation artifacts are absent. It never downloads model weights as part of
the artifact check.

Run the default offline unit suite with:

```bash
.venv/bin/python -m pytest
```

Artifact-dependent checks are explicitly marked as integration tests and are
excluded from the default unit run. After restoring or rebuilding the private
artifacts, run them with:

```bash
.venv/bin/python scripts/artifacts.py
.venv/bin/python -m pytest -m integration
```

The checker validates raw and cleaned manifests, record hashes, local vector
store metadata/entries, and evaluation provenance. Recovery/rebuild commands
are printed by `scripts/artifacts.py`; generated datasets, indexes, results,
and model weights remain local and must not be committed.

Start the API after the artifact check succeeds:

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

## Environment

Copy `.env.example` to `.env` and set local values as later phases require. Never commit `.env`, Hugging Face tokens, database credentials, model weights, or generated datasets.

### Frontend deployment on Vercel

The Next.js project lives in `frontend/`. When creating the Vercel project, set
its Root Directory to `frontend/`; `frontend/vercel.json` provides the build and
URL normalization settings. Add these Production environment variables in
Vercel Project Settings before deploying:

```text
NEXT_PUBLIC_USE_MOCK_API=false
NEXT_PUBLIC_API_URL=https://<your-deployed-backend-domain>
```

`NEXT_PUBLIC_API_URL` is the public FastAPI origin without a trailing slash and
is used by `frontend/services/api.ts` for `/api/live`, `/api/chat/stream`, and
the other `/api/...` requests.
These `NEXT_PUBLIC_*` values are embedded during `next build`, so changing them
requires a new deployment. For local development, copy
`frontend/.env.example` to `frontend/.env.local`; mock mode remains available
with `NEXT_PUBLIC_USE_MOCK_API=true`. Vercel Web Analytics is mounted in the
frontend root layout; enable it from the project's Analytics dashboard after
the first deployment.

### CORS configuration

#### Development

Run the frontend at `http://localhost:3000` and the backend at
`http://localhost:8000` with:

```env
CORS_ORIGINS=http://localhost:3000
```

#### Production

Set `CORS_ORIGINS` on the backend hosting platform to every browser origin
that should call the API. Include the Vercel-generated domain and any custom
domain, separated by commas with no wildcard:

```env
CORS_ORIGINS=https://your-app.vercel.app,https://your-domain.com
```

Origins must include the scheme and exact host, without a trailing slash. The
backend allows `GET`, `POST`, and `OPTIONS`, accepts the `Content-Type` header,
and enables credentials for authenticated browser requests. The frontend must
use `credentials: 'include'` when it needs to send cookies; bearer tokens still
need to be supplied in the request headers.

After changing `CORS_ORIGINS`, update the environment variable on the hosting
platform and restart/redeploy the backend. If the browser reports a CORS error,
check that the frontend origin exactly matches one configured value and that
`/api/health` returns `200`. If preflight fails, confirm that `OPTIONS` and
`Content-Type` are present in the request and that the backend has restarted.

## Production Deployment

The backend accepts environment variables from the process environment or a
local `.env` file. Copy `backend/.env.example` to `.env` at the repository root
and replace the placeholders; never commit the resulting file or its secrets.

### Development configuration

```env
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_URL=
GENERATOR_BACKEND=local
GENERATOR_API_BASE=
GENERATOR_API_KEY=
GENERATOR_API_MODEL=
MODEL_NAME=qwen/qwen-2.5-1.5b-instruct
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
HF_TOKEN=
CORS_ORIGINS=http://localhost:3000
```

Development mode allows the database, external model key, and production
origins to remain unset. For production, use `GENERATOR_BACKEND=openai` and
the `GENERATOR_API_*` variables for an OpenAI-compatible hosted model. The
legacy `OPENAI_*` names are accepted for compatibility only.

### Production configuration

```env
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=postgresql://user:password@host:5432/diu_admission
GENERATOR_BACKEND=openai
GENERATOR_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
GENERATOR_API_KEY=your-secret-key
GENERATOR_API_MODEL=gemini-2.5-flash
MODEL_NAME=qwen/qwen-2.5-1.5b-instruct
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
HF_TOKEN=your-hugging-face-token
CORS_ORIGINS=https://your-app.vercel.app,https://your-domain.com
```

In production, `DATABASE_URL`, `GENERATOR_API_BASE`, and `CORS_ORIGINS` must be
non-empty. CORS origins are comma-separated exact browser origins; do not add a
trailing slash. The application validates these settings during startup and
stops instead of serving with an incomplete production configuration.

Start the production backend with:

```bash
sh -c 'uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}'
```

The startup hook logs the environment, normalized CORS origins, whether the
database and model endpoint are configured, the RAG backend, and a UTC
timestamp. Secrets and database passwords are never written to logs. In
production, a missing `DATABASE_URL`, `GENERATOR_API_BASE`, or `CORS_ORIGINS`
causes startup to fail with a specific error before requests are accepted.

Verify a running deployment with:

```bash
curl http://localhost:8000/api/live
curl http://localhost:8000/api/ready
```

`/api/live` is a fast process check. `/api/ready` and `/api/health` include
bounded checks for the database, model endpoint, and RAG backend. The legacy
`/health` path returns the same detailed response for existing clients. A check
may be `not_configured` in development or `error` when an optional dependency
is unavailable; the HTTP response still returns `200` so orchestration can
distinguish process availability from a dependency outage.

### Common startup errors

- `DATABASE_URL required in production` — set a PostgreSQL `DATABASE_URL`.
- `GENERATOR_API_BASE required in production` — set the OpenAI-compatible model
  service URL.
- `CORS_ORIGINS required in production` — set comma-separated browser origins,
  such as `https://your-app.vercel.app`.

### Restart and monitoring

For local development, stop the running Uvicorn process with `Ctrl-C`, activate
the environment again if needed, and rerun the development command. For a
container or process manager, restart the backend using the same command after
updating environment variables, then call `/api/live` and `/api/ready` and inspect startup
logs. Keep the health endpoint in the deployment's liveness/availability
monitor and alert on dependency checks reporting `error`.

## Current status

Phase 5 cleaning and normalization is implemented. The immutable raw snapshot
feeds traceable cleaned records under `data/cleaned/v2/`; embedded PDF text,
reliable tables, source currency states, manual-review states, hashes, and complete
raw lineage are preserved. Validation passes, while the cleaned dataset remains
truthfully partial because the BBA page is a non-substantive shell and the captured
noticeboard has no admission-related entry.

The retrieval layer converts that snapshot into traceable, structure-aware evidence
chunks with authority-gated semantic retrieval (production: PostgreSQL + pgvector; a
local JSON store for development). The FastAPI backend exposes `GET /api/live`,
`GET /api/ready`, and detailed `GET /api/health` (`GET /health` remains a compatibility alias),
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
Generated raw, cleaned, KB, evaluation, and research artifacts are ignored by Git; retain them in backed-up
research storage together with their manifests.

Build or search the retrieval index after completing the PostgreSQL setup in
[`docs/backend/rag_retrieval.md`](docs/backend/rag_retrieval.md):

```bash
python scripts/build_knowledge_base.py --dry-run
python scripts/build_knowledge_base.py
python scripts/search_knowledge.py "What documents are required for DIU admission?"
```

## Deployment

The deployment target is a Vercel frontend plus a separate Python backend host.
Use [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for the complete
preflight and post-deployment checklist, [ENV_VARIABLES.md](ENV_VARIABLES.md)
for provider settings, and [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for
recovery steps.

### Frontend deployment to Vercel

Prerequisites: a Vercel account, this repository connected to GitHub, and the
backend URL after backend deployment.

1. In Vercel, choose **Add New Project** and select this repository.
2. Set the project Root Directory to `frontend/`. Vercel uses the committed
   `frontend/vercel.json` settings (`npm ci`, `npm run build`, `.next`).
3. Add these Production environment variables:

   ```text
   NEXT_PUBLIC_API_URL=https://your-backend.example
   NEXT_PUBLIC_USE_MOCK_API=false
   ```

4. Deploy and visit the generated `https://your-app.vercel.app` URL.
5. Test chat, eligibility, programs, sources, and the browser console. New
   commits to the configured branch trigger redeployments automatically.

To roll back, select a previous deployment in the Vercel dashboard and choose
**Redeploy**, or revert the deployment commit and push it to the configured
branch.

### Backend deployment

Railway is the simplest Git-based option; Fly.io provides multi-region control;
Render and similar Python hosts are also supported. For any provider:

1. Create an account and connect this GitHub repository.
2. Add the production variables listed in [ENV_VARIABLES.md](ENV_VARIABLES.md),
   including `APP_ENV=production`, PostgreSQL `DATABASE_URL`,
   `GENERATOR_BACKEND=openai`, `GENERATOR_API_BASE`, `GENERATOR_API_KEY` when
   required, and the Vercel origin in
   `CORS_ORIGINS`.
3. Set the deploy/start command:

   ```bash
   sh -c 'uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}'
   ```

4. Deploy and copy the public backend URL.
5. Verify it before deploying the frontend:

   ```bash
   curl https://your-backend.example/api/health
   ```

For Railway, create **New Project → Deploy from GitHub**, select this
repository, add variables, and deploy. For Fly.io, authenticate with `flyctl`,
run `flyctl launch` from the repository, set secrets with `flyctl secrets set`,
and deploy with `flyctl deploy`. Keep all provider secrets in the provider's
secret manager, not in Git.

### Verify frontend-backend communication

From the deployed frontend browser console:

```javascript
fetch('https://your-backend.example/api/health', { credentials: 'include' })
  .then((response) => response.json())
  .then((data) => console.log('✅ CORS working:', data))
  .catch((error) => console.error('❌ Error:', error));
```

The backend must report HTTP `200`, and the response checks should match the
configured database, model endpoint, and RAG backend. If the frontend cannot
connect, verify `NEXT_PUBLIC_API_URL`, exact `CORS_ORIGINS`, provider logs, and
restart the backend after environment changes.
