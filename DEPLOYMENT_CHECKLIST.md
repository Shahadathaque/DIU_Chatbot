# DIU Admission AI Deployment Checklist

Use this checklist after replacing every placeholder with provider-specific
values. Never paste credentials into this file or commit a real `.env` file.

## Pre-deployment local verification

- [ ] Backend tests pass: `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv311/bin/python -m pytest tests/ -q`
- [ ] Frontend tests pass: `cd frontend && npm test`
- [ ] Frontend typecheck passes: `cd frontend && npm run typecheck`
- [ ] Frontend lint passes: `cd frontend && npm run lint`
- [ ] Frontend production build succeeds: `cd frontend && npm run build`
- [ ] Dependency audit and clean install pass: `cd frontend && npm audit`, `npm ci --dry-run`
- [ ] No secrets are tracked: inspect `git status` and review staged files
- [ ] Local backend health check returns `200`: `curl http://localhost:8000/api/health`
- [ ] Local frontend serves successfully at `http://localhost:3000`

## Backend deployment

- [ ] Create/populate PostgreSQL + pgvector using [docs/backend/neon_setup.md](docs/backend/neon_setup.md)
- [ ] Rotate any database/provider secret previously shared in chat, logs, or screenshots
- [ ] `scripts/sync_runtime_catalog.py --dry-run` reports the expected programs/sources
- [ ] Synchronize the runtime catalog to Neon and set `RUNTIME_CATALOG_BACKEND=database`
- [ ] Rebuild a new pgvector table with the configured hosted embedding model
- [ ] Confirm `RAG_TABLE_NAME`, `EMBEDDING_API_MODEL`, and `EMBEDDING_DIMENSION` match that table
- [ ] Create a Railway, Fly.io, Render, or equivalent account
- [ ] Connect the GitHub repository
- [ ] Set production variables from [ENV_VARIABLES.md](ENV_VARIABLES.md)
- [ ] Set the deploy command to `sh -c 'uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}'`
- [ ] Confirm PostgreSQL and the OpenAI-compatible model endpoint are reachable
- [ ] Deploy successfully and record the backend URL

### Verify the backend

- [ ] `curl https://your-backend.example/api/health` returns `200`
- [ ] `/api/live` returns quickly and `/api/ready` reports database, model endpoint, RAG, and runtime catalog states
- [ ] Provider logs show production startup validation succeeded
- [ ] `CORS_ORIGINS` includes every Vercel/custom frontend origin
- [ ] `POST /api/chat` returns a contract-shaped response
- [ ] `POST /api/eligibility` returns a deterministic decision
- [ ] `GET /api/programs` and `GET /api/sources` return data
- [ ] Invalid requests return `422` without model initialization

## Frontend deployment on Vercel

- [ ] Create or select a Vercel project
- [ ] Set the project root directory to `frontend/`
- [ ] Confirm the build command is `npm run build` and install command is `npm ci`
- [ ] Set `NEXT_PUBLIC_API_URL=https://your-backend.example`
- [ ] Set `NEXT_PUBLIC_USE_MOCK_API=false`
- [ ] Deploy and record the Vercel URL

### Verify the frontend

- [ ] Vercel URL loads without 404s or build errors
- [ ] Browser console has no failed API or CORS requests
- [ ] Chat sends and displays a response
- [ ] Eligibility page loads and submits a check
- [ ] Programs and sources pages load
- [ ] English, Bangla, and Banglish UI flows behave as expected

## Post-deployment communication tests

- [ ] Run the browser-console health request from `TROUBLESHOOTING.md`
- [ ] Send a chat request and verify the response in the Network panel
- [ ] Run an eligibility request and verify the response
- [ ] Confirm source links open the official DIU URLs
- [ ] Test a validation error and confirm the frontend displays it safely
- [ ] Test on a mobile browser for responsive layout and touch interaction

## Security and rollback

- [ ] No API key, database password, HF token, or auth secret appears in frontend bundles
- [ ] Production CORS contains exact origins only; never use `*`
- [ ] Provider logs do not print credentials
- [ ] Record the deployed commit and environment-variable version
- [ ] Know how to redeploy the previous Vercel/backend release
- [ ] After an environment change, restart/redeploy and repeat the health check
