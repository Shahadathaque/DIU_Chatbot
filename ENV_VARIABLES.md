# Environment Variables Reference

Use provider secret/environment-variable settings for real values. The values
below are examples only.

## Frontend — Vercel

| Variable | Example value | Required | Notes |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://your-backend.example` | Yes | Public FastAPI origin; no trailing slash. |
| `NEXT_PUBLIC_USE_MOCK_API` | `false` | Yes | Disable mock responses in production. |

`NEXT_PUBLIC_*` values are embedded at build time. Redeploy after changing
them. These values are public; never place a secret in a `NEXT_PUBLIC_*`
variable.

## Backend — Railway/Fly.io/Render/etc.

| Variable | Example value | Required | Notes |
| --- | --- | --- | --- |
| `APP_ENV` | `production` | Yes | Enables production startup validation. |
| `LOG_LEVEL` | `INFO` | No | Defaults to `INFO`. |
| `DATABASE_URL` | `postgresql://user:password@host:5432/diu_admission` | Yes in production | PostgreSQL/pgvector connection string. |
| `GENERATOR_BACKEND` | `openai` | Yes in production | Use `local` only for development; production should use a hosted endpoint. |
| `GENERATOR_API_BASE` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Yes in production | OpenAI-compatible hosted model base URL. |
| `GENERATOR_API_KEY` | `provider-key-placeholder` | Provider-dependent | Backend-only secret; never expose it to Next.js. |
| `GENERATOR_API_MODEL` | `gemini-2.5-flash` | Yes with hosted provider | Model name accepted by the provider. |
| `CORS_ORIGINS` | `https://your-app.vercel.app,https://your-domain.example` | Yes in production | Exact comma-separated browser origins; never `*`. |
| `MODEL_NAME` | `qwen/qwen-2.5-1.5b-instruct` | No | Model identifier used by the configured model service. |
| `EMBEDDING_MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | No | Embedding model identifier. |
| `HF_TOKEN` | `hf-token-placeholder` | No | Only for gated Hugging Face assets. |
| `DB_POOL_MIN_SIZE` | `1` | No | Keep small on free PostgreSQL plans. |
| `DB_POOL_MAX_SIZE` | `4` | No | Maximum pooled connections per backend instance. |
| `DB_POOL_TIMEOUT` | `10` | No | Seconds to wait for a pooled connection. |
| `RATE_LIMIT_PER_MINUTE` | `30` | No | Production chat requests per client IP per minute. |
| `SENTRY_DSN` | empty | No | Optional error monitoring; only active when `sentry-sdk` is installed. |

Development defaults are documented in `backend/.env.example`. Production
requires non-empty `DATABASE_URL`, `GENERATOR_API_BASE`, and `CORS_ORIGINS`.
The older `OPENAI_API_BASE` and `OPENAI_API_KEY` names remain accepted as
compatibility aliases but should not be used for new deployments.

## Never commit

- `.env` or `.env.local` files containing real values
- API keys, Hugging Face tokens, database passwords, or auth secrets
- Model weights or generated private datasets

Use `backend/.env.example` and `frontend/.env.example` as safe templates.
