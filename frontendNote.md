# DIU Admission AI — Frontend Viva Note

## 1. Project summary

The frontend is a responsive web interface for the **DIU Admission AI** research
prototype. It gives prospective Daffodil International University students four main
screens: a landing page, an admission chatbot, a deterministic eligibility checker,
and a searchable program directory. The browser displays backend results and official
source links; it does not decide eligibility or invent admission facts.

## 2. Technologies and why they are used

| Technology | Use in this project |
| --- | --- |
| **Next.js 16 App Router** | Provides routing, layouts, page metadata, font loading, and production builds. |
| **React 19** | Builds interactive components and manages form, chat, loading, error, and filter state. |
| **TypeScript** | Defines API/request/response types and catches type errors before runtime. Strict mode is enabled. |
| **Tailwind CSS 4** | Creates the responsive layout, spacing, colors, typography, and component states. |
| **Custom global CSS** | Defines DIU-inspired design tokens, animations, scrollbar behavior, focus styles, and reduced-motion support. |
| **Fetch API** | Connects the browser to the FastAPI backend. |
| **Vitest** | Tests API services and pure frontend logic without requiring a browser or live backend. |
| **ESLint + TypeScript compiler** | Check code quality and type safety. |

No external component library or animation package is used. Reusable SVG icons are
implemented locally, while Geist and Noto Sans Bengali are loaded through Next.js.

## 3. Frontend structure

```text
frontend/
├── app/                 # Routes, root layout, metadata, and global CSS
├── components/          # Chat, eligibility, program, layout, and UI components
├── services/            # API client, mock API, storage, payload, and presentation logic
└── types/api.ts         # Shared frontend API types
```

The route files are small server-rendered page shells. Components that require browser
state, effects, local storage, or user interaction use `"use client"`.

## 4. Pages completed

- **Home (`/`)**: presents the product purpose, main features, research disclaimer,
  multilingual support, and links to Chat and Eligibility.
- **Chat (`/chat`)**: accepts English, Bangla, or Banglish questions, shows suggested
  prompts, conversation history, typing/loading feedback, citations, retry errors, and
  a New Chat action.
- **Eligibility (`/eligibility`)**: loads the supported programs from the backend,
  collects SSC/HSC or diploma information, submits it to the rule-engine endpoint, and
  presents Eligible, Not Eligible, or More Information Required.
- **Programs (`/programs`)**: loads the program catalog, supports client-side search by
  program/faculty/degree, and links to official pages when the API provides a URL.

`Header`, `Footer`, and `ResearchNotice` are shared by every page through the root
layout. The header includes responsive desktop/mobile navigation and active-route
feedback.

## 5. API integration

All requests go through `frontend/services/api.ts`, which keeps network logic out of
the UI components.

| Endpoint | Frontend purpose |
| --- | --- |
| `POST /api/chat` | Sends the question, selected language, and recent conversation history. |
| `POST /api/eligibility` | Sends the academic profile to the deterministic backend rule engine. |
| `GET /api/programs` | Loads the complete program directory. |
| `GET /api/programs?eligibility_only=true` | Loads only the project's supported eligibility-program scope. |
| `GET /api/sources` | Supported by the service layer, but there is currently no separate Sources page. |
| `GET /health` | Supported for backend health checking. |

Two modes are controlled by environment variables:

- `NEXT_PUBLIC_USE_MOCK_API=true`: uses local demo fixtures for isolated frontend work.
- `NEXT_PUBLIC_USE_MOCK_API=false`: calls the real FastAPI service at
  `NEXT_PUBLIC_API_URL`.

The API client applies a 90-second timeout, parses the backend error envelope, handles
unreachable or unreadable responses, and validates important response fields before
returning them to components.

## 6. State and data flow

The main React hooks are:

- `useState` for messages, forms, results, loading states, errors, language, and search.
- `useEffect` for initial data loading and chat restoration/persistence.
- `useRef` for chat scrolling, focus management, and the textarea.
- `useMemo` for efficient program filtering.

