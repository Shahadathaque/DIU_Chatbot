# TASK-18 — Build Hosted Vector Index and Verify Deployment Readiness

Status: Complete

## Objective

Configure the user-provided hosted model credentials locally, validate hosted
generation and embeddings, rebuild the complete v2 knowledge base into an
isolated Neon pgvector table, and verify that the lightweight production backend
can start and answer requests without local cleaned or model files.

## Acceptance criteria

- Hosted model authentication is tested without logging the credential.
- A representative hosted generation request succeeds.
- A representative hosted embedding request returns exactly 768 finite values.
- The complete validated v2 dataset is embedded with the hosted model and stored
  in `diu_knowledge_chunks_hosted` without modifying the existing E5 table.
- Neon metadata records the hosted embedding model and dimension.
- Representative English, Bangla, and Banglish retrieval succeeds against the
  hosted table.
- Production configuration validation passes with database catalogs, pgvector,
  hosted generation, hosted embeddings, and exact CORS configuration.
- The production backend starts without local data/model dependencies and its
  liveness/readiness and catalog endpoints succeed.
- Existing offline unit tests remain green.
- No secret or generated artifact is committed or printed.

## Constraints

- Do not change admission facts, eligibility rules, scraped/cleaned data, RAG
  ranking behavior, or frontend behavior.
- Do not commit `.env`, credentials, model weights, or generated datasets.
- Do not log database passwords, provider keys, or full connection strings.
- Treat any credential pasted into chat as compromised and require replacement
  before public deployment.
- Do not modify or replace the existing local E5 research index.
- Stop before an external hosting deployment if the hosting account is unavailable
  or the production secrets have not been rotated.

## Verification

- Hosted generation returned a complete grounded answer with minimal reasoning.
- Hosted embeddings returned 768 finite values using `gemini-embedding-2`.
- Neon table `diu_knowledge_chunks_hosted` contains 264 chunks from 18 documents.
- English, Bangla, and Banglish retrieval returned the official admission checklist.
- Production startup, liveness, readiness, 52 programs, 18 sources, and chat passed
  with nonexistent local artifact paths and offline Hugging Face settings.
- Offline unit suite: 349 passed, 41 integration tests deselected.
