# TASK: Prepare production deployment configuration

## Goal

Prepare the project for a Vercel-hosted Next.js frontend and separately hosted FastAPI backend.

## Requirements

- Inspect existing frontend and backend deployment configuration.
- Add only necessary production configuration files.
- Add a production-safe FastAPI start command.
- Document frontend and backend environment variables.
- Keep CORS configurable for the deployed frontend.
- Keep secrets out of Git.
- Do not change admission facts, eligibility rules, scraping, or RAG behavior.
- Add/update relevant tests and run them.

## Acceptance criteria

- Frontend backend URL is configurable.
- Backend external model endpoint is configurable.
- FastAPI has a production start command.
- No real credentials are committed.
- Relevant tests pass.