Chat flow:

```text
User message → typed request + last 6 turns → FastAPI/RAG → answer + confidence + sources → UI
```

Chat messages and the chosen language are saved in a versioned `localStorage` record.
Invalid, blocked, or corrupted storage fails safely, and New Chat clears it. The request
builder sends at most the latest six conversation turns so follow-up questions retain
context without an unlimited request payload.

Eligibility flow:

```text
Academic form → pathway-specific payload → backend rule engine → status/rules/source → result card
```

For diploma applicants, diploma GPA, discipline, and duration replace irrelevant HSC
fields. The frontend formats the backend decision into a readable requirement table,
but it never recalculates or overrides the decision. Raw rule matches and evidence gaps
remain available inside collapsed research/debug details.

## 7. UX, responsiveness, and accessibility

- Responsive Tailwind breakpoints adapt cards, grids, navigation, forms, and chat for
  mobile, tablet, and desktop screens.
- The chat uses an internally scrollable, viewport-bounded panel with a stable composer.
- Loading skeletons, a typing indicator, empty states, error alerts, retry actions, and
  disabled submit states give clear feedback.
- Official links open safely with `target="_blank"` and `rel="noopener noreferrer"`.
- Semantic labels, `aria-live`, `role="alert"`, keyboard submission, a skip link, and
  visible focus outlines improve accessibility.
- Noto Sans Bengali supports Bangla Unicode. Reduced-motion CSS disables unnecessary
  animation for users who request it.
- A permanent research notice reminds users to confirm important facts with official
  DIU sources.

## 8. Testing approach

Focused Vitest tests cover:

- mock and real API behavior, URLs, request bodies, backend errors, timeouts, and
  unreachable services;
- six-turn chat history construction;
- chat storage persistence, restoration, clearing, corruption, and unavailable storage;
- standard-versus-diploma eligibility payloads;
- eligibility-result presentation for pass, fail, missing, and unverified conditions.

Useful frontend commands are `npm test`, `npm run typecheck`, `npm run lint`, and
`npm run build`.

## 9. Design decisions to explain in a viva

1. **Why is eligibility not calculated in React?** Admission eligibility is a
   deterministic domain decision, so the backend rule engine owns it. The frontend only
   collects input and explains the returned result.
2. **Why keep mock mode?** It allows frontend development and service tests without a
   running backend, while real mode uses the same typed interface.
3. **Why centralize API calls?** It avoids duplicated fetch/error/timeout logic and keeps
   components focused on presentation.
4. **Why use TypeScript types?** They document the frontend-backend contract and catch
   incompatible data use during development.
5. **How are follow-up questions supported?** The latest six user/assistant turns are
   included in each chat request, and conversation state survives reloads in localStorage.
6. **How are hallucinations reduced in the UI?** The UI displays backend-provided source
   links, marks missing citations clearly, and tells users to verify important details.
7. **How is multilingual use supported?** The chat request contains an `en`, `bn`, or
   `banglish` language value, Bangla fonts are loaded, and Unicode responses are rendered
   without translation in the browser.
8. **What is one current limitation?** A dedicated official-sources page is not yet
   implemented even though the source API client exists; answer citations and official
   program/result links are already displayed where available.

## 10. One-minute viva answer

> I developed the frontend of DIU Admission AI with Next.js App Router, React,
> TypeScript, and Tailwind CSS. It has a responsive landing page, multilingual admission
> chat, eligibility form, and searchable program directory. A centralized typed API
> service can switch between mock fixtures and the real FastAPI backend. Chat history is
> persisted locally and the latest six turns are sent for follow-up context. Eligibility
> remains deterministic because the browser never decides it; it only sends applicant
> data to the backend rule engine and presents the returned rules and official source.
> I also added loading, empty, error, retry, mobile navigation, accessibility, reduced
> motion, and focused Vitest coverage for the service and data-transformation logic.
