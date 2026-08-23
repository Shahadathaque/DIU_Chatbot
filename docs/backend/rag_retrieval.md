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
discarded. Each cohort requires its explicit search option, except for a narrow
exact-topic fallback: when a user explicitly names a one-to-one official section
(for example life insurance or guardian guidelines), the retriever may return that
section's partial title-only record solely as verified-link evidence. Chat then
skips generation, returns low confidence, and states that sufficient current
information is unavailable.

Authority adjustments
ensure current/stable evidence ranks above opted-in lower-authority evidence.
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

- application process, online application, and diploma application pathway;
- required documents;
- tuition and fees;
- local/international scholarships, financial aid, waivers, and the waiver calculator;
- program catalog and program information;
- eligibility guidance, deadlines, contacts, and international admission;
- admission-test schedule, seat plan, and result;
- credit transfer, guardian guidance, payment guidance, and life insurance.

Program words no longer imply a catalog request by themselves. Catalog routing
requires list/discovery wording such as “show available programs” or “what
programs does DIU offer?”. Claims such as “all undergraduate students receive a
free laptop” use a fact-check path instead. That path requires the distinctive
claim terms to occur in compatible official evidence, preventing a generic
program grid from being presented as proof. If the claim is present in an
official source, the assistant may answer it from that source; otherwise it
returns insufficient information.

Faculty catalog requests use a shared conservative resolver before the
admission-domain gate. Bare official faculty names and natural discovery wording
such as “Graduate Studies” or “Which programs are in Graduate Studies?” route to
the scoped program catalog. Harmless `and`/`&`, punctuation, capitalization, and
faculty/department wrappers are normalized. Exact faculty wording also outranks
similarly named partial programs (for example Agriculture Sciences versus
Agricultural Science), while program names such as Civil Engineering and
Information Technology remain program-specific. Runtime source metadata remains
the fallback for future faculty labels that are not yet represented by an alias.

Specific intents are resolved before broad ones. In particular, deadlines beat
generic application wording, international scholarships remain distinct from
local scholarships and financial aid, and payment instructions remain distinct
from fee amounts. Explicit faculty, semester, program, or year terms on current
schedule/result/deadline questions must survive evidence filtering.

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

Exact one-to-one topics use a category-scoped candidate lane before generic
semantic ranking. Only candidates from the intent's canonical category are
threshold-exempt, so a short official page is not crowded out by a long generic
admission page. The global thresholds and unrelated-query behavior are unchanged.

## Complete admission-section audit

`scripts/audit_admission_coverage.py` checks every one of the 21 admission-menu
sections against its deterministic intent, registered evidence category, and,
with `--retrieval`, the configured real vector store. Each section has a primary
query plus at least three English, Bangla, Banglish, typo, or short-form variants:

```bash
python scripts/audit_admission_coverage.py
python scripts/audit_admission_coverage.py --retrieval
```

On 2026-08-23, the deterministic mode passed all 21 sections and all 84 query
variants. A prior primary-query-only retrieval run passed 21/21 against the
refreshed 317-chunk pgvector index. The expanded 84-query retrieval mode must be
run from an environment that can reach the configured database; it is not
silently treated as passed when network access is unavailable. The audit covers
admission overview/schedule/seat plan/results, contacts/programs/application,
all guideline topics, local/international tuition and scholarships, payment,
waivers/calculator, financial aid, and life insurance. The separate cleaned-table
tuition audit checks 211 harmless naming variants across all 50 canonical
fee-bearing programs, including undergraduate/postgraduate name ambiguity. The
international tuition audit adds 45 audience-isolation checks across every USD
row and verifies that explicit local/international comparisons retrieve both
compatible rows without currency conversion.

`scripts/audit_query_quality.py` adds an adversarial deterministic gate for typo,
short-query, intent-conflict, audience, follow-up, unsupported-claim, and
multi-program cases. Each failure prints the query, expected resolution, and
actual resolution instead of reducing a quality problem to a single aggregate.

`scripts/audit_faculty_catalog_retrieval.py` derives every faculty and expected
program from the cleaned official program table, then tests bare names,
conjunction variants, and natural catalog wording. Its default deliberately
uninformative embeddings prove that exact faculty metadata—not semantic luck—
selects every row. Pass `--retrieval` to repeat the same complete-faculty audit
against the configured hosted embedding provider and pgvector index.

## Program compatibility and multi-program tuition

Program aliases are normalized for punctuation, whitespace, `and`/`&`, and
common degree spelling variants. Alias matches retain their query spans. The
resolver keeps the most-specific alias within an overlapping span while
preserving independent program mentions elsewhere in the same query. This makes
`Information Technology and Management` beat `management`, without causing a
different-length pair such as `CSE and Master of Pharmacy` to lose one program.

Bare program subjects are also accepted when at least two meaningful words form
a contiguous fragment of exactly one canonical program name. For example,
`Information Technology` resolves to Information Technology & Management even
without words such as “program” or “tuition.” Shared fragments remain unresolved
rather than being guessed; `Business Administration` can refer to more than one
degree and therefore requires clarification.

An explicit postgraduate marker cannot fall back to the undergraduate version.
For program-specific tuition questions, canonical program and degree-level
compatibility take precedence over generic semantic similarity. Multi-program
tuition answers are assembled deterministically from each compatible structured
fee row, so a text generator cannot omit one requested program. No fee value is
hard-coded outside the cleaned tuition evidence.

Tuition audience resolution distinguishes explicit student scope from a requested
display currency. “Local and international” keeps both structured evidence lanes;
“international fees in BDT” remains international evidence and preserves the USD
values actually published by DIU. Deterministic responses label each audience and
currency instead of merging or converting them.

Universal funding claims such as “every undergraduate student gets a
scholarship” use fact-check compatibility rather than the generic scholarship
list path. International document requests likewise cannot fall back to a local
admission checklist.

### Evidence-backed product examples

The chat suggestions correspond directly to collected official records:

- bachelor/online application documents → `DIU-DOC-001`;
- diploma application pathway → `DIU-APP-001`;
- scholarship categories → `DIU-SCH-001`;
- admission steps → `DIU-ADM-002`;
- program catalog → `DIU-PROG-001`.

API citations are created only from the retrieved chunks' stored title and
official source URL. The generator cannot add sources to the response.

If the optional language-generation provider is temporarily unavailable after
verified evidence has been retrieved, chat returns the deterministic grounded
evidence summary with the same official citations instead of a transient 503.
Empty or incompatible retrieval still returns the normal insufficient-information
response; this fallback does not bypass retrieval thresholds or evidence gates.

## Local development fallback

When PostgreSQL is unavailable, set:

```dotenv
RAG_VECTOR_BACKEND=local
RAG_LOCAL_STORE_PATH=data/chunks/local_knowledge_base.json
```

Then run the same builder and search commands. This persists embeddings in a JSON
file for small local tests. It is linear-search, single-process development
storage—not a production replacement for PostgreSQL + pgvector.
