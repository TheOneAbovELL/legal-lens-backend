# Frontend redesign audit (before the premium UI transformation)

Scope: `frontend/` only. The backend, its contracts and the SSE event protocol are frozen and are
used as the source of truth (`frontend/contract/openapi.json`, `docs/API.md`).

## 1. What works (keep)

| Area | State | Decision |
|---|---|---|
| Typed API client (`src/lib/api`) | one transport, bearer, request ids, timeout, error envelope → `ApiError`; no raw fetch in components | **reuse unchanged** |
| SSE parser (`src/lib/streaming/sse.ts`) | chunk-boundary safe, malformed-line tolerant, AbortController; tested | **reuse unchanged** |
| Chat state machine (`chatReducer.ts`, `useChat.ts`) | optimistic send, backend-driven phases, token accumulation, regeneration restart, reconciliation on `complete`, cancel/fail, no reload of a live stream when the created conversation's route appears | **reuse**; extend with sub-query progress and settled streaming state |
| Auth (`AuthProvider`, token store, `RequireAuth`) | validates stored token, central 401 handling, return-to route | **reuse** |
| Conversations data layer (`useConversations.ts`) | TanStack queries + optimistic mutations | **reuse** |
| Evidence selection (`EvidenceContext`) | message-scoped citation list, selected citation, drawer flag | **reuse**; add next/previous navigation |
| Markdown renderer (`AnswerMarkdown`) | raw HTML disabled, stable `MarkdownLink` component type (detached-node bug fixed, covered by E2E) | **reuse**; restyle |
| Error translation (`lib/utils/errors.ts`) | typed codes → human copy | **reuse** |
| Tests (34 Vitest, 5 Playwright) | real behaviour (streams, citations, reload, ownership) | **keep passing**; add coverage for new components |

## 2. What is visually weak

* **Card soup.** Answers, sources, mapping, search results, settings, diagnostics are all bordered
  rounded boxes with shadows; hierarchy comes from borders, not typography.
* **Generic chat look.** User bubble + assistant box + badges reads like a developer test console.
  No product voice in the empty state ("Ask Legal Lens…" + four big buttons).
* **Typography.** Single system sans at 15px; no editorial face for statute titles/source text; weak
  hierarchy between product name, page title, question, answer, evidence, metadata.
* **Colour.** Two near-identical blue accents, a yellow citation colour and four status colours used
  everywhere (badges on every message). Dark theme is an inverted light theme.
* **Icons.** Unicode glyphs and emoji (`☰ ✕ ⋯ ⚠ → ←`) instead of one icon set.
* **Brand.** A magnifier-in-a-square mark and the word "Legal Lens"; no wordmark system, no
  loading/empty-state branding.
* **Sidebar.** Flat list, no grouping by date, no conversation search, footer is a disclaimer line.
* **Evidence.** Right panel is a stack of cards; no "why was this cited" framing, no
  next/previous, mobile drawer is a generic side sheet rather than a bottom sheet.
* **Search.** Results show raw relevance scores and retrieval-source badges to end users.
* **Banners.** Offline/degraded alerts take a full-width block above the conversation.
* **Diagnostics** looks like the product (same cards) instead of a developer surface.

## 3. What is structurally weak

* Visual styles live in one 1,100-line `global.css` keyed by ad-hoc class names; no documented
  design system (tokens exist but are not organised by role).
* `Card.tsx` hosts `Card`, `Skeleton` and `Alert`; `Dialog.tsx` hosts `Dialog` and `Drawer`.
  Primitives such as IconButton, Chip, Tooltip, Sheet, Avatar, Tabs do not exist.
* `SettingsPage` lives under `features/auth`; mapping lives under `features/legal`;
  `ConnectionStatus` under `app`. Acceptable, but the redesign introduces `features/evidence`,
  `features/mapping`, `features/settings` and `components/layout` to match responsibilities.
* `AssistantMessage` mixes layout, actions, trust line and mapping rendering in one component.
* No conversation search, no date grouping, no composer default-profile preference.

## 4. Reuse / redesign / delete / new

| Reuse as-is | Redesign (same contract) | Delete | New |
|---|---|---|---|
| `lib/api/*`, `lib/streaming/sse.ts`, `lib/auth/token.ts`, `lib/utils/*`, `types/api.ts`, `AuthProvider`, `RequireAuth`, `useConversations`, `EvidenceContext` (extended), `chatReducer`/`useChat` (extended), `Toast`, `ErrorBoundary`, `Menu` (restyled) | `AppShell`, `Sidebar`, `ChatView`, `MessageList`, `UserMessage`, `AssistantMessage`, `ChatComposer`, `StatusRow`, `AnswerMarkdown` (chip label), `SourceCard` → `EvidenceCard`, `EvidencePanel`, `SourcePage`, `LegalMappingCard` → `MappingComparison`, `SearchPage`, `SearchResultCard` → `SearchResult`, `LoginPage`, `SignupPage`, `SettingsPage`, `DiagnosticsPage`, `ConnectionStatus`, `Badge`, `Button`, `Field`, `Dialog`/`Drawer` | `Card` (card soup), `AuthBrand` (replaced by `Brand`), `ConnectionBanner` block style, Unicode icon usage | design tokens (`tokens.css` rewritten, light and dark designed separately), typography scale, `IconButton`, `Chip`/`CitationChip`, `Tooltip` (hover source preview), `Sheet` (mobile bottom sheet), `Avatar`, `Tabs` (settings), `Brand` (wordmark + mark), `ResearchProgress` (sub-query status), `MessageActions`, `SourcePreview`, conversation grouping + search, `lucide-react` icons |

## 5. Backend contract check

Every feature in the redesign is backed by an existing endpoint or event:

| UI capability | Backend source |
|---|---|
| Status sequence (analysing → searching → reviewing → preparing) | `intent`/`safety`/`complexity`/`analysis`/`plan`/`retrieval`/`reranking`/`evidence` events |
| "Researching N legal aspects" with per-aspect completion | `plan.subqueries[]` then `retrieval` (all sub-queries retrieved together) |
| Citation chips `[C1] IPC §420`, hover preview, excerpt highlight | `citation` events / `citations[]` with `act`, `section`, `title`, `excerpt`, `source` |
| Evidence next/previous | `citations[]` order on the message |
| Mapping comparison | `bns_alerts[]` (`old`, `new`, `mapping_type`, `subject`, `notes`, `effective`, `verification_status`) |
| Trust line "Based on N retrieved legal sources" | `citations.length`, `disclaimer` |
| Conversation titles | backend titles from the first question; `PATCH` rename |
| Conversation search / date groups | client-side over `GET /conversations` (`title`, `updated_at`) |
| Default retrieval profile preference | existing `profile` request field; preference stored locally |
| Search results without raw scores | `results[]` (`citation`, `snippet`, `content`, `retrieval_sources`, `bns_alert`); numeric scores hidden |
| Degraded line | `/health`, `/ready` |

Not shown because the backend does not support it: upload, deep research, case-law filter beyond
`document_types`, saved research, thumbs/share/export. No backend change is required.

## 6. Plan (phases → commits)

1. design system (tokens, typography, primitives, icons) 2. application shell + sidebar
3. chat (editorial layout, composer, streaming, research progress) 4. evidence (chips, panel,
sheet, source viewer, mapping) 5. search 6. authentication 7. settings + diagnostics
8. responsive + accessibility 9. tests (component, E2E, visual) 10. docs + final polish.
