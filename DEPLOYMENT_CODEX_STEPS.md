# Vercel Deployment — Step-by-Step Codex Prompts

Follow these steps in order. Copy each prompt into **Codex** and execute.

---

## STEP 1: Frontend Environment Setup for Vercel

**Paste this into Codex:**

```
Frontend environment setup for Vercel deployment.

Current state:
- frontend/.env.example has NEXT_PUBLIC_USE_MOCK_API and NEXT_PUBLIC_API_URL
- Vercel will provide backend URL at deployment time
- Currently uses http://localhost:8000 for local dev

Requirements:
1. Update frontend/next.config.ts to support environment-based backend URL
2. Ensure API client in frontend/services/api.ts uses NEXT_PUBLIC_API_URL
3. Add vercel.json with deployment settings (including analytics)
4. Create frontend/.env.local for local development (already exists?)
5. Document the frontend environment variables needed for Vercel

Implementation:
- Update next.config.ts to add env configuration if needed
- Create vercel.json in the frontend directory with:
  - buildCommand: "npm run build"
  - installCommand: "npm ci"
  - outputDirectory: ".next"
  - cleanUrls: true
  - trailingSlash: false
- Ensure frontend environment variables documentation in README is correct
- Verify that NEXT_PUBLIC_API_URL is used correctly in API calls

Files to check/modify:
- frontend/next.config.ts
- frontend/vercel.json (create if missing)
- frontend/services/api.ts
- frontend/.env.example
- README.md

Do NOT change any admission logic, RAG behavior, or model code.
```

**After Codex completes:** Tell me what was created/modified.

---

## STEP 2: Backend Environment Configuration for Production

**Paste this into Codex:**

```
Backend environment configuration for production deployment.

Current state:
- backend/core/config.py loads from .env using pydantic-settings
- CORS is set to "http://localhost:3000" by default
- Settings include: app_env, log_level, database_url, model_name, etc.

Requirements for production:
1. Add production-safe environment variable names/documentation
2. Support external model endpoint (Qwen or other OpenAI-compatible)
3. Support PostgreSQL database URL
4. Support production CORS origins (Vercel domain)
5. Document all required environment variables for deployment

Implementation:
- Update backend/core/config.py to add:
  - openai_api_base (for Qwen or compatible endpoint)
  - openai_api_key (optional, for auth)
  - production CORS configuration support
  - deployment environment detection (production vs. development)
- Create backend/.env.example with all required variables documented
- Ensure no secrets are exposed in code
- Add validation that required env vars are set in production mode

Files to modify:
- backend/core/config.py
- backend/.env.example
- backend/main.py (CORS configuration)

Do NOT change any admission logic, eligibility rules, or RAG behavior.
```

**After Codex completes:** Tell me what was created/modified.

---

## STEP 3: Backend CORS Configuration for Production

**Paste this into Codex:**

```
Backend CORS configuration for Vercel-hosted frontend.

Current state:
- backend/main.py has CORSMiddleware
- cors_origins comes from settings.cors_origins (comma-separated string)
- Default is "http://localhost:3000"

Requirements:
1. Support production CORS origins (Vercel domain)
2. Keep development CORS working (localhost:3000)
3. Make CORS origins configurable via environment variable
4. In production, CORS must allow the deployed Next.js frontend URL

Implementation:
- Update CORS configuration in backend/main.py to:
  - Parse comma-separated origins from env var (already does this)
  - Add allow_credentials, allow_methods, allow_headers as needed
  - Support production origin format (e.g., https://yourapp.vercel.app)
- Create .env.example with CORS_ORIGINS documented for both dev and prod
- Add validation that at least one origin is configured

Development CORS_ORIGINS=http://localhost:3000
Production CORS_ORIGINS=https://your-app.vercel.app,https://your-app.com

Files to modify:
- backend/main.py (CORS setup)
- backend/.env.example
- backend/core/config.py (if needed for CORS parsing)

Do NOT change any admission data or eligibility logic.
```

**After Codex completes:** Tell me what was created/modified.

---

## STEP 4: Backend Production Start Command

**Paste this into Codex:**

```
Backend production startup command and documentation.

Current requirements:
1. Create a documented production start command
2. Ensure it validates configuration on startup (not at request time)
3. Add health check verification
4. Support environment-based settings
5. No model weights loaded until first request (lazy loading)

Implementation:
1. Create backend/start.sh or document uvicorn start in README
2. Production start command should be:
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
3. Add startup logging to show:
   - App environment (production/development)
   - CORS origins configured
   - Database URL configured (without exposing password)
   - Model endpoint configured (without exposing API key)
4. Update README with "Production Startup" section
5. Ensure health check endpoint (/api/health) returns 200 on startup

Files to create/modify:
- backend/start.sh (optional, for ease)
- README.md (deployment section)
- backend/main.py (startup logging)
- backend/api/health.py (if health check needs update)

Do NOT change any admission logic or RAG behavior.
```

