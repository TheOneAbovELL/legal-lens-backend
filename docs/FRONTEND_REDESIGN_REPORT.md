# Frontend redesign report

Branch `redesign/premium-frontend`. Backend, API contracts and the SSE protocol were not modified;
`frontend/contract/openapi.json` is unchanged and the backend suite still passes (186 tests).

## 1. Before / after architecture

| | Before | After |
|---|---|---|
| Visual system | one 1,100-line stylesheet, ad-hoc classes, two blues + yellow citations, inverted dark theme | documented tokens (`tokens.css`, light and dark designed separately), typography roles, 4 px spacing, three radii, three elevations; one accent; warm evidence tint |
| Primitives | Button, Field, Badge, Card, Dialog/Drawer, Menu, Toast, Spinner | Button/IconButton, Field (Input/Textarea/Select), Badge/StatusText, CitationChip + SourcePreview, Tooltip, Dialog/Drawer/Sheet, Notice/Skeleton, Avatar, Toast, Menu (arrow keys), Brand |
| Icons | Unicode glyphs and emoji | `lucide-react` only |
| Features | `auth`, `chat`, `citations`, `conversations`, `legal`, `search`, `diagnostics`; settings under `auth` | `auth`, `chat`, `evidence`, `conversations`, `mapping`, `search`, `settings`, `diagnostics`; `components/layout`; `hooks` |
| Unchanged | `lib/api`, `lib/streaming/sse.ts`, `lib/auth/token.ts`, `types/api.ts`, `AuthProvider`, `useConversations`, `useChat`; `chatReducer` extended (research aspects, warnings policy) | |

## 2. Design problems discovered (audit → fixed)

Card soup; generic chat bubbles and badge noise on every message; a single system sans with no
hierarchy; inverted dark theme; emoji/Unicode icons; a flat sidebar without grouping or search;
an evidence panel that was a stack of cards with no "why" and no next/previous; raw relevance scores
and retrieval badges in search; full-width degraded banners; a diagnostics page that looked like the
product; internal pipeline warnings ("LLM decomposition unavailable (JSONDecodeError)…") rendered to
users; brand mark without a wordmark system. Details in `FRONTEND_REDESIGN_AUDIT.md`.

## 3. Design system

See `FRONTEND_DESIGN_SYSTEM.md`: paper/ink palette with one muted-blue accent, Inter for UI and
Source Serif 4 for titles, questions, statute references and passages; 760 px reading column;
restrained motion with reduced-motion support; evidence-first rules (chips, previews, document-like
passages, "why cited" line).

## 4. Major UI changes

* **Shell**: compact top bar (brand, Research / Search / Diagnostics, account), collapsible sidebar
  (state remembered), evidence pane on the right of research views, quiet net-status line.
* **Sidebar**: "New research", conversation search, Today / Yesterday / Previous 7 days / Older
  groups, hover-revealed row menu (rename, delete), footer with Settings, About and account.
* **Empty workspace**: "Research law with evidence, context, and citations." with Ask / Retrieve /
  Verify and four compact suggested-research rows (all real pipeline questions).
* **Conversation**: editorial turns (YOU / LEGAL LENS labels, serif question), answer prose with
  headings/lists/responsive tables, inline `C1` chips with hover previews, Sources row with
  `C1 BNS §318` chips, trust line ("Based on N retrieved legal sources", "Multi-aspect research"),
  actions (View evidence, Copy, Regenerate, Stop), disclaimer.
* **Streaming**: progress line driven by backend events (Analyzing question → Searching legal
  sources / Researching N legal aspects → Reviewing N passages → Preparing answer from N sources),
  four-step indicator, per-aspect checklist from the planner's sub-queries, blinking caret on the
  streaming paragraph; never chain-of-thought.
* **Evidence**: document-like cards (serif reference, document line, "Exact match for a provision
  named in the question" / "Passage ranked relevant…", highlighted question terms, More/Copy/Open
  source), previous/next navigation with position, "Cited for" context; right pane (desktop), right
  drawer (tablet), bottom sheet with grip (phone).
* **Source reader**: kicker, serif title, metadata line, large serif passage with highlights, sibling
  passages, Back to the same conversation.
* **Mapping**: hairline-bounded comparison (source provision → target provision, status word,
  subject, effective date, verification, notes) — no coloured card.
* **Search**: research explorer with filters disclosure, hairline result list (provision, document,
  passage, mapping, Use in research, Open source), selected passage on the right; raw scores and
  retrieval-source badges removed; `?q=` runs on arrival.
