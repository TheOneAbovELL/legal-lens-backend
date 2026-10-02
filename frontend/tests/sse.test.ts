import { describe, expect, it, vi } from "vitest";
import { parseEventBlock, splitEvents, streamEvents } from "@/lib/streaming/sse";

function encodeStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("SSE parsing", () => {
  it("splits complete blocks and keeps the remainder", () => {
    const { events, rest } = splitEvents('data: {"type":"start"}\n\ndata: {"type":"tok');
    expect(events).toEqual(['data: {"type":"start"}']);
    expect(rest).toBe('data: {"type":"tok');
  });

  it("parses data lines, tolerates CRLF and rejects malformed JSON", () => {
    expect(parseEventBlock('data: {"type": "token", "content": "Hi"}')).toEqual({ type: "token", content: "Hi" });
    expect(parseEventBlock(': comment\r\ndata: {"type":"start"}')).toEqual({ type: "start" });
    expect(parseEventBlock("data: {not json")).toBeNull();
    expect(parseEventBlock('data: {"no": "type"}')).toBeNull();
  });

  it("yields events across arbitrary chunk boundaries and never duplicates tokens", async () => {
    const body = encodeStream([
      'data: {"type":"start","request_id":"r1"}\n\nda',
      'ta: {"type":"token","content":"Sec"}\n\ndata: {"type":"token","con',
      'tent":"tion"}\n\ndata: garbage\n\ndata: {"type":"complete","status":"complete"}\n\n',
    ]);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } })));
    const malformed: string[] = [];
    const seen: string[] = [];
    for await (const event of streamEvents("/api/v1/chat/stream", { query: "x" }, { onMalformed: (l) => malformed.push(l) })) {
      seen.push(event.type === "token" ? `token:${event.content}` : event.type);
    }
    expect(seen).toEqual(["start", "token:Sec", "token:tion", "complete"]);
    expect(malformed).toEqual(["data: garbage"]);
  });

  it("turns an error response into ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { code: "rate_limited", message: "slow down" } }), { status: 429 })));
    const iterator = streamEvents("/api/v1/chat/stream", { query: "x" });
    await expect(iterator.next()).rejects.toMatchObject({ name: "ApiError", code: "rate_limited", status: 429 });
  });
});
