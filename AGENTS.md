Update the repository's AGENTS.md to become the permanent engineering
instruction for this project.

Project:
DIU Admission AI

Goal:
Build a research-grade but practical AI admission assistant exclusively for
Daffodil International University.

IMPORTANT:
I am the sole developer. There are no separate member ownership boundaries.

The project has two goals:

1. Working product:
   - Chat
   - Eligibility checker
   - Programs
   - Official sources
   - English/Bangla/Banglish support

2. Research:
   Compare:
   A. Base LLM
   B. Fine-tuned LLM
   C. Base LLM + RAG
   D. Fine-tuned LLM + RAG

==================================================
EXECUTION RULES
==================================================

1. NEVER implement the entire project at once.

2. Only work on the task explicitly written in TASK.md.

3. If TASK.md is missing, STOP and ask me to create/select a task.

4. Do NOT automatically move to the next milestone.

5. Before modifying files:
   - inspect the repository
   - inspect relevant existing implementations
   - inspect contracts
   - inspect tests

6. Preserve working code.

7. Do not rewrite functioning components unnecessarily.

8. Every implementation must include appropriate tests.

9. Never claim a test passed unless it was actually executed.

10. Never fabricate:
    - DIU admission requirements
    - tuition fees
    - deadlines
    - scholarship rules
    - eligibility rules
    - research results
    - citations

11. Official DIU sources are authoritative.

12. If a required fact cannot be verified from collected DIU sources,
    mark it as unknown/insufficient information.

13. Never hard-code changing admission facts into the LLM.

14. Changing facts should come through the knowledge/RAG pipeline.

15. Deterministic eligibility decisions must come from the rule engine,
    not from the LLM.

16. The LLM may explain a rule-engine result but may never override it.

17. Never commit:
    - .env
    - API keys
    - tokens
    - passwords
    - model weights
    - large generated artifacts

18. Keep raw scraped data immutable.

19. Maintain data provenance:
    source URL, title, retrieval date, document ID, content hash.

20. Keep research experiments reproducible:
    model version, dataset version, seed, parameters, metrics.

==================================================
ARCHITECTURE
==================================================

Official DIU Sources
        ↓
Source Registry
        ↓
Scraper
        ↓
Raw Data
        ↓
Cleaning
        ↓
Structured Knowledge Base
        ↓
 ┌───────────────┬─────────────────┐
 ↓               ↓                 ↓
RAG           Eligibility      Fine-tuning
 ↓               ↓                 ↓
Retriever      Rule Engine       Dataset
 ↓               ↓                 ↓
Context        Decision          LoRA/QLoRA
 └───────────────┬─────────────────┘
                 ↓
              LLM
                 ↓
              FastAPI
                 ↓
             Next.js

==================================================
TECHNOLOGY
==================================================

Backend:
Python
FastAPI
Pydantic

AI:
PyTorch
Transformers
PEFT
TRL
Accelerate
Sentence Transformers

RAG:
PostgreSQL
pgvector
Local JSON fallback for development

Scraping:
Playwright
BeautifulSoup

Frontend:
Next.js
TypeScript
Tailwind CSS

Testing:
pytest
Vitest

==================================================
RESEARCH REQUIREMENTS
==================================================

The final research must compare:

Base LLM
Fine-tuned LLM
Base LLM + RAG
Fine-tuned LLM + RAG

Use the same held-out evaluation dataset.

Evaluate where applicable:

- factual correctness
- relevance
- groundedness
- hallucination rate
- domain adherence
- refusal accuracy
- English performance
- Bangla performance
- Banglish performance
- retrieval Recall@K
- eligibility correctness
- latency

Never manufacture evaluation results.

==================================================
TASK EXECUTION
==================================================

When executing TASK.md:

1. Read TASK.md completely.
2. Identify acceptance criteria.
3. Inspect relevant code.
4. Implement only the requested task.
5. Run required tests.
6. Fix failures caused by your implementation.
7. Update documentation if required.
8. Update plan.md status.
9. Provide a completion report.
10. STOP.

Do NOT start another task after completion.

==================================================
COMPLETION REPORT
==================================================

Always report:

### Completed
...

### Files created
...

### Files modified
...

### Tests executed
...

### Test results
...

### Manual verification
...

### Known issues
...

### Research impact
...

### Next task
...

Then STOP.