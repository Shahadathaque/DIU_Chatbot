# TASK-PUBLISH — Publish Completed Project Work to GitHub

Status: In progress

This task supersedes the completed `TASK-CATALOG` instructions. Permanent
constraints in `AGENTS.md` remain authoritative.

## Objective

Safely commit the completed, verified source code, tests, contracts, and project
documentation currently in the working tree and push the commit to the existing
GitHub `origin` on the current `main` branch.

## Scope and acceptance criteria

1. Audit the complete commit candidate before staging.
2. Exclude `.env`, credentials, tokens, passwords, model weights, raw/cleaned
   datasets, local KB/vector artifacts, research results, and other large generated
   artifacts.
3. Preserve the current implementation; do not perform new feature work.
4. Confirm the remote branch has not advanced before pushing.
5. Stage only the audited source, tests, rules, configuration examples, and docs.
6. Review the staged diff/stat and run secret/large-file checks.
7. Commit with a descriptive message and push to `origin/main`.
8. Report the pushed commit SHA and stop.

## Prohibited work

- Do not start M6, fine-tuning, training, or research evaluation.
- Do not change eligibility behavior, admission facts, or research results.
- Do not force-push, rewrite history, or delete branches.
- Do not commit ignored/private/generated artifacts.
