"""Optional single-page frontend serving (FRONTEND_DIST_PATH)."""

from __future__ import annotations

from pathlib import Path

import httpx
from asgi_lifespan import LifespanManager

from app.container import Container
from app.core.config import Settings
from app.main import create_app
from tests.conftest import make_container, make_settings


async def _client(settings: Settings):  # type: ignore[no-untyped-def]
    def factory(s: Settings) -> Container:
        return make_container(s)

    app = create_app(settings, container_factory=factory)
    return app, LifespanManager(app)


async def test_spa_fallback_and_api_precedence(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Legal Lens</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    app, manager = await _client(make_settings(tmp_path, frontend_dist_path=dist))
    async with manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/health")).json() == {"status": "healthy"}  # API keeps precedence
            assert (await c.get("/api/v1/nope")).status_code == 404
            assert (await c.get("/api/v1/nope")).json()["error"]["code"] == "not_found"
            for path in ("/app", "/app/chat/abc", "/login"):
                resp = await c.get(path)
                assert resp.status_code == 200 and "Legal Lens" in resp.text, path
            assert (await c.get("/assets/app.js")).text == "console.log(1)"
            assert (await c.get("/favicon.svg")).text == "<svg/>"
            assert "Legal Lens" in (await c.get("/..%2F..%2Fetc%2Fpasswd")).text  # traversal -> index, never a file


async def test_missing_dist_serves_api_only(tmp_path: Path) -> None:
    app, manager = await _client(make_settings(tmp_path, frontend_dist_path=tmp_path / "missing"))
    async with manager:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/app")).status_code == 404
