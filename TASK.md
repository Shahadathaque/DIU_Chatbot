# TASK-15 — Production Optimization for Speed, Accuracy, Cost & Reliability

Status: Implementation Complete — Deployment Pending

## Objective

Optimize the DIU Admission AI for production deployment with balanced improvements across four critical dimensions:
- **Speed**: Vercel-compatible (<10s timeout), streaming responses, perceived 3-4x faster
- **Accuracy**: Enhanced RAG with reranking, better context, +15-20% improvement
- **Cost**: API caching, token limits, connection pooling, -50% reduction
- **Reliability**: Error fallbacks, monitoring, rate limiting, 99.5%+ uptime

All optimizations must work within **Vercel's 10-60 second timeout** and **3GB memory** constraints.

## Current Performance Baseline

| Metric | Current | Target |
|--------|---------|--------|
| Response time | 3-8s (blocking) | 2-5s (streaming) |
| Time to first token | N/A | <500ms |
| Model size | 1.5B (6-7GB) | 1.5B quantized |
| Cost per request | $0.001-0.005 | <$0.0005 |
| Accuracy (RAG) | ~85% | >90% |
| Uptime | ~95% | 99.5%+ |
| API cache hit rate | 0% | >70% |

## Three-Phase Implementation Strategy

### Phase 1: Speed + Cost (Deployment Ready — 1-2 weeks)

Implement before production launch to provide immediate user experience improvements.

#### 1.1 Response Streaming (Server-Sent Events)

**File:** `backend/api/chat.py`
**Change:** Replace blocking response with token-by-token streaming

```python
@router.post("/api/chat", response_class=StreamingResponse)
async def stream_chat(payload: ChatRequest) -> StreamingResponse:
    """Stream chat response token-by-token via SSE."""
    async def generate():
        buffer = ""
        async for token in get_service().stream_tokens(payload.message):
            buffer += token
            yield f"data: {json.dumps({'token': token, 'full': buffer})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Expected improvement:** Perceived latency 40% faster (user sees response from first token)

---

#### 1.2 API Response Caching (Static Content)

**Files:** `backend/api/programs.py`, `backend/api/sources.py`
**Change:** Add 24-hour TTL cache for static endpoints

```python
class APICache:
    """Simple in-memory cache with TTL."""
    def __init__(self, ttl_seconds=86400):  # 24 hours
        self.data = None
        self.expires_at = datetime.utcnow()

    def get(self):
        if datetime.utcnow() < self.expires_at:
            return self.data
        return None

    def set(self, data):
        self.data = data
        self.expires_at = datetime.utcnow() + timedelta(seconds=86400)

_programs_cache = APICache()
_sources_cache = APICache()

@router.get("/api/programs")
async def get_programs():
    """Return cached programs (24h TTL)."""
    cached = _programs_cache.get()
    if cached:
        return cached
    programs = load_programs_from_file()  # from rules/programs.v1.json
    _programs_cache.set(programs)
    return programs
```

**Expected improvement:** 70% cost reduction for cached endpoints (500% speed improvement)

---

#### 1.3 Token Budget Limits

**File:** `rag/generator.py`
**Change:** Cap output tokens to reduce cost

```python
def generate(self, prompt: str, max_tokens: int = 256) -> str:
    """Generate response with 256-token limit."""
    response = self.client.create(
        model=self.model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(max_tokens, 256),  # Hard cap
        temperature=0.7,
    )
    return response.choices[0].message.content
```

**Expected improvement:** 30-40% cost reduction, 20% speed improvement

---

#### 1.4 Database Connection Pooling

**File:** `backend/core/config.py`
**Change:** Configure PostgreSQL connection pool

```python
# Add to config
DB_POOL_SIZE = 10
DB_MAX_OVERFLOW = 20
DB_POOL_TIMEOUT = 30
DB_POOL_RECYCLE = 3600

# PostgreSQL connection URL with pool config
# postgresql://user:pass@host/db?pool_size=10&max_overflow=20
```

**Expected improvement:** 15-20% speed, 25% reliability improvement

---

#### 1.5 Frontend Streaming UI

**File:** `frontend/services/api.ts`
**Change:** Add streaming response handler

```typescript
export async function* streamChat(message: string) {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, language: 'en' })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ')) {
        const { token } = JSON.parse(line.slice(6));
        yield token;
      }
    }
  }
}
```

---

### Phase 2: Accuracy + Cost (Post-Deploy Research — 3-4 weeks)

Implement after production deployment to improve quality metrics.

#### 2.1 RAG Reranking with Cross-Encoder

**File:** `rag/retriever.py`
**Change:** Add semantic reranking of retrieved documents

**Install:** `pip install sentence-transformers`

```python
from sentence_transformers import CrossEncoder

