"""Smoke test against a RUNNING backend (start it first with `uvicorn app.main:app --reload`).

    python scripts/smoke_test.py [--base-url http://127.0.0.1:8000]

Authentication: uses SMOKE_USERNAME / SMOKE_PASSWORD if set; otherwise signs up a throwaway
`smoke_<random>` account with a random password (never printed). Statuses: PASS, FAIL, BLOCKED
(an external dependency is unavailable — never reported as PASS).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from collections.abc import Callable

import httpx

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"


class Smoke:
    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(180, connect=5))
        self.results: list[tuple[str, str, str]] = []
        self.token: str | None = None
        self.ready: dict = {}
        self.question = "What does the indexed law say about punishment?"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def run(self, name: str, check: Callable[[], tuple[str, str]]) -> None:
        start = time.perf_counter()
        try:
            status, detail = check()
        except httpx.HTTPError as exc:
            status, detail = FAIL, f"{type(exc).__name__}: {exc}"
        except (AssertionError, KeyError, ValueError, json.JSONDecodeError) as exc:
            status, detail = FAIL, f"{type(exc).__name__}: {exc}"
        detail = f"{detail} ({(time.perf_counter() - start) * 1000:.0f} ms)"
        self.results.append((name, status, detail))
        print(f"[{status}] {name:<16} {detail}")

    @staticmethod
    def fail(resp: httpx.Response) -> tuple[str, str]:
        try:
            err = resp.json().get("error", {})
            msg = f"{err.get('code')}: {err.get('message')}"
        except ValueError:
            msg = resp.text[:200]
        return FAIL, f"{resp.request.method} {resp.request.url.path} -> HTTP {resp.status_code} {msg}"

    # ------------------------------------------------------------------ checks
    def root(self) -> tuple[str, str]:
        r = self.http.get("/")
        if r.status_code != 200:
            return self.fail(r)
        body = r.json()
        assert body["status"] == "ok" and body["service"] == "legal-lens-backend"
        return PASS, f"version {body['version']}"

    def health(self) -> tuple[str, str]:
        r = self.http.get("/health")
        return (PASS, "healthy") if r.status_code == 200 and r.json() == {"status": "healthy"} else self.fail(r)

    def readiness(self) -> tuple[str, str]:
        r = self.http.get("/ready")
        self.ready = r.json()
        checks = ", ".join(f"{k}={v}" for k, v in self.ready.get("checks", {}).items())
        if r.status_code == 200:
            return PASS, checks
        return BLOCKED, f"not ready: failed={self.ready.get('failed')} ({checks})"

    def auth(self) -> tuple[str, str]:
        username, password = os.getenv("SMOKE_USERNAME"), os.getenv("SMOKE_PASSWORD")
        if not (username and password):
            username, password = f"smoke_{secrets.token_hex(4)}", secrets.token_urlsafe(16) + "-1a"
            r = self.http.post("/api/v1/auth/signup", json={"username": username, "password": password})
            if r.status_code == 403:
                return BLOCKED, "registration disabled; set SMOKE_USERNAME/SMOKE_PASSWORD"
            if r.status_code != 201:
                return self.fail(r)
        r = self.http.post("/api/v1/auth/login", json={"username": username, "password": password})
        if r.status_code != 200:
            return self.fail(r)
        self.token = r.json()["access_token"]
        me = self.http.get("/api/v1/auth/me", headers=self.headers())
        if me.status_code != 200 or me.json()["username"] != username:
            return self.fail(me)
        bad = self.http.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password-1"})
        assert bad.status_code == 401, f"wrong password returned {bad.status_code}"
        return PASS, f"signup/login/me OK as {username}; bad password -> 401"

    def search(self) -> tuple[str, str]:
        r = self.http.post("/api/v1/search", json={"query": "punishment", "top_k": 3}, headers=self.headers())
        if r.status_code == 503:
            return BLOCKED, "dependency unavailable: " + r.json()["error"]["message"]
        if r.status_code != 200:
            return self.fail(r)
        body = r.json()
        if body["total"] == 0:
            return FAIL, "no results: index is empty (run scripts/ingest.py)"
        md = body["results"][0]["metadata"]
        if md.get("section"):  # ask about something that is actually indexed, so chat exercises the LLM
            self.question = f"What does {md.get('act') or md['title']} Section {md['section']} provide? Answer briefly."
        mode = (body.get("diagnostics") or {}).get("retrieval_mode", "n/a")
        return PASS, f"{body['total']} results, retrieval_mode={mode}, profile={body['retrieval_metadata']['strategy']}"

    def chat(self) -> tuple[str, str]:
        if self.ready.get("checks", {}).get("llm") != "configured":
            return BLOCKED, "LLM provider not configured"
        r = self.http.post("/api/v1/chat", json={"query": self.question},
                           headers=self.headers())
        if r.status_code in (502, 503):
            return BLOCKED, r.json()["error"]["message"]
        if r.status_code != 200:
            return self.fail(r)
        body = r.json()
        assert body["answer"], "empty answer"
        m = body["metadata"]
        return PASS, (f"route={m['route']} profile={m['retrieval_profile']} model={m['model']} "
                      f"citations={len(body['citations'])}")

    def streaming(self) -> tuple[str, str]:
        if self.ready.get("checks", {}).get("llm") != "configured":
            return BLOCKED, "LLM provider not configured"
        types: list[str] = []
        with self.http.stream("POST", "/api/v1/chat/stream", json={"query": self.question},
                              headers=self.headers()) as resp:
            if resp.status_code != 200:
                resp.read()
                return self.fail(resp)
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    types.append(json.loads(line[6:])["type"])
        if types and types[-1] == "error":
            return BLOCKED, "stream ended with an error event (see server log)"
        assert types and types[0] == "start" and types[-1] == "done", f"unexpected event sequence {types[:3]}...{types[-2:]}"
        if types.count("token") <= 1:
            return FAIL, "no LLM token stream (only a fixed message was returned)"
        return PASS, f"{len(types)} events, {types.count('token')} token events from the LLM, ended with done"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    args = p.parse_args()
    line = "=" * 40
    print(f"{line}\nLEGAL LENS BACKEND SMOKE TEST\n{line}\ntarget: {args.base_url}\n")
    smoke = Smoke(args.base_url)
    try:
        smoke.http.get("/health", timeout=5)
    except httpx.HTTPError:
        print(f"[FAIL] cannot connect to {args.base_url}. Start the server: uvicorn app.main:app --reload")
        return 1
    for name, check in (("Root", smoke.root), ("Health", smoke.health), ("Readiness", smoke.readiness),
                        ("Authentication", smoke.auth), ("Search", smoke.search), ("Chat", smoke.chat),
                        ("Streaming", smoke.streaming)):
        smoke.run(name, check)
    statuses = [s for _, s, _ in smoke.results]
    result = FAIL if FAIL in statuses else (BLOCKED if BLOCKED in statuses else PASS)
    print(f"\n{line}\nRESULT: {result}  ({statuses.count(PASS)} pass, {statuses.count(FAIL)} fail, "
          f"{statuses.count(BLOCKED)} blocked)\n{line}")
    return 0 if result == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
