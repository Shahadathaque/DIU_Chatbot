# DIU RAG Retrieval

This step implements evidence retrieval only. It does not call an LLM, generate
answers, expose `/api/chat`, or change the frontend.

## Architecture

`scripts/build_knowledge_base.py` validates the cleaned v1 manifest and records,
creates structure-aware text/table chunks, embeds them with
`intfloat/multilingual-e5-base`, and upserts them into PostgreSQL with pgvector.
`scripts/search_knowledge.py` embeds a query and returns eligible official-source
chunks. The JSON local backend has the same contract but is only a development
and test fallback.

Default retrieval permits records only when all of these conditions hold:

- `currency_status` is `current_date_sensitive` or `stable_reference`;
- `manual_review` is false; and
- `extraction_status` is `success`.

Historical, uncertain, manual-review, and partial records are stored rather than
discarded. Each cohort requires its explicit search option. Authority adjustments
then ensure current/stable evidence ranks above opted-in lower-authority evidence.
Retrieval also enforces a raw semantic-similarity floor before authority boosts,
uses a small transparent admission-domain gate for unrelated questions, suppresses
near-duplicate results, and supports conservative program aliases such as `CSE`.

## Embedding model

The default is `intfloat/multilingual-e5-base` (768 dimensions). It is an
open-source multilingual retrieval model suitable for English and Bangla; its
shared multilingual space is also a pragmatic fit for code-mixed Banglish. The
implementation uses the model-required `query:` and `passage:` prefixes and
normalized embeddings for cosine search. `EMBEDDING_MODEL_NAME`, revision,
dimension, batch size, and device remain configurable. Changing the model or
dimension requires rebuilding the index because pgvector columns have a fixed
dimension. The default revision is pinned to Hugging Face commit
`d128750597153bb5987e10b1c3493a34e5a4502a`, preventing safe reruns from silently
mixing embeddings from different model revisions.
When selecting another model, configure that model's own immutable revision and
output dimension together, then run a complete `--rebuild`.

## PostgreSQL + pgvector setup (production)

1. Install PostgreSQL 15 or newer and a pgvector server extension with HNSW
   support (pgvector 0.5.0 or newer), or use a managed PostgreSQL service that
   provides it.
2. Create an application database and least-privilege login. For example, from
   an administrator `psql` session:

   ```sql
   CREATE ROLE diu_chat LOGIN PASSWORD 'replace-with-a-secret';
   CREATE DATABASE diu_chat OWNER diu_chat;
   \connect diu_chat
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

   If the application role cannot create extensions, the database administrator
   must run the final statement once. The builder also issues the idempotent
   statement for databases where the role has permission.
3. Copy `.env.example` to `.env` and set a URL appropriate for the environment:

   ```dotenv
   DATABASE_URL=postgresql://diu_chat:replace-with-a-secret@127.0.0.1:5432/diu_chat
   RAG_VECTOR_BACKEND=pgvector
   EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-base
   EMBEDDING_MODEL_REVISION=d128750597153bb5987e10b1c3493a34e5a4502a
   EMBEDDING_DIMENSION=768
   ```
4. Use Python 3.11 and install the pinned dependencies:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
5. Validate/chunk without a model download or database write, then build:

   ```bash
   python scripts/build_knowledge_base.py --dry-run
   python scripts/build_knowledge_base.py
   ```

The builder creates `diu_knowledge_chunks`, a small compatibility-metadata table,
the fixed-width vector column, an HNSW cosine index, and B-tree metadata indexes.
Stable chunk IDs and upserts make ordinary reruns safe. Stale chunks are removed
only for documents processed by that run. Use `--rebuild` only when intentionally
replacing the complete index, such as after changing the embedding model. A
pgvector rebuild performs schema replacement and all inserts in one transaction,
so a failed rebuild rolls back to the previous index.

`--limit N` processes the first N manifest records. A mutating `--limit` build
cannot be combined with `--rebuild`, preventing accidental replacement of the
complete production index with a partial dataset.

## Search

```bash
python scripts/search_knowledge.py "What documents are required for DIU admission?"
python scripts/search_knowledge.py "Tell me about CSE tuition." --top-k 3
python scripts/search_knowledge.py "Spring 2026 admission" --include-historical
```

The CLI prints rank, semantic and relevance scores, chunk text, title, category,
program, official source URL, and currency/manual-review status. A minimum score
and explicit recognition of other named universities suppress unsupported hits.

## Multilingual query understanding

`rag/query_processing.py` classifies user wording before embedding it. The
classification is deterministic and contains no admission facts. It normalizes
spacing and Unicode, recognizes common English, Bangla, and Banglish admission
wording, preserves an explicitly named program, and produces an
evidence-oriented retrieval query for these intents:

- application process and diploma application pathway;
- required documents;
- tuition and fees;
- scholarships and waivers;
- program catalog and program information;
- eligibility guidance, deadlines, contacts, and international admission.

The retriever still applies the official-source, freshness, extraction-quality,
program, and fact-compatibility gates after semantic search. Eligibility
questions retrieve the official program catalog only to confirm the named
program; chat directs the applicant to the deterministic Eligibility Checker
and never converts a catalog match into an eligibility decision.

### Threshold calibration

The production thresholds remain `0.75` semantic similarity and `0.72`
post-ranking relevance. They were not lowered for this change. Reproducible
queries against the 264-chunk Neon index showed why intent reformulation was
needed:

| Query | Previous best semantic score | Canonical-intent score | Official evidence |
| --- | ---: | ---: | --- |
| `How do I apply?` | 0.6833 | 0.8381 | `DIU-ADM-002` admission flow chart |
| `What are the admission requirements?` | 0.7470 | 0.8347 | `DIU-DOC-001` admission checklist |
| `Can diploma students apply?` | 0.7028 | 0.7978 | `DIU-APP-001` online application form |

These measurements explain the earlier refusals and demonstrate improvement
without weakening the global evidence gate. Unsupported topics, another named
university, personal application status, and guaranteed/secret policy claims
still return no evidence.

### Evidence-backed product examples

The chat suggestions correspond directly to collected official records:

- bachelor/online application documents → `DIU-DOC-001`;
- diploma application pathway → `DIU-APP-001`;
- scholarship categories → `DIU-SCH-001`;
- admission steps → `DIU-ADM-002`;
- program catalog → `DIU-PROG-001`.

API citations are created only from the retrieved chunks' stored title and
official source URL. The generator cannot add sources to the response.

## Local development fallback

When PostgreSQL is unavailable, set:

```dotenv
RAG_VECTOR_BACKEND=local
RAG_LOCAL_STORE_PATH=data/chunks/local_knowledge_base.json
```

Then run the same builder and search commands. This persists embeddings in a JSON
file for small local tests. It is linear-search, single-process development
storage—not a production replacement for PostgreSQL + pgvector.
