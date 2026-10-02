# Frontend

React 19 + TypeScript (strict) + Vite 7, TanStack Query for server state, React Router 7,
`react-markdown` (raw HTML disabled) for answers, `lucide-react` for icons. The visual system is
documented in [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md); the redesign rationale in
[FRONTEND_REDESIGN_AUDIT.md](FRONTEND_REDESIGN_AUDIT.md) and [FRONTEND_REDESIGN_REPORT.md](FRONTEND_REDESIGN_REPORT.md).
Lives in `frontend/`.

```
frontend/
├── src/
│   ├── main.tsx                  entry (providers, global styles)
│   ├── app/                      App (routes, LoadingScreen), AppShell (top bar, collapsible sidebar,
│   │                             evidence pane / drawer / sheet), providers, ConnectionStatus (net line), config
│   ├── components/
│   │   ├── ui/                   Button/IconButton, Field (Input/Textarea/Select), Badge/StatusText, Chip (CitationChip,
│   │   │                         SourcePreview), Tooltip, Overlay (Dialog/Drawer/Sheet), Feedback (Notice/Skeleton),
│   │   │                         Avatar, Toast, Menu, Spinner
│   │   └── layout/               Brand (mark + wordmark)
│   ├── features/
│   │   ├── auth/                 AuthProvider (session, 401 handling), AuthLayout, Login/Signup pages, RequireAuth
│   │   ├── conversations/        Sidebar (grouped, searchable, rename/delete, about, account), useConversations
│   │   ├── chat/                 ChatView (intro + thread), MessageList, UserMessage, AssistantMessage, ChatComposer,
│   │   │                         ResearchProgress, chatReducer (pure state machine), useChat (streaming controller)
│   │   ├── evidence/             EvidenceContext (selection, next/previous), EvidencePanel (pane/list/tools),
│   │   │                         EvidenceCard, AnswerMarkdown (citation chips), SourcePage (document reader)
│   │   ├── mapping/              MappingComparison (IPC → BNS)
│   │   ├── search/               SearchPage, SearchResult
│   │   ├── settings/             SettingsPage (account, appearance, conversation, privacy, developer)
│   │   └── diagnostics/          DiagnosticsPage (development only, monospace developer surface)
│   ├── hooks/useMediaQuery.ts    breakpoints
│   ├── lib/
│   │   ├── api/client.ts         the single HTTP transport (base URL, bearer, request id, timeout, error envelope → ApiError)
│   │   ├── api/index.ts          systemApi, authApi, chatApi, searchApi, conversationApi, legalApi, diagnosticsApi, CLIENT_PATHS
│   │   ├── streaming/sse.ts      POST SSE parser (chunk-boundary safe, malformed-line tolerant, AbortController)
│   │   ├── auth/token.ts         token storage
│   │   ├── preferences.ts        theme, default retrieval depth, local data reset
│   │   └── utils/                errors (typed error → copy), citations, format
│   ├── types/api.ts              frontend view of the backend schemas
│   └── styles/                   tokens.css (light + dark), global.css
├── tests/                        Vitest + Testing Library (unit, component, contract)
├── e2e/                          Playwright: journey (TEST 1–4 + diagnostics), mobile (TEST 5), visual (snapshots + report captures)
├── contract/openapi.json         exported by `python scripts/export_openapi.py`
├── Dockerfile, nginx.conf        static build behind nginx with /api proxy (SSE-safe)
└── vite.config.ts                dev proxy for /api, /health, /ready → backend; vendor chunking
```

## Routes

| Route | Screen |
|---|---|
| `/login`, `/signup` | split authentication layout (product statement + form); authenticated users are redirected to `/app` |
| `/app` | research workspace: intro with suggested research, composer |
| `/app/chat/:conversationId` | a persisted conversation |
| `/app/search` | legal source explorer (`?q=` runs the query on arrival) |
| `/app/sources/:documentId?chunk=` | document reader with the cited passage highlighted and sibling passages |
| `/app/settings` | account, appearance, conversation, privacy, developer |
| `/app/diagnostics` | development only (`VITE_ENABLE_DIAGNOSTICS`; off in production builds) |

Unauthenticated access to `/app/*` redirects to `/login` and returns to the intended route after
sign-in. A `401` anywhere clears the session centrally (`setUnauthorizedHandler`).

## Research flow

1. `ChatComposer` → `useChat.send()` appends the user turn and a streaming assistant turn, then opens
   `POST /api/v1/chat/stream`.
2. `chatReducer` applies every SSE event: `complexity`/`analysis`/`plan`/`retrieval`/`evidence` drive
   `ResearchProgress` ("Analyzing question", "Searching legal sources" or "Researching N legal
   aspects" with the planner's aspects, "Reviewing N passages", "Preparing answer from N sources");
   `token` events append text (a new `attempt` restarts the draft); `citation` events fill the chips.
3. `complete` is canonical: answer, citations, mapping alerts, analysis, `message_id`,
   `conversation_id` replace the transient state — one assistant message, never two.
4. `error` events, transport failures and Stop produce failed / incomplete turns with "Try again".
5. When the backend created the conversation, the route switches to `/app/chat/:id` without
   reloading the live state (covered by `tests/chat.test.tsx` and E2E TEST 1); later visits load
   history with stored citations.

The evidence pane follows the latest completed answer. A `[C1]` chip (hover: source preview) or a
source chip selects and scrolls to the passage; next/previous step through the message's citations.
On tablets the pane becomes a right drawer, on phones a bottom sheet. Mapping cards render only from
`bns_alerts` returned by the backend.

## States

Every network feature has idle / loading (skeletons) / streaming / success / empty / error /
unauthorized / degraded states. `ConnectionLine` polls `/health` and `/ready` and shows one quiet
line: "Connection interrupted — reconnecting…" (with Retry now) or "Limited mode: … unavailable",
which disappears when the backend recovers. Typed backend errors are translated in
`lib/utils/errors.ts`; raw transport messages never reach the screen.

## Configuration

`VITE_API_URL` (empty in dev: the Vite proxy forwards `/api`, `/health`, `/ready` to
`VITE_DEV_PROXY_TARGET`, default `http://127.0.0.1:8000`), `VITE_PORT`, `VITE_ENABLE_DIAGNOSTICS`.
Nothing secret is ever read by the client; CI greps the bundle for secret-looking strings.

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
npx playwright test e2e/visual.spec.ts --update-snapshots   # refresh visual baselines + docs/screenshots
```

## Contract synchronisation

`src/types/api.ts` is hand-written (small, readable). `tests/contract.test.ts` loads
`contract/openapi.json` and checks every `CLIENT_PATHS` entry and every response field the UI
reads; CI fails when the exported OpenAPI document is stale (`python scripts/export_openapi.py`).
