"""Deterministic backend for browser (Playwright) tests and offline frontend development.

Runs the REAL application (same routers, services, graph, database layer) with the test doubles
from ``tests/``: in-memory Qdrant holding the fixture corpus, a temporary SQLite database, the
hashing embedder and a scripted LLM. Nothing here touches Qdrant Cloud, Groq or the developer's
``.env``. This is test tooling: the production application never imports ``tests``.

    python scripts/e2e_server.py --port 8011
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.conftest import ingest_corpus, make_container, make_settings  # noqa: E402
from tests.fakes import ScriptedLLM  # noqa: E402

# No section numbers: the answer validator rejects provisions absent from the evidence, and this
# reply must stay valid for every fixture question (simple, moderate and complex).
E2E_ANSWER = (
    "Based on the indexed sources, the cited provision sets out the rule described in the evidence, "
    "including who it applies to and the consequence it prescribes [C1]. Where several provisions are "
    "compared, the later code restates the earlier rule with the changes noted in the evidence [C1]. "
    "This is legal information, not legal advice."
)


def build_app(port: int):  # type: ignore[no-untyped-def]
    from app.container import Container
    from app.core.config import Settings
    from app.main import create_app

    tmp = Path(tempfile.mkdtemp(prefix="legal-lens-e2e-"))
    settings = make_settings(
        tmp,
        app_env="test",
        log_level="INFO",
        log_json=False,
        rate_limit_enabled=False,
        diagnostics_enabled=True,
        docs_enabled=True,
        public_base_url=f"http://127.0.0.1:{port}",
        cors_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost:5174"],
    )
    holder: dict[str, Container] = {}

    def factory(s: Settings) -> Container:
        holder["c"] = make_container(s, ScriptedLLM([E2E_ANSWER]))
        return holder["c"]

    app = create_app(settings, container_factory=factory)
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):  # type: ignore[no-untyped-def]
        async with inner(application):
            await ingest_corpus(holder["c"])
            print(f"[e2e] fixture corpus ingested; database at {tmp}", flush=True)
            yield

    app.router.lifespan_context = lifespan
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(build_app(args.port), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
