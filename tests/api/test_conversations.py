"""Conversation persistence through the real app: ownership boundaries, chat persistence, streaming
reconciliation, failure semantics and stateless anonymous use."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.container import Container
from app.core.config import Settings
from app.core.exceptions import LLMProviderError
from app.main import create_app
from tests.conftest import ingest_corpus, make_container, make_settings
from tests.fakes import ScriptedLLM

pytestmark = pytest.mark.asyncio


async def _signup(client: httpx.AsyncClient, name: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/signup", json={"username": name, "password": "Secret-pass-1"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_chat_without_token_is_stateless(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/chat", json={"query": "What is the punishment under Section 420 IPC?",
                                                   "conversation_id": "client-side-id"})
    body = resp.json()
    assert resp.status_code == 200 and body["persisted"] is False and body["message_id"] is None
    assert body["conversation_id"] == "client-side-id"  # echoed for MEM-0 only
    assert body["status"] == "complete" and body["analysis"]["complexity"] == "SIMPLE"


async def test_chat_creates_conversation_and_persists_both_messages(client: httpx.AsyncClient) -> None:
    auth = await _signup(client, "alice")
    resp = await client.post("/api/v1/chat", json={"query": "What is the punishment under Section 420 IPC?"},
                             headers=auth)
    body = resp.json()
    assert resp.status_code == 200 and body["persisted"] is True and body["message_id"] and body["conversation_id"]

    listing = (await client.get("/api/v1/conversations", headers=auth)).json()
    assert listing["total"] == 1 and listing["conversations"][0]["title"].startswith("What is the punishment")

    detail = (await client.get(f"/api/v1/conversations/{body['conversation_id']}", headers=auth)).json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    assistant = detail["messages"][1]
    assert assistant["id"] == body["message_id"] and assistant["status"] == "complete"
    assert assistant["content"] == body["answer"] and assistant["complexity"] == "SIMPLE"
    assert [c["citation_id"] for c in assistant["citations"]] == [c["citation_id"] for c in body["citations"]]
    assert assistant["citations"][0]["excerpt"]

    # Continue the same conversation: the follow-up is appended, not duplicated.
    again = await client.post("/api/v1/chat", json={"query": "What is its punishment?",
                                                    "conversation_id": body["conversation_id"]}, headers=auth)
    assert again.status_code == 200 and again.json()["conversation_id"] == body["conversation_id"]
    messages = (await client.get(f"/api/v1/conversations/{body['conversation_id']}/messages", headers=auth)).json()
    assert len(messages) == 4


async def test_users_cannot_read_append_or_delete_each_others_conversations(client: httpx.AsyncClient) -> None:
    alice, bob = await _signup(client, "alice"), await _signup(client, "bob")
    created = (await client.post("/api/v1/conversations", json={"title": "Alice's notes"}, headers=alice)).json()
    cid = created["id"]

    assert (await client.get(f"/api/v1/conversations/{cid}", headers=bob)).status_code == 404
    assert (await client.get(f"/api/v1/conversations/{cid}/messages", headers=bob)).status_code == 404
    assert (await client.patch(f"/api/v1/conversations/{cid}", json={"title": "x"}, headers=bob)).status_code == 404
    assert (await client.delete(f"/api/v1/conversations/{cid}", headers=bob)).status_code == 404
    appended = await client.post("/api/v1/chat", json={"query": "Explain Section 420 IPC", "conversation_id": cid},
                                 headers=bob)
    assert appended.status_code == 404 and appended.json()["error"]["code"] == "not_found"
    # Bob's listing is empty; Alice still owns an intact conversation with no messages.
    assert (await client.get("/api/v1/conversations", headers=bob)).json()["total"] == 0
    assert (await client.get(f"/api/v1/conversations/{cid}", headers=alice)).json()["messages"] == []


async def test_rename_delete_and_unauthenticated_access(client: httpx.AsyncClient) -> None:
    alice = await _signup(client, "alice")
    cid = (await client.post("/api/v1/conversations", json={}, headers=alice)).json()["id"]
    renamed = await client.patch(f"/api/v1/conversations/{cid}", json={"title": "  IPC 420  "}, headers=alice)
    assert renamed.status_code == 200 and renamed.json()["title"] == "IPC 420"
    assert (await client.get("/api/v1/conversations")).status_code == 401
    assert (await client.delete(f"/api/v1/conversations/{cid}", headers=alice)).status_code == 204
    assert (await client.get(f"/api/v1/conversations/{cid}", headers=alice)).status_code == 404


async def test_stream_complete_event_carries_persisted_message_id(client: httpx.AsyncClient) -> None:
    alice = await _signup(client, "alice")
    async with client.stream("POST", "/api/v1/chat/stream", json={"query": "Explain Section 420 IPC"},
                             headers=alice) as resp:
        events = [json.loads(line[6:]) async for line in resp.aiter_lines() if line.startswith("data: ")]
    start, complete = events[0], events[-1]
    assert start["type"] == "start" and start["persisted"] is True and start["conversation_id"]
    assert complete["type"] == "complete" and complete["message_id"] and complete["status"] == "complete"
    # The complete event is the ChatResponse contract, byte-for-byte the same keys as the JSON endpoint.
    json_body = (await client.post("/api/v1/chat", json={"query": "Explain Section 420 IPC"}, headers=alice)).json()
    assert set(complete) - {"type"} == set(json_body)
    assert complete["bns_alerts"][0]["old"] == "IPC 420" and complete["analysis"]["complexity"] == "SIMPLE"
    assert any(e["type"] == "analysis" and e["complexity"] == "SIMPLE" for e in events)
    detail = (await client.get(f"/api/v1/conversations/{start['conversation_id']}", headers=alice)).json()
    assert detail["messages"][1]["id"] == complete["message_id"]
    assert detail["messages"][1]["content"] == complete["answer"]


async def test_user_message_survives_llm_failure(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    failing = ScriptedLLM(failures=[LLMProviderError("boom", status_code=500), LLMProviderError("boom", status_code=500)])
    holder: dict[str, Container] = {}

    def factory(s: Settings) -> Container:
        holder["c"] = make_container(s, failing)
        return holder["c"]

    app = create_app(settings, container_factory=factory)
    async with LifespanManager(app):
        await ingest_corpus(holder["c"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            alice = await _signup(client, "alice")
            resp = await client.post("/api/v1/chat", json={"query": "Explain Section 420 IPC"}, headers=alice)
            assert resp.status_code == 502 and resp.json()["error"]["code"] == "llm_provider_error"
            listing = (await client.get("/api/v1/conversations", headers=alice)).json()
            cid = listing["conversations"][0]["id"]
            messages = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=alice)).json()
            assert [m["role"] for m in messages] == ["user", "assistant"]
            assert messages[1]["status"] == "failed" and messages[1]["citations"] == []
