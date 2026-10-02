## Summary

<!-- What changed and why. Link the issue if there is one. -->

## Checklist

- [ ] `pytest -q` passes (backend) and `cd frontend && npm test` passes (frontend)
- [ ] `ruff check app scripts tests` and `npm run lint && npm run typecheck` are clean
- [ ] If a schema or router changed: `python scripts/export_openapi.py` and the contract test pass
- [ ] If the UI changed: `npm run test:e2e` passes; screenshots refreshed if the visual spec changed
- [ ] No secrets, API keys or `.env` values in code, docs, tests or the frontend bundle
- [ ] Docs updated (`docs/`, `README.md`) where behaviour changed

## Reviewer notes

<!-- Anything a reviewer should know: trade-offs, follow-ups, blocked items. -->