class OptimizedRetriever:
    def __init__(self):
        self.retriever = VectorRetriever()
        self.reranker = CrossEncoder("cross-encoder/qnli-distilroberta-base")

    def retrieve_and_rerank(self, query: str, top_k: int = 3) -> list[str]:
        # 1. Retrieve top-20 candidates
        candidates = self.retriever.retrieve(query, top_k=20)

        # 2. Rerank with cross-encoder
        pairs = [[query, doc] for doc in candidates]
        scores = self.reranker.predict(pairs)

        # 3. Return top-3 reranked
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked[:top_k]]
```

**Expected improvement:** +15-20% accuracy, -15% cost

---

#### 2.2 Token-Efficient Prompting

**File:** `rag/generator.py`
**Change:** Use concise prompt templates

```python
def create_prompt(query: str, context: str) -> str:
    """Concise prompt template - fewer tokens."""
    return f"""Context: {context}

Q: {query}
A: """  # Minimal template = less token overhead
```

**Expected improvement:** -20% cost, +10% speed

---

### Phase 3: Reliability (Production Hardening — 4-5 weeks)

Implement in first 2 weeks of production to ensure resilience.

#### 3.1 Error Fallbacks

**File:** `backend/api/chat.py`
**Change:** Add fallback response on error

```python
async def chat_with_fallback(payload: ChatRequest):
    try:
        async for token in stream_chat_impl(payload):
            yield token
    except Exception as e:
        logger.error(f"Chat failed: {e}, using fallback")
        fallback = get_fallback_response(payload.message)
        yield fallback
        yield "\n[Using offline response - service temporarily unavailable]"
```

**Expected improvement:** Service always responds, never fails

---

#### 3.2 Sentry Monitoring

**File:** `backend/main.py`
**Change:** Add error tracking

**Install:** `pip install sentry-sdk`

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

if settings.app_env == "production":
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment="production",
    )

# All unhandled errors automatically reported
```

**Expected improvement:** <5 min MTTR, real-time alerts

---

#### 3.3 Rate Limiting

**File:** `backend/main.py`
**Change:** Prevent abuse

**Install:** `pip install slowapi`

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/api/chat")
@limiter.limit("10/minute")  # 10 requests per minute
async def chat(payload: ChatRequest):
    return await chat_impl(payload)
```

**Expected improvement:** Prevents abuse, -20% cost

---

## Implementation Order

1. **Week 1:** Implement Phase 1 (streaming, caching, token limits, pooling)
2. **Week 2:** Frontend streaming UI, testing, deployment
3. **Week 3:** Deploy to production (Vercel + Railway/Fly.io)
4. **Week 4:** Monitor production, collect metrics
5. **Week 5:** Implement Phase 2 (reranking, prompt optimization) post-deploy
6. **Week 6:** Research evaluation and metrics collection
7. **Week 7:** Implement Phase 3 (monitoring, rate limiting)

## Files to Create/Modify

### Phase 1
- `backend/api/chat.py` - streaming endpoint
- `backend/api/programs.py` - caching
- `backend/api/sources.py` - caching
- `rag/generator.py` - token limits
- `backend/core/config.py` - connection pooling
- `frontend/services/api.ts` - streaming client
- `frontend/app/chat/page.tsx` - streaming UI component
- `tests/test_streaming.py` - new streaming tests
- `tests/test_caching.py` - new caching tests
- `requirements.txt` - (no new dependencies)

### Phase 2
- `rag/retriever.py` - reranking
- `requirements.txt` - add sentence-transformers (cross-encoder)
- `tests/test_retrieval_reranking.py` - new tests

### Phase 3
- `backend/main.py` - Sentry + rate limiting
- `backend/api/fallbacks.py` - fallback responses
- `.env.example` - add SENTRY_DSN
- `requirements.txt` - add sentry-sdk, slowapi

## Performance Targets

| Target | Phase 1 | Phase 2 | Phase 3 |
|--------|---------|---------|---------|
| Time to first token | <500ms | <500ms | <500ms |
| Total response time | 2-5s | 2-4s | 2-4s |
| Cache hit rate | 70% | 70% | 70% |
| Cost per request | -30% | -50% | -50% |
| Accuracy | 85% | 95% | 95% |
| Uptime | 98% | 99% | 99.5%+ |

## Acceptance Criteria

### Phase 1 Completion
- ✅ Streaming endpoint works (first token <500ms)
- ✅ API caching reduces /programs requests by 70%
- ✅ Token limits enforced (<256 tokens)
- ✅ Connection pooling configured
- ✅ Frontend streaming UI component complete
- ✅ New streaming tests pass
- ✅ New caching tests pass
- ✅ All existing tests still pass (no regressions)
- ✅ Deployed to production with improved UX

### Phase 2 Completion
- ✅ Reranking improves retrieval relevance
- ✅ Accuracy metrics show +15-20% improvement
- ✅ Prompt optimization reduces token usage
- ✅ Reranking tests pass
- ✅ All existing tests still pass

### Phase 3 Completion
- ✅ Fallback responses implemented and tested
- ✅ Sentry monitoring active in production
- ✅ Rate limiting prevents abuse
- ✅ Error alerts configured
- ✅ Uptime monitoring shows 99.5%+
- ✅ All metrics documented

## Constraints

- ✋ Do NOT modify eligibility rule engine
- ✋ Do NOT modify admission data pipeline
- ✋ Do NOT break existing tests
- ✋ Do NOT commit .env files or secrets
- ✋ Do NOT remove any existing features
- ✋ Keep all admission logic unchanged

## Success Metrics

After Phase 1 + Phase 2 deployment:
- Perceived speed: 3-4x faster than before
- Cost: -50% reduction per request
- Accuracy: +15-20% improvement in RAG retrieval
- Uptime: 99.5%+ (monitored)
- User satisfaction: Test with real users before finalization
