# TASK-17 — Neon Runtime Catalog, Hosted Inference, and Backend Deployment Preparation

Status: Complete

## Objective

Make the deployed FastAPI backend independent of local cleaned-data and model
files by storing the runtime program/source catalog in Neon, supporting hosted
OpenAI-compatible generation and embeddings, and producing a lightweight,
documented backend deployment artifact.

## Acceptance criteria

- Neon schema stores program and official-source runtime records with provenance
  and dataset metadata.
- An idempotent migration command validates the cleaned snapshot and atomically
  synchronizes programs/sources into Neon.
- Production `/api/programs` and `/api/sources` read from Neon and never silently
  fall back to local cleaned files.
- Development/test record injection and an explicit local development mode remain
  available.
- A hosted OpenAI-compatible embedding adapter is configurable and used by both
  knowledge-base indexing and query retrieval.
- Embedding model, revision, and dimensions remain checked by pgvector metadata;
  incompatible embedding spaces cannot be mixed.
- Production validation requires database-backed catalogs, pgvector, hosted
  generation, and hosted embeddings.
- A slim deployment requirements file and container/host configuration exclude
  local model and scraping dependencies.
- Environment examples and deployment documentation contain placeholders only.
- Unit tests cover catalog persistence, production local-file independence,
  hosted embeddings, configuration validation, and deployment configuration.
- Existing tests continue to pass.
- The verified local v2 catalog is synchronized to the configured Neon database,
  if the existing local secret and network access are available.

## Constraints

- Do not change admission facts, eligibility rules, RAG ranking behavior, or
  frontend behavior.
- Do not fabricate or manually fill runtime catalog rows.
- Derive every runtime row from the validated cleaned DIU snapshot and preserve
  source URL, retrieval timestamp, document/content hashes, and dataset metadata.
- Do not commit `.env`, credentials, model weights, or generated datasets.
- Do not log database passwords, provider keys, or full connection strings.
- Keep the local model/embedding paths available for research and offline
  development, but do not include their heavy dependencies in the deployment
  environment.
- Do not deploy or publish externally without the provider credentials and account
  authorization required for that external state change.
