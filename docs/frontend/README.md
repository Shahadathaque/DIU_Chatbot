# DIU Admission AI — Frontend

Member 2 ownership: `frontend/` and `docs/frontend/`.

## Stack

- Next.js (App Router)
- TypeScript
- Tailwind CSS

## Run locally

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment variables

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_USE_MOCK_API` | `true` (default) uses frontend mock fixtures. Set `false` for live FastAPI. |
| `NEXT_PUBLIC_API_URL` | FastAPI base URL, e.g. `http://localhost:8000` |

Never put server secrets in `NEXT_PUBLIC_*` variables.

## API modes

- **Mock mode** (`NEXT_PUBLIC_USE_MOCK_API=true`): responses come from `frontend/services/mock-api.ts`. Fixtures are labeled as temporary demo data.
- **Real mode** (`NEXT_PUBLIC_USE_MOCK_API=false`): requests go to `${NEXT_PUBLIC_API_URL}/api/...`.

Central client: `frontend/services/api.ts`  
Provisional types: `frontend/types/api.ts`

## API contract status

`contracts/api-contract.md` is not yet in the repository. Frontend types follow the shapes from the master prompt and must be reconciled when the shared contract lands.

Expected endpoints:

- `GET /health`
- `POST /api/chat`
- `POST /api/eligibility`
- `GET /api/programs`
- `GET /api/sources` (reserved; not required for current UI)

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Landing |
| `/chat` | Admission chat |
| `/eligibility` | Eligibility form + results |
| `/programs` | Program directory |

## Scripts

```bash
npm run lint
npm run test
npx tsc --noEmit
npm run build
```

## Boundaries

Do not edit backend/AI folders. Request API changes through the shared contract process.
