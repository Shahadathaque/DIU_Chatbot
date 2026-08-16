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
| `RUNTIME_CATALOG_BACKEND` | `database` | Yes in production | Makes programs/sources read Neon instead of private local cleaned files. |
| `RAG_VECTOR_BACKEND` | `pgvector` | Yes in production | Production retrieval backend. |
| `RAG_TABLE_NAME` | `diu_knowledge_chunks_hosted` | Yes in production | Use a new table whenever the embedding space changes. |
| `GENERATOR_BACKEND` | `openai` | Yes in production | Use `local` only for development; production should use a hosted endpoint. |
| `GENERATOR_API_BASE` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Yes in production | OpenAI-compatible hosted model base URL. |
| `GENERATOR_API_KEY` | `provider-key-placeholder` | Yes in production | Backend-only secret; never expose it to Next.js. |
| `GENERATOR_API_MODEL` | `gemini-3.6-flash` | Yes in production | Current model name accepted by the provider. |
| `GENERATOR_API_REASONING_EFFORT` | `minimal` | Recommended for Gemini 3 | Keeps short admission answers fast and prevents hidden reasoning from consuming the response budget. |
| `EMBEDDING_BACKEND` | `openai` | Yes in production | Uses the lightweight hosted embedding adapter. |
| `EMBEDDING_API_BASE` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Yes in production | OpenAI-compatible embeddings base URL. |
| `EMBEDDING_API_KEY` | `provider-key-placeholder` | Yes in production | Backend-only secret. It may equal the generator key. |
| `EMBEDDING_API_MODEL` | `gemini-embedding-2` | Yes in production | Must be the model used to build the configured vector table. |
| `EMBEDDING_DIMENSION` | `768` | Yes in production | Must match the provider output and pgvector table metadata. |
| `CORS_ORIGINS` | `https://your-app.vercel.app,https://your-domain.example` | Yes in production | Exact comma-separated browser origins; never `*`. |
| `MODEL_NAME` | `qwen/qwen-2.5-1.5b-instruct` | No | Model identifier used by the configured model service. |
| `EMBEDDING_MODEL_NAME` | `intfloat/multilingual-e5-base` | Local only | Local research/offline embedding model. Hosted mode derives this from `EMBEDDING_API_MODEL`. |
| `HF_TOKEN` | `hf-token-placeholder` | No | Only for gated Hugging Face assets. |
| `DB_POOL_MIN_SIZE` | `1` | No | Keep small on free PostgreSQL plans. |
| `DB_POOL_MAX_SIZE` | `4` | No | Maximum pooled connections per backend instance. |
| `DB_POOL_TIMEOUT` | `10` | No | Seconds to wait for a pooled connection. |
| `RATE_LIMIT_PER_MINUTE` | `30` | No | Production chat requests per client IP per minute. |
| `SENTRY_DSN` | empty | No | Optional error monitoring; only active when `sentry-sdk` is installed. |

Development defaults are documented in `backend/.env.example`. Production
requires database catalog + pgvector backends, non-empty database/generator/
embedding settings, and exact `CORS_ORIGINS`.
The older `OPENAI_API_BASE` and `OPENAI_API_KEY` names remain accepted as
compatibility aliases but should not be used for new deployments.

## Never commit

- `.env` or `.env.local` files containing real values
- API keys, Hugging Face tokens, database passwords, or auth secrets
- Model weights or generated private datasets

Use `backend/.env.example` and `frontend/.env.example` as safe templates.
