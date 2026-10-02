# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub security advisories](https://github.com/TheOneAbovELL/legal-lens-backend/security/advisories/new).
Do not open a public issue. You will receive an acknowledgement within 72 hours.

Include: the affected component (API endpoint, frontend screen, pipeline stage), reproduction steps,
and the impact. Never include API keys, tokens or `.env` contents in a report.

## Supported versions

| Version | Supported |
|---|---|
| `main` / latest release | yes |
| older tags | no |

## How the project handles secrets and data

See [docs/SECURITY.md](docs/SECURITY.md): secrets live only in the environment, are never logged or
returned by diagnostics, and the frontend bundle is scanned in CI. Conversations are scoped to the
owning user; retrieved legal text is treated as untrusted data by the generation prompt.
