# TASK-16 — Restore Complete v2 Knowledge Base and Neon Index

Status: Complete

## Objective

Regenerate the missing `data/raw/collection-v2-finalized` and
`data/cleaned/v2` artifacts from the registered official DIU sources, validate
their provenance, and rebuild the configured Neon pgvector index.

## Acceptance criteria

- The controlled scraper selects only registered official DIU sources.
- A new immutable v2 raw snapshot is collected without modifying older raw data.
- Raw and cleaned validation complete successfully.
- `data/cleaned/v2/manifest.json` exists and contains the complete validated set.
- The Neon pgvector index is rebuilt from v2.
- A representative retrieval query succeeds against Neon.
- No credentials, generated datasets, or model artifacts are committed.

## Constraints

- Do not change eligibility rules, admission logic, source facts, or model code.
- Do not fabricate or manually fill missing admission information.
- Preserve all existing raw snapshots.
- Use official registered DIU sources and retain provenance/hashes.
- Do not download models when a verified cached artifact is available.