**After Codex completes:** Tell me what was created/modified.

---

## STEP 5: Validate Request Handling (No Model Load on Invalid Request)

**Paste this into Codex:**

```
Ensure invalid API requests return 422 without loading models.

Current state:
- Chat endpoint validates ChatRequest body before building chat service
- Other endpoints should similarly validate before initializing models

Requirements:
1. FastAPI should validate request bodies and return 422 BEFORE any service initialization
2. Models (generator, retriever) should only be loaded after validation passes
3. Tests should verify invalid requests return 422 without model initialization

Implementation:
1. Verify chat.py endpoint:
   - ChatRequest validation happens first (in route)
   - Chat service built only after validation
2. Check other endpoints (eligibility, programs, sources)
3. Add test cases that send invalid JSON/payloads and verify:
   - Status code 422 is returned
   - No model initialization happens
   - Error details are clear

Files to check/modify:
- backend/api/chat.py
- backend/api/eligibility.py
- backend/api/programs.py
- backend/api/sources.py
- tests/test_api_*.py (add 422 validation tests)

Do NOT change admission logic or eligibility rules.
```

**After Codex completes:** Tell me what was created/modified.

---

## STEP 6: Test Verification (Frontend)

**Paste this into Codex:**

```
Verify frontend tests pass for Vercel deployment.

Current state:
- frontend package.json has: test, lint, typecheck commands
- Tests use vitest
- ESLint configured

Requirements:
1. Run all frontend tests and verify they pass
2. Run TypeScript type checking
3. Run linting
4. Verify build succeeds

Implementation:
1. Run: npm run test (in frontend/)
2. Run: npm run typecheck (in frontend/)
3. Run: npm run lint (in frontend/)
4. Run: npm run build (in frontend/)
5. Report results

All must pass with no errors or warnings.

Do NOT commit results, just report back.
```

**After Codex completes:** Run tests locally and tell me the results.

---

## STEP 7: Test Verification (Backend)

**Paste this into Codex:**

```
Verify backend tests pass for Vercel deployment.

Current state:
- Backend uses pytest
- Tests are in tests/ directory
- Unit tests should run offline

Requirements:
1. Run backend unit tests
2. Verify no network calls during tests
3. Tests should pass with local/mocked artifacts

Implementation:
1. Run: python -m pytest tests/ (in backend root)
2. Run with coverage: python -m pytest tests/ --cov=backend --cov=rag
3. Verify all tests pass
4. Report: number of tests, pass count, any failures

Only run unit tests (not integration tests).

Do NOT commit results, just report back.
```

**After Codex completes:** Run tests locally and tell me the results.

---

## STEP 8: Update Deployment Documentation

**Paste this into Codex:**

```
Update README and documentation for Vercel deployment.

Requirements:
1. Add "Deployment" section to README with:
   - Frontend deployment on Vercel
   - Backend deployment on separate host (Railway, Fly.io, etc.)
   - Environment variables needed
   - How to set backend URL in Vercel dashboard
2. Add "Environment Variables" section documenting:
   - Frontend vars (NEXT_PUBLIC_API_URL, NEXT_PUBLIC_USE_MOCK_API)
   - Backend vars (database_url, model endpoint, CORS origins, etc.)
3. Add "Production Setup" section with:
   - Backend startup command
   - Required environment variables
   - Health check verification
4. Ensure no secrets or credentials are documented
5. Keep all existing content about research, architecture, and rules

Files to modify:
- README.md (add deployment sections)
- docs/DEPLOYMENT.md (optional, create detailed deployment guide)

Do NOT change any admission logic, eligibility rules, or architecture.
```

**After Codex completes:** Tell me what was added to documentation.

---

## Summary

After completing all 8 steps, you will have:

✅ Frontend configured for Vercel
✅ Backend configured for production
✅ CORS set up for frontend-backend communication
✅ Production startup command documented
✅ Invalid requests handled with 422 response
✅ All tests passing
✅ Deployment documentation complete

Then you can:
1. Deploy frontend to Vercel
2. Deploy backend to Railway/Fly.io/other host
3. Set environment variables on each platform
4. Test the deployed system
