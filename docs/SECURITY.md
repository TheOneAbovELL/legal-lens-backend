# Security

## Secrets

* All secrets come from the environment / `.env` (git-ignored; `.env.example` has placeholders only).
  Historical credentials in any old `.env` are treated as compromised: rotate them.
* Nothing is printed, logged or returned by diagnostics: `Settings` stores keys as `SecretStr`,
  `repr(settings)` and `/api/v1/diagnostics/config` expose only non-secret values, and the log
  formatter redacts bearer tokens, `gsk_…`/`sk-…` keys and `password=` pairs (`app/core/logging.py`).
* The frontend bundle only ever receives `VITE_*` values; CI greps the built bundle for
  secret-looking strings. Provider keys never reach the browser: every LLM, Qdrant and Neo4j call
  happens server-side.

## Authentication

* bcrypt password hashes (8–72 bytes, must mix letters with digits/symbols); signed HS256 JWT with
  issuer, subject, role claim and expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 60).
* Login returns a generic `401 authentication_failed` for unknown users and wrong passwords alike.
* Production refuses to start without a `JWT_SECRET_KEY` of at least 32 characters.
* `AUTH_REQUIRED=true` makes chat/search/statute endpoints require a token; conversations always do.

### Token storage trade-off (frontend)

The backend is a bearer-token API, so the web client keeps the JWT in `localStorage` to survive
refreshes. That is only safe because the client never renders untrusted HTML: markdown is rendered
with `react-markdown` (raw HTML skipped), excerpts and answers are inserted as text, and there is no
`dangerouslySetInnerHTML`. A future HTTP-only cookie session would remove the XSS exposure entirely
and requires a CSRF token; the client is structured so only `lib/api/client.ts` and
`lib/auth/token.ts` would change.

## Authorization / multi-tenancy

Every conversation query includes the owner's user id (`ConversationRepository`). A conversation
owned by someone else is a `404`, never a `403`, so existence is not leaked. Tests:
`tests/api/test_conversations.py::test_users_cannot_read_append_or_delete_each_others_conversations`.

## Prompt injection

Retrieved text is data. The system prompt states that evidence is untrusted quoted material and
must never override instructions; evidence always lives in the *user* message under an
`EVIDENCE:` header, never in the system message; citation IDs that appear inside evidence are not
valid IDs (`tests/unit/test_prompt_injection.py`). Answers are validated after generation: unknown
citation IDs, provisions absent from evidence, and uncited claims are rejected (one bounded
regeneration, then stripped + warned).

## Transport and abuse controls

* Request ids on every response (`X-Request-ID`), structured error envelope, no stack traces.
* Body limit (`MAX_REQUEST_BYTES`), query limit (`MAX_QUERY_CHARS`), sliding-window rate limit per
  user/IP on login, signup, chat, stream, search (429 + `Retry-After`).
* CORS allow-list (`CORS_ORIGINS`); `*` is rejected in production.
* Swagger/ReDoc and diagnostics are off in production unless explicitly enabled.
* Readiness never calls the LLM or writes; the Qdrant diagnostic is read-only.

## Checklist before a release

1. `git grep -nE "gsk_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|password\s*=\s*['\"][^'\"]+"` returns nothing.
2. `.env` is ignored (`git check-ignore .env`).
3. `APP_ENV=production` with a strong `JWT_SECRET_KEY`, explicit `CORS_ORIGINS`, `DOCS_ENABLED`
   and `DIAGNOSTICS_ENABLED` unset or `false`.
4. `npm run build` then inspect `dist/` for secrets (CI does this).
