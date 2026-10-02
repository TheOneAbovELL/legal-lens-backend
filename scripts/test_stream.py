"""Interactive SSE client for the Legal Lens chat stream.

    python scripts/test_stream.py
    python scripts/test_stream.py "Compare IPC 420 and BNS 318" --base-url http://127.0.0.1:8000
    python scripts/test_stream.py "..." --token <JWT>          # when AUTH_REQUIRED=true
    python scripts/test_stream.py "..." --raw                  # print raw JSON events

Prints each event as it arrives (tokens inline), then latency, time-to-first-token and token count.
Exit code 0 on a `done` event, 1 on `error` or a broken stream.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx


def label(event: dict) -> str:
    t = event.get("type")
    if t == "start":
        return f"[START] request_id={event.get('request_id')}"
    if t == "intent":
        return f"[INTENT] {event.get('intent')} (confidence {event.get('confidence')}) entities={event.get('entities')}"
    if t == "safety":
        return f"[SAFETY] {event.get('decision')} {event.get('categories') or ''}"
    if t == "complexity":
        return (f"[COMPLEXITY] {event.get('complexity')} -> profile {event.get('profile')}, route {event.get('route')}"
                f"\n             reasons: {', '.join(event.get('reasons', []))}")
    if t == "plan":
        lines = [f"[PLAN] method={event.get('method')} subqueries={len(event.get('subqueries', []))}"]
        lines += [f"         {s['id']}: {s['query']}  ({s['purpose']})" for s in event.get("subqueries", [])]
        return "\n".join(lines)
    if t == "retrieval":
        return f"[RETRIEVAL] {event.get('candidates')} fused candidates; raw hits per source {event.get('sources')}"
    if t == "reranking":
        return f"[RERANKING] {event.get('reranker')} -> {event.get('count')} candidates"
    if t == "evidence":
        return f"[CONTEXT] {event.get('count')} chunks selected ({event.get('context_tokens')} tokens)"
    if t == "bns_alert":
        return "[BNS] " + "; ".join(f"{m['source_act']} {m['source_section']} -> {m['target_act']} "
                                    f"{', '.join(m['target_sections']) or '-'} ({m['mapping_type']})"
                                    for m in event.get("mappings", []))
    if t == "citation":
        where = " ".join(str(x) for x in (event.get("act"), event.get("section")) if x)
        return f"[CITATION] {event.get('citation_id')} {event.get('title')} {where}".rstrip()
    if t == "validation":
        return f"[VALIDATION] valid={event.get('valid')} warnings={event.get('warnings')}"
    if t == "status":
        return f"[STATUS] {event.get('message')}"
    if t == "error":
        return f"[ERROR] {event.get('code')}: {event.get('message')}"
    if t == "complete":
        return f"[COMPLETE] refused={event.get('refused')} citations={len(event.get('citations', []))}"
    return f"[{str(t).upper()}] {event}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", nargs="?", default="What is the punishment for cheating under Section 420 IPC?")
    p.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument("--token", default=os.getenv("LEGAL_LENS_TOKEN"), help="bearer token (or LEGAL_LENS_TOKEN)")
    p.add_argument("--session-id", default=None)
    p.add_argument("--raw", action="store_true", help="print raw JSON events")
    p.add_argument("--timeout", type=float, default=180.0)
    args = p.parse_args()

    headers = {"Accept": "text/event-stream"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    body = {"query": args.query, "session_id": args.session_id}
    print(f"POST {args.base_url}/api/v1/chat/stream\nQ: {args.query}\n")

    start = time.perf_counter()
    first_token: float | None = None
    tokens = 0
    in_tokens = False
    final: dict | None = None
    try:
        with httpx.stream("POST", f"{args.base_url}/api/v1/chat/stream", json=body, headers=headers,
                          timeout=httpx.Timeout(args.timeout, connect=10)) as resp:
            if resp.status_code != 200:
                resp.read()
                print(f"[HTTP {resp.status_code}] {resp.text[:500]}")
                return 1
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if args.raw:
                    print(json.dumps(event, ensure_ascii=False))
                if event["type"] == "token":
                    tokens += 1
                    if first_token is None:
                        first_token = time.perf_counter() - start
                        if not args.raw:
                            print("[TOKENS] ", end="")
                    in_tokens = True
                    if not args.raw:
                        print(event["content"], end="", flush=True)
                    continue
                if in_tokens and not args.raw:
                    print()
                    in_tokens = False
                if not args.raw:
                    print(label(event))
                if event["type"] in ("complete", "error"):
                    final = event
    except httpx.HTTPError as exc:
        print(f"\n[STREAM FAILED] {type(exc).__name__}: {exc}")
        return 1

    total = time.perf_counter() - start
    print("\n" + "-" * 50)
    print(f"total latency:        {total:.2f} s")
    print(f"time to first token:  {first_token:.2f} s" if first_token is not None else "time to first token:  n/a")
    print(f"token events:         {tokens}")
    if final is None:
        print("RESULT: FAIL (stream ended without a done/error event)")
        return 1
    if final["type"] == "error":
        print(f"RESULT: FAIL ({final.get('code')})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
