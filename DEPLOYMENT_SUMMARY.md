# Deployment Summary

## Project

DIU Admission AI — a Next.js frontend and FastAPI backend for DIU admission
questions, eligibility checks, programs, and official sources.

## Readiness status

- ✅ Frontend unit tests: **14 passing**
- ✅ Backend unit tests: **320 passing**, with 41 integration tests explicitly deselected
- ✅ Frontend TypeScript, ESLint, and Next.js production build pass
- ✅ Backend offline test suite, startup validation, and health checks pass
- ✅ Backend API coverage: 87%; core: 100%; eligibility: 90%; RAG: 77%
- ✅ CORS supports exact localhost/Vercel/custom origins with credentials
- ✅ Environment variables and deployment procedures are documented
- ✅ No model weights, API keys, tokens, passwords, or private datasets are committed

The repository is ready for deployment. External provider deployment itself has
not been performed in this workspace, so the provider URL and production
credentials still need to be supplied by the operator.

## Deployment sequence

1. Deploy the backend to Railway, Fly.io, Render, or another Python host.
2. Set production variables and record the backend URL.
3. Verify `https://your-backend.example/api/health` returns `200`.
4. Set `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_USE_MOCK_API=false` in Vercel.
5. Deploy the frontend with project root `frontend/`.
6. Add the Vercel URL to backend `CORS_ORIGINS` and restart the backend.
7. Run the post-deployment checks in `DEPLOYMENT_CHECKLIST.md`.

## References

- [Deployment checklist](DEPLOYMENT_CHECKLIST.md)
- [Environment variables](ENV_VARIABLES.md)
- [Troubleshooting guide](TROUBLESHOOTING.md)
- [API contract](contracts/api-contract.md)
