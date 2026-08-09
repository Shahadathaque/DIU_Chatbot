# Frontend

The DIU Admission AI frontend is a Next.js App Router application in `frontend/`.

## Development

```bash
cd frontend
cp .env.example .env.local
npm run dev
```

`NEXT_PUBLIC_USE_MOCK_API=true` keeps development independent from the FastAPI backend. Set it to `false` and provide `NEXT_PUBLIC_API_URL` when the backend is available. The frontend expects the endpoints described in `contracts/api-contract.md`.
