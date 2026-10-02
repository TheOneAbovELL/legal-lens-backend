/**
 * Server-Sent Events over POST (EventSource only supports GET). Parses `data:` lines separated by
 * blank lines, tolerates chunk boundaries anywhere, ignores malformed JSON lines (reported via
 * `onMalformed`) and supports AbortController.
 */
import type { StreamEvent } from "@/types/api";
import { fetchRaw, toApiError, type RequestOptions } from "@/lib/api/client";

export interface SseOptions extends Omit<RequestOptions, "method" | "body"> {
  onMalformed?: (line: string) => void;
}

/** Split an SSE text buffer into complete event blocks; returns the remainder. */
export function splitEvents(buffer: string): { events: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  return { events: parts.filter((p) => p.trim().length > 0), rest };
}

/** Parse one event block into its JSON payload (joined `data:` lines) or null if malformed. */
export function parseEventBlock(block: string): StreamEvent | null {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");
  if (!data) return null;
  try {
    const parsed = JSON.parse(data) as unknown;
    if (parsed && typeof parsed === "object" && typeof (parsed as { type?: unknown }).type === "string") {
      return parsed as StreamEvent;
    }
    return null;
  } catch {
    return null;
  }
}

export async function* streamEvents(path: string, body: unknown, options: SseOptions = {}): AsyncGenerator<StreamEvent> {
  const response = await fetchRaw(path, {
    ...options,
    method: "POST",
    body,
    headers: { ...(options.headers ?? {}), Accept: "text/event-stream" },
    timeoutMs: options.timeoutMs ?? 180_000,
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  if (!response.body) {
    throw new Error("Streaming is not supported by this browser.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = splitEvents(buffer);
      buffer = rest;
      for (const block of events) {
        const event = parseEventBlock(block);
        if (event) yield event;
        else options.onMalformed?.(block);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      const event = parseEventBlock(buffer);
      if (event) yield event;
      else options.onMalformed?.(buffer);
    }
  } finally {
    reader.releaseLock();
  }
}
