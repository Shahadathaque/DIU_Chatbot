# Automatic DIU knowledge refresh

The production refresh is a scheduled, registry-driven job. It is deliberately
separate from FastAPI requests and the Next.js frontend.

## Flow

Every 12 hours, `.github/workflows/refresh-knowledge.yml` runs:

1. Collect every active or manual-review source in `data/source_registry.csv`
   into a new append-only `.refresh-work/<version>/raw/` snapshot.
2. Stop if any selected source failed, returned no successful capture, or if the
   raw manifest/integrity validator reports an error.
3. Clean into a new candidate directory and run the full cleaned-dataset
   validator. The small 18-source corpus is re-cleaned for deterministic
   cross-document duplicate analysis; only new or changed chunks are embedded.
4. Require non-empty tuition and program catalogs, unique IDs, required program
   provenance, no failed cleaned extraction, and no program-count collapse below
   50% of the active catalog.
5. Compare stable IDs and content hashes with PostgreSQL. Reuse the stored vector
   for every unchanged chunk and call the configured production embedder only
   for new or changed chunks.
6. Upsert the complete validated chunk snapshot, delete stale chunks, and replace
   the runtime programs/sources in one PostgreSQL transaction.
7. Verify vector, program, and source counts before committing. Any collection,
   cleaning, embedding, database, catalog, or post-check failure returns non-zero
   and leaves the previously published knowledge base intact.

The job prints counts only: unchanged/new/updated/removed chunks, sources, and
programs, plus embedded/reused vector counts. It does not print credentials,
database URLs, provider request bodies, or source contents.

## Configuration

The workflow reads `DATABASE_URL` and `EMBEDDING_API_KEY` from GitHub repository
secrets. Its non-secret model, dimension, table, and backend values must match
the Render service. Changing an embedding model or dimension requires a planned
new-table bootstrap; the refresh refuses incompatible metadata.

The production runtime catalog and pgvector table must be initialized once using
the documented bootstrap commands before enabling the schedule.

## Manual execution and recovery

With the same environment variables configured locally:

```bash
.venv311/bin/python scripts/refresh_knowledge.py
```

Or use **Actions → Refresh DIU knowledge → Run workflow**. GitHub retains the
non-secret refresh snapshot/report artifact for 90 days. If a run fails, inspect
that artifact and the summarized error, repair the source adapter/registry or
provider configuration, then rerun. Do not delete or rebuild the active vector
table as routine recovery—the failed transaction did not replace it.

## How a new program reaches chat

- If DIU adds the program to an already approved catalog or tuition source, the
  next valid snapshot discovers it, derives catalog metadata, builds its chunks,
  embeds the new chunks, and publishes them atomically.
- If DIU publishes it only at a new URL, first review and add that official URL
  to `data/source_registry.csv`. The collector never follows unapproved pages.
- A removed program disappears only after a complete validated collection and a
  candidate that passes the reduction guard.

## External limitations

GitHub Actions schedules are approximate, provider and DIU outages can delay a
run, and a materially redesigned DIU page may need an extractor update. These
conditions fail closed: the existing production snapshot remains active.
