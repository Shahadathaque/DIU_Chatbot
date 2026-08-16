# TASK-19 — Deploy Backend and Connect Vercel Frontend

Status: In Progress

## Objective

Deploy the lightweight FastAPI backend from the current `main` branch, configure
its existing Neon and hosted Gemini runtime secrets in the hosting platform,
deploy the Next.js frontend to Vercel, and verify the complete public application.

## User decision

The user explicitly requested continuing with the existing local credentials
after being informed that credentials previously pasted into chat or screenshots
should be considered exposed. Never copy their values into tracked files, logs,
commands shown in documentation, screenshots, or completion reports.

## Acceptance criteria

- The current repository and deployment configuration are inspected before any
  external changes.
- The backend is deployed from the repository using the committed lightweight
  deployment configuration and production start command.
- Backend secrets are entered only in the hosting provider's secret/environment
  manager and are never committed or printed.
- Production uses the Neon runtime catalogs, hosted pgvector table
  `diu_knowledge_chunks_hosted`, Gemini generation, and 768-dimensional Gemini
  embeddings.
- `/api/live` and `/api/ready` return HTTP 200; readiness reports database,
  model endpoint, RAG backend, and runtime catalog as `ok`.
- Public programs, sources, eligibility, and a grounded chat request are verified.
- The frontend is deployed from `frontend/` with mock mode disabled and its
  public API URL pointing to the deployed backend.
- Backend CORS contains the exact Vercel production origin and no wildcard.
- The deployed frontend successfully calls the backend from a browser.
- Failed chat requests do not leave an empty assistant answer or a misleading
  missing-citation notice in the conversation.
- Relevant local tests/build checks remain green after any required configuration
  changes.
- Deployment URLs and non-secret verification results are documented.

## Expected production settings

- `APP_ENV=production`
- `RUNTIME_CATALOG_BACKEND=database`
- `RAG_VECTOR_BACKEND=pgvector`
- `RAG_TABLE_NAME=diu_knowledge_chunks_hosted`
- `GENERATOR_BACKEND=openai`
- `GENERATOR_API_MODEL=gemini-3.6-flash`
- `GENERATOR_API_REASONING_EFFORT=minimal`
- `EMBEDDING_BACKEND=openai`
- `EMBEDDING_API_MODEL=gemini-embedding-2`
- `EMBEDDING_DIMENSION=768`
- Exact production `CORS_ORIGINS`
- `NEXT_PUBLIC_USE_MOCK_API=false`
- Deployed `NEXT_PUBLIC_API_URL`

Secret values must be read from the ignored local environment only when needed
for provider configuration; never reproduce them in task documentation.

## Manual-action boundary

- The user may need to sign in, authorize GitHub/provider access, select a free
  plan, confirm a deployment, or complete CAPTCHA/account verification.
- Do not enable paid billing, purchase resources, register domains, or change
  account security settings without explicit user approval.
- If the backend provider cannot run the project within its free-plan limits,
  report the measured limitation and present a free alternative before changing
  providers.

## Constraints

- Do not change admission facts, eligibility rules, scraped/cleaned data, RAG
  ranking behavior, or research results.
- Do not rebuild or overwrite the original local E5 index.
- Do not commit `.env`, API keys, passwords, tokens, generated datasets, or model
  weights.
- Do not expose secret values in terminal output, URLs, screenshots, Git history,
  or chat responses.
- Preserve the working local development configuration.
- Stop after TASK-19; do not begin another milestone automatically.
