# AI Architecture

```mermaid
flowchart TD
    DIU[DIU Official Website] --> Registry[Source Registry]
    Registry --> Scraper[Controlled Web Scraping]
    Scraper --> Raw[Immutable Raw Data]
    Raw --> Clean[Cleaning and Normalization]
    Clean --> Dataset[Structured DIU Admission Dataset]

    Dataset --> FTData[Fine-Tuning Dataset]
    Base[Configurable Base LLM] --> Adapter[LoRA / QLoRA]
    FTData --> Adapter
    Adapter --> FTModel[Fine-Tuned Model]

    Dataset --> Chunks[Provenance-Preserving Chunking]
    Chunks --> Embed[Embeddings]
    Embed --> VectorDB[(PostgreSQL + pgvector)]
    VectorDB --> Retriever[Semantic Retriever]

    User[User] --> API[FastAPI]
    API --> Query[Query Processing and Domain Check]
    Query --> Retriever
    Retriever --> Context[Relevant DIU Context]
    Context --> FTModel
    FTModel --> Answer[Grounded Answer + Official Sources]
    Answer --> Frontend[Next.js Frontend]

    Student[Student Data] --> Rules[Deterministic Eligibility Engine]
    Rules --> Result[Eligibility Result]
    Result --> Explain[LLM Explanation]
    Query --> Rules
    Context --> Explain
    Explain --> Answer
```

## Boundaries

- The registry controls collection; the scraper must not crawl the entire domain.
- Raw data is immutable; cleaning, chunking, and dataset generation create versioned derivatives.
- Model and embedding choices remain configurable.
- Eligibility decisions come only from verified deterministic rules; the LLM cannot override them.
- Identity, terminology, clarification, refusal, uncertainty, and response structure are stable fine-tuning behavior.
- Fees, deadlines, notices, requirements, scholarships, and waivers are changing facts supplied primarily through RAG.
- FastAPI owns orchestration and the contract; the frontend contains no admission decision logic.

