# DIU Admission AI — Frontend

Part of a single-developer project (see `AGENTS.md`); `frontend/` and
`docs/frontend/` are maintained here.

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

`contracts/api-contract.md` is the shared contract. `frontend/types/api.ts` is
aligned with it; additive backend fields such as eligibility
`rule_matches`/`evidence_gaps` and source `category` are optional and safely
ignored by the frontend types.

Live endpoints:

- `GET /health`
- `POST /api/chat`
- `POST /api/eligibility`
- `GET /api/programs`
- `GET /api/sources` (no UI page yet)

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

This is a single-developer project; there is no member ownership split (see
`AGENTS.md`). API shape changes are coordinated through the shared contract.
