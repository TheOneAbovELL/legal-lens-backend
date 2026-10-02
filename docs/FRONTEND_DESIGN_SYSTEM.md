# Legal Lens design system

The web client is a **legal research workstation**: an AI conversation, a research interface and an
evidence/citation interface in one calm, editorial surface. The design does most of its work with
typography, whitespace and alignment; borders, cards and colour are used sparingly and always to
mean something. Everything below is implemented in `frontend/src/styles/tokens.css`,
`frontend/src/styles/global.css` and `frontend/src/components/`.

## Principles

1. **Evidence first.** Citations are chips you can read (`C1 · IPC §420`), hover to preview and open
   without leaving the answer. Evidence looks like a document extract, not an API payload.
2. **Editorial, not dashboard.** One reading column (760 px) for the thread; serif for titles, questions,
   statute references and passages; sans for UI. No card soup: hierarchy comes from type scale,
   section labels and hairlines.
3. **One accent.** A muted blue marks links, the active route, citations and the primary action.
   Status colours (ok / warn / danger) appear only as status words and inline notices.
4. **Honest state.** Progress is derived from backend events; empty, degraded and failed states are
   typographic and specific; nothing fake is shown.
5. **Calm motion.** Short rises and slides for overlays and new turns; nothing bounces; reduced motion
   disables all of it.

## Colour tokens

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#f4f2ed` paper | `#16181c` | workspace background |
| `--surface` | `#fbfaf7` | `#1c1f24` | reading surface, inputs, panels |
| `--surface-2` | `#f0ede6` | `#141619` | top bar, sidebar |
| `--surface-3` | `#e9e5dc` | `#262a31` | hover / pressed / inset |
| `--ink`, `--ink-2`, `--ink-3`, `--ink-4` | `#1a1c21` → `#9a9fa8` | `#e9e7e2` → `#5d626b` | text hierarchy: body, secondary, metadata, placeholder |
| `--line`, `--line-2` | `#e2ded5`, `#cfcabf` | `#2b2f37`, `#3a3f49` | hairlines, input borders |
| `--accent` (+ `-hover`, `-soft`, `-line`, `-ink`) | `#2c5a8c` | `#8fb4de` | links, active nav, citations, primary |
| `--evidence-bg/line/ink/mark` | warm `#f6f1e4` family | `#22201a` family | selected evidence, highlighted passages |
| `--ok`, `--warn`, `--danger` (+ `-soft`) | muted | muted | status words, notices |
| `--overlay` | 42 % ink | 55 % black | scrims |

Dark mode is a separate palette (never an inversion): backgrounds are near-black greys with warm
text, the accent is lightened for contrast, evidence keeps its warm tint. `data-theme="light|dark"`
overrides the system preference; the choice is applied before first paint from `localStorage`.

## Typography

| Role | Face | Size / weight |
|---|---|---|
| UI | Inter (system fallback) | 13–14.5 px / 400–600 |
| Product name, page title, user question, answer headings, statute references, passages | Source Serif 4 (Georgia fallback) | 17–32 px / 400–600 |
| Answer body | Inter | 16.5 px, line-height 1.7 |
| Metadata, section labels | Inter | 12 px; labels uppercase, tracked 0.08 em |
| Diagnostics | JetBrains Mono / system mono | 13 px |

Scale tokens: `--text-xs 12`, `--text-sm 13`, `--text-md 14.5`, `--text-lg 16.5`, `--text-xl 20`,
`--text-2xl 26`, `--text-3xl 32`. Fonts load from Google Fonts with `display=swap`; the fallbacks
keep every screen usable offline.

## Spacing, radii, elevation, motion

* 4 px scale: `--s-1` 4 … `--s-16` 64. Thread gap 32, section padding 20–32, control padding 8–12.
* Radii: `--r-sm` 4 (chips, badges, menu items), `--r-md` 8 (buttons, inputs), `--r-lg` 12
  (composer, dialog, sheet), pill for avatars only.
* Elevation: `--shadow-1` for raised controls, `--shadow-2` for menus/dialogs, `--shadow-sheet` for the
  bottom sheet. Nothing else casts a shadow.
* Motion: `--t-fast` 120 ms (hover), `--t-base` 200 ms (rise/fade), `--t-slow` 320 ms (drawers,
  sheet, sidebar collapse); easing `cubic-bezier(.2,.7,.2,1)`; disabled by `prefers-reduced-motion`.

## Layout