* **Auth**: split layout with the product statement (Ask / Retrieve / Verify) and a minimal form
  ("Continue"); phone shows the brand above the form.
* **Settings**: Account, Appearance (system/light/dark segmented), Conversation (default retrieval
  depth, a real request field), Privacy (clear local preferences), Developer (dev builds only).
* **Diagnostics**: monospace developer surface with healthy / degraded / unavailable words and
  expandable raw payloads; banner states it is not part of the product.

## 5. Component architecture

`components/ui` primitives are presentation-only; `features/*` own behaviour; `lib/api` is the only
place that knows endpoint paths; `lib/streaming/sse.ts` the only SSE parser; `chatReducer` is a pure
state machine (`loading conversation` → `idle` → `submitting/analyzing` → `streaming` → `completed`
or `failed/incomplete`). Stable React keys and a module-level `MarkdownLink` component keep citation
nodes attached across re-renders (regression covered by `tests/chat.test.tsx` and E2E TEST 1).

## 6. Responsive strategy

| Width | Layout |
|---|---|
| 1440 / 1280 | sidebar 268/248 px, 760 px reading column, evidence pane 392/340 px |
| 1024 | sidebar, reading column, evidence as right drawer |
| 768 | ☰ drawer sidebar, full-width column, evidence drawer, filters stack |
| 430 / 390 / 375 | icon-only nav, "+" new research, bottom-sheet evidence, sticky composer with safe-area padding, hints hidden, mapping stacked vertically |

Checked by Playwright (`e2e/visual.spec.ts`) at all seven sizes: no horizontal overflow; captures in
`docs/screenshots/`.

## 7. Accessibility

Semantic landmarks (`banner`, `navigation`, `complementary`, `dialog`); every control a real button
or link with a visible focus ring; overlays trap focus, close on Escape, return focus and lock body
scroll; citation chips are buttons with descriptive labels and `aria-pressed`; evidence cards are
focusable and activate with Enter/Space; live regions for progress, toasts and the net line; status
never colour-only; `prefers-reduced-motion` disables animation; contrast ≥ 4.5:1 on all text.

## 8. Testing

| Suite | Count | What it covers |
|---|---|---|
| Vitest (`frontend/tests`) | 41 | reducer phases/aspects/warnings policy, SSE parsing, client errors, contract vs OpenAPI, login/signup/expired session/logout, chat submit → stream → reconcile → citation → evidence, error and insufficient-evidence states, offline line, search results/empty/degraded, **new**: chip labels + keyboard + tooltip, evidence list selection and next/previous, drawer/sheet Escape and close, mapping statuses, research aspects progress, date grouping |
| Playwright desktop | 5 | TEST 1 login → workspace → new research → stream → citation → evidence → source → sign out/in; TEST 2 reload + switch conversations; TEST 3 search → result → evidence → use in research; TEST 4 complex query → backend-driven status (no reasoning text) → multi-aspect answer; moderate; refusal; diagnostics status words |
| Playwright mobile (Pixel 7) | 1 | TEST 5 drawer sidebar → chat → citation → bottom sheet → close; no overflow |
| Playwright visual | 1 | snapshots for login, empty workspace, conversation, evidence, search, mobile conversation (`e2e/__snapshots__`, local platform; skipped on CI) + captures at seven viewports |
| Backend | 186 | unchanged |

`npm run lint`, `npm run typecheck`, `npm run build` pass; the bundle contains no secret-like strings.

## 9. Browser verification

Performed against the real backend (port 8000, real Groq key, local index) and the dev server:
sign-in, suggested research, streamed simple answer with chips and mapping, complex question with
"Researching 3 legal aspects", evidence pane/drawer selection and navigation, source reader and Back,
reload persistence, search with filters, settings theme switch (light and dark inspected), diagnostics;
plus Playwright captures at 1440, 1280, 1024, 768, 430, 390 and 375 px (`docs/screenshots/`).

## 10. Remaining limitations

* History reloaded from the database carries citations but not mapping alerts or analysis (the
  backend stores evidence only), so mapping comparisons appear in live answers, not in reloaded
  history. A backend change could persist `bns_alerts`; out of scope here.
* Mapping citations `[M1]` are rendered as plain text (they reference the mapping block, not a
  passage); only `[C#]` become chips.
* Google Fonts are loaded from the network; offline the system fallbacks (Georgia/Segoe UI) apply.
* Visual snapshots are platform-specific and are not asserted on CI.
* The sidebar collapse control hides the sidebar entirely rather than showing a rail; a rail with
  icons would need more design work.
