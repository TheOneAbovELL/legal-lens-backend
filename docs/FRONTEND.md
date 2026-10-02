# Frontend

React 19 + TypeScript (strict) + Vite 7, TanStack Query for server state, React Router 7,
`react-markdown` (raw HTML disabled) for answers. No component library: a small set of primitives
styled with CSS variables (`src/styles/tokens.css`). Lives in `frontend/`.

```
frontend/
├── src/
│   ├── main.tsx                 entry (theme bootstrap, providers)
│   ├── app/                     App (routes), AppShell (top bar, sidebar, evidence panel, drawers),
│   │                            providers (Query, Router, Toast, Auth, ErrorBoundary), ConnectionStatus, config
│   ├── components/ui/           Button, Field (Input/Textarea), Badge, Card/Alert/Skeleton, Dialog/Drawer, Menu, Toast, Spinner
│   ├── features/
│   │   ├── auth/                AuthProvider (session state, 401 handling), Login/Signup pages, RequireAuth, AccountMenu, Settings
│   │   ├── chat/                ChatView, MessageList, UserMessage, AssistantMessage, ChatComposer, StatusRow,
│   │   │                        chatReducer (pure state machine), useChat (streaming controller)
│   │   ├── citations/           AnswerMarkdown (citation chips), SourceCard, EvidencePanel, EvidenceContext, SourcePage
│   │   ├── conversations/       Sidebar (list, rename, delete), useConversations (queries + mutations)
│   │   ├── search/              SearchPage, SearchResultCard
│   │   ├── legal/               LegalMappingCard (IPC → BNS)
│   │   └── diagnostics/         DiagnosticsPage (development only)
│   ├── lib/
│   │   ├── api/client.ts        the single HTTP transport (base URL, bearer, request id, timeout, error envelope → ApiError)
│   │   ├── api/index.ts         systemApi, authApi, chatApi, searchApi, conversationApi, legalApi, diagnosticsApi, CLIENT_PATHS
│   │   ├── streaming/sse.ts     POST SSE parser (chunk-boundary safe, malformed-line tolerant, AbortController)
│   │   ├── auth/token.ts        token storage
│   │   └── utils/               errors (typed error → copy), citations, format
│   ├── types/api.ts             frontend view of the backend schemas
│   └── styles/                  tokens.css, global.css
├── tests/                       Vitest + Testing Library (unit + component + contract)
├── e2e/                         Playwright journeys (desktop + mobile)
├── contract/openapi.json        exported by `python scripts/export_openapi.py`
├── Dockerfile, nginx.conf       static build behind nginx with /api proxy (SSE-safe)
└── vite.config.ts               dev proxy for /api, /health, /ready → backend
```

## Routes

| Route | Screen |
|---|---|
| `/login`, `/signup` | authentication (authenticated users are redirected to `/app`) |
| `/app` | workspace: new chat (empty state with example questions) |
| `/app/chat/:conversationId` | a persisted conversation |
| `/app/search` | evidence explorer (retrieval only) |
| `/app/sources/:documentId?chunk=` | full source passage + other passages of the document |
| `/app/settings` | account, theme |
| `/app/diagnostics` | development only (`VITE_ENABLE_DIAGNOSTICS`, off in production builds) |

Unauthenticated access to `/app/*` redirects to `/login` and returns to the intended route after
sign-in. A `401` anywhere clears the session centrally (`setUnauthorizedHandler`).

## Chat flow

1. `ChatComposer` → `useChat.send()` appends an optimistic user bubble and a streaming assistant
   placeholder, then opens `POST /api/v1/chat/stream`.
2. Every SSE event goes through `chatReducer` (pure, unit-tested): `complexity`/`analysis`/`plan`/
   `retrieval`/`evidence` drive the status row ("Analyzing question…", "Finding legal evidence…",
   "Reviewing N candidate passages…", "Generating answer from N sources…"), `token` events append
   text (a new `attempt` number restarts the draft), `citation` events fill the chip list.
3. `complete` is canonical: answer text, citations, mapping alerts, analysis, `message_id`,
   `conversation_id` replace the transient state — one assistant message, never two.
4. `error` events, transport failures and Stop produce `failed` / `incomplete` messages with Retry.
5. When the backend created the conversation, the route switches to `/app/chat/:id` without
   reloading the live state; later visits load history (with stored citations) from the API.

The evidence panel (desktop) / drawer (≤ 1100 px) follows the latest completed answer; clicking a
`[C1]` chip or a source chip selects and scrolls to the card, highlighting question terms in the
excerpt. Mapping cards render only from `bns_alerts` returned by the backend.

## States

Every network feature has idle / loading / streaming / success / empty / error / unauthorized /
degraded states. `ConnectionBanner` polls `/health` and `/ready`: backend down → "Legal Lens backend
is currently unavailable" + Retry; dependencies missing → "Running in degraded mode" naming them
(index, embedding model, LLM, database). Typed backend errors are translated in
`lib/utils/errors.ts`; raw transport messages never reach the screen.

## Configuration

`VITE_API_URL` (empty in dev: the Vite proxy forwards `/api`, `/health`, `/ready` to
`VITE_DEV_PROXY_TARGET`, default `http://127.0.0.1:8000`), `VITE_PORT`, `VITE_ENABLE_DIAGNOSTICS`.
Nothing secret is ever read by the client.

## Commands

```bash
npm install
npm run dev          # http://localhost:5173
npm run lint
npm run typecheck
npm test             # Vitest (unit, component, contract)
npm run contract     # contract test only
npm run build        # production bundle in dist/
npm run test:e2e     # Playwright (starts scripts/e2e_server.py + Vite automatically)
```

## Contract synchronisation

`src/types/api.ts` is hand-written (small, readable). `tests/contract.test.ts` loads
`contract/openapi.json` and checks every `CLIENT_PATHS` entry and every response field the UI
reads; CI fails when the exported OpenAPI document is stale (`python scripts/export_openapi.py`).