```
┌ top bar (52) ───────────────────────────────────────────────────────────────┐
│ ☰ ▣ Legal Lens   Research  Search  [Diagnostics]              + user ▾     │
├ sidebar (268) ─┬ workspace ───────────────────────────┬ evidence (392) ─────┤
│ + New research │ reading column 760 px, centred       │ Evidence · 2 sources │
│ search         │ YOU / LEGAL LENS turns               │ C1 BNS §318          │
│ Today …        │ Sources  C1 BNS §318  C7 IPC §420    │ passage … marks      │
│ Settings/About │ sticky composer                      │ C7 IPC §420          │
└────────────────┴──────────────────────────────────────┴──────────────────────┘
```

| Width | Sidebar | Evidence |
|---|---|---|
| ≥ 1281 px | 268 px, collapsible (state remembered) | 392 px pane |
| 1101–1280 px | 248 px | 340 px pane |
| 821–1100 px | 248 px | right drawer (420 px) |
| ≤ 820 px | drawer from the ☰ button | bottom sheet with grip, safe-area padding |
| ≤ 480 px | drawer | sheet; composer hints hidden; labels collapse to icons |

## Components (`src/components`)

| Primitive | Notes |
|---|---|
| `Button` (`primary`, `accent`, `secondary`, `ghost`, `danger`; `sm/md/lg`; `icon`, `loading`) and `IconButton` (label = accessible name + tooltip) | one height per size; icons 16 px |
| `Input`, `Textarea`, `Select` (`Field.tsx`) | label always present (visually hidden when needed), error/hint wired via `aria-describedby` |
| `Badge` (uppercase status pill), `ComplexityBadge`, `MappingBadge`, `StatusText` (healthy / degraded / unavailable word with a dot) | colour only for semantics |
| `CitationChip` + `SourcePreview` (`Chip.tsx`) | `[C1] IPC §420`; hover/focus preview; `aria-pressed` when selected |
| `Tooltip` | focus and hover, Escape closes, `role="tooltip"` |
| `Dialog`, `Drawer` (left/right), `Sheet` (bottom) (`Overlay.tsx`) | scrim, focus trap, Escape, focus return, body scroll lock |
| `Notice` (neutral / info / warn / danger), `Skeleton` (`Feedback.tsx`) | the only inline "boxes" in the product |
| `Toast` (ink on paper, bottom-right), `Menu` (arrow keys, Escape, click-outside), `Avatar`, `Spinner`, `kbd` | |
| `Brand` / `BrandMark` (`components/layout`) | abstract lens-over-text mark; wordmark in serif |

Feature components: `ConversationSidebar` (groups by Today / Yesterday / Previous 7 days / Older,
client-side search, rename/delete), `UserMessage`, `AssistantMessage` (answer, mapping, sources row,
trust line, actions), `ResearchProgress` (phase line, four steps, research aspects), `ChatComposer`
(sticky, auto-grow, Enter/Shift+Enter, stop, retrieval depth), `AnswerMarkdown`, `EvidenceCard`,
`EvidencePane`/`EvidenceList`/`EvidenceTools` (next/previous), `SourcePage` (document reader),
`MappingComparison`, `SearchResult`, settings sections, diagnostics blocks.

Icons: `lucide-react` only (16–18 px, 1.5 px stroke). No emoji, no Unicode glyph icons.

## Accessibility rules

* Every interactive element is a real `button`, `a`, `input` or `select` with a visible focus ring
  (`:focus-visible`, 2 px accent).
* Overlays: `role="dialog"`, `aria-modal`, labelled by their title, Escape closes, focus moves in and
  returns, Tab is trapped.
* Citation chips are buttons with `aria-label="Citation C1: IPC §420"` and `aria-pressed` when
  selected; evidence cards are focusable and activate with Enter/Space; `aria-current` marks the
  selected passage.
* Live regions: progress line (`role="status"`, polite), toasts, net-status line.
* Contrast: body text ≥ 11:1 (light) / ≥ 12:1 (dark); metadata ≥ 4.6:1; accent on surface ≥ 5:1.
* Status is never colour-only: words (healthy / degraded), icons and text accompany every tone.

## Interaction principles

* Sending a question appends the user turn immediately; the assistant turn shows the progress line
  until the first token, then streams; the `complete` event reconciles the final text and citations
  without creating a second message.
* Clicking a citation never navigates: it selects the passage in the pane (desktop), the right drawer
  (tablet) or the bottom sheet (phone). The source reader is a deliberate second step ("Open source")
  and always offers "Back" to the same conversation.
* Degraded backend: one quiet line under the top bar ("Connection interrupted — reconnecting…" /
  "Limited mode: …") that disappears by itself.
* Nothing the backend cannot do is shown: no upload, deep-research, saved-research or feedback controls.
