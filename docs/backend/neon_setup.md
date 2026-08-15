# Neon PostgreSQL + pgvector deployment

This project keeps the authoritative DIU chunks in PostgreSQL for production.
The local JSON index is a development fallback and should not be used as the
only production copy.

## 1. Create the database

1. Create a free Neon project and choose the region closest to your backend.
2. Open the SQL Editor and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Neon exposes a pooled connection string. Use the pooled URL for the web API so
free compute does not create a new TCP connection for every request. Keep the
direct URL available for one-time indexing if the provider recommends it.

## 2. Configure a local indexing environment

The scraper and cleaned snapshot are private/generated artifacts and are not
committed to Git. Run the index build from the same machine where those
artifacts exist:

```bash
source .venv/bin/activate
cp .env.example .env
```

Set the database and production vector backend in `.env`:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require
RAG_VECTOR_BACKEND=pgvector
RAG_TABLE_NAME=diu_knowledge_chunks
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=4
DB_POOL_TIMEOUT=10
```

Do not commit this `.env` file.

## 3. Verify and build the index

First validate the private cleaned snapshot without downloading a model or
writing to the database:

```bash
.venv/bin/python scripts/build_knowledge_base.py --dry-run
```

Then build the complete index. The first run downloads the pinned embedding
model and can take several minutes:

```bash
.venv/bin/python scripts/build_knowledge_base.py --rebuild
```

Use `--rebuild` only after confirming that the cleaned snapshot is complete.
Changing `EMBEDDING_MODEL_NAME`, its revision, or its dimension requires a full
rebuild because pgvector columns have a fixed dimension.

Synchronize the API runtime catalog separately. This validates the same manifest
and stores the program/source rows plus provenance in Neon:

```bash
.venv311/bin/python scripts/sync_runtime_catalog.py --dry-run
.venv311/bin/python scripts/sync_runtime_catalog.py
```

The operation is idempotent and transactional. Production requests then use
`RUNTIME_CATALOG_BACKEND=database`; they do not need `data/cleaned/v2`.

Verify the populated index:

```bash
.venv/bin/python scripts/search_knowledge.py \
  "What documents are required for DIU admission?" --top-k 3
```

## 4. Configure the backend host

Set these backend secrets/environment variables on Cloud Run, Render, Railway,
or another Python host:

```dotenv
APP_ENV=production
RUNTIME_CATALOG_BACKEND=database
RAG_VECTOR_BACKEND=pgvector
RAG_TABLE_NAME=diu_knowledge_chunks_hosted
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require
GENERATOR_BACKEND=openai
GENERATOR_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
GENERATOR_API_KEY=provider-secret
GENERATOR_API_MODEL=provider-flash-model
EMBEDDING_BACKEND=openai
EMBEDDING_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
EMBEDDING_API_KEY=provider-secret
EMBEDDING_API_MODEL=provider-embedding-model
EMBEDDING_DIMENSION=768
CORS_ORIGINS=https://your-app.vercel.app
```

Before deploying chat, rebuild the complete knowledge base into the new hosted
embedding table using these hosted embedding variables. Never point a hosted
query embedder at the existing local E5 table.

Start the service with the platform-provided port:

```bash
sh -c 'uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}'
```

## 5. Verify deployment

Use `/api/live` for a fast liveness probe and `/api/ready` for dependency
readiness:

```bash
curl -fsS https://your-backend.example/api/live
curl -fsS https://your-backend.example/api/ready
```

The readiness response must report the database and RAG backend as `ok`. If the
model endpoint is `error`, check the provider URL, model name, and backend secret
without placing the secret in logs or frontend variables.
