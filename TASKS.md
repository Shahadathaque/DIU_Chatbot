# TASK-01 — Backend API Foundation

## Objective

Connect the existing backend to the already implemented DIU retrieval
pipeline and make the contract endpoints functional without implementing
LLM generation yet.

This task is ONLY backend API integration.

---

# EXISTING COMPONENTS

Already implemented:

- DIU source registry
- scraper
- cleaned data
- RAG chunking
- embeddings
- vector store
- retriever
- FastAPI scaffold
- API contract
- frontend mock API

Do not rewrite these systems.

---

# IMPLEMENT

## 1. POST /api/chat

Flow:

Request
→ validate
→ domain gate
→ retriever
→ retrieve relevant DIU chunks
→ create evidence-based response
→ return sources

IMPORTANT:

A real LLM is NOT required in this task.

Until TASK-02, the response may be a clearly structured evidence summary.

Do NOT pretend it is an LLM-generated answer.

The response must never invent facts.

If retrieval produces insufficient evidence:

return an insufficient-information response.

---

## 2. GET /api/programs

Build the response from the existing cleaned DIU knowledge.

Do not manually type program data unless the existing data source requires
a small mapping layer.

---

## 3. GET /api/sources

Return registered/available DIU sources.

Include:

- title
- URL
- category where available

---

## 4. Error handling

Use the API contract:

error:
{
  "error": {
    "code": "...",
    "message": "...",
    "details": ...
  }
}

Use appropriate HTTP status codes.

---

# DO NOT IMPLEMENT

Do NOT implement:

- LLM generation
- fine-tuning
- eligibility rules
- model training
- new scraper
- new embedding model
- new vector database
- frontend redesign

---

# TESTS

Create/update tests for:

1. Chat valid request
2. Chat insufficient retrieval
3. Chat out-of-domain request
4. Programs endpoint
5. Sources endpoint
6. Invalid request
7. Backend startup

Use mocked dependencies where appropriate.

Tests must not require an external GPU.

Tests must not require a production database.

---

# ACCEPTANCE CRITERIA

The task is complete only if:

[ ] POST /api/chat works

[ ] GET /api/programs works

[ ] GET /api/sources works

[ ] Responses match contracts/api-contract.md

[ ] No fabricated DIU information

[ ] Sources are returned for supported answers

[ ] Insufficient evidence is handled safely

[ ] Existing tests still pass

[ ] New tests pass

[ ] API starts successfully

[ ] No frontend files modified

[ ] No secrets added

---

# REQUIRED FINAL REPORT

Report:

### Implemented

### Files created

### Files modified

### Tests run

### Test results

### API examples

### Known limitations

### Next task

Then STOP.