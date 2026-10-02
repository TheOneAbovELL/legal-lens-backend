import { describe, expect, it } from "vitest";
import { chatReducer, initialChatState, phaseLabel, type ChatState } from "@/features/chat/chatReducer";
import type { ChatResponse, Citation, StreamEvent } from "@/types/api";

const citation: Citation = { citation_id: "C1", document_id: "ipc", title: "IPC", act: "IPC", section: "420", source: "fixture", retrieval_sources: ["dense"], excerpt: "Whoever cheats…" };

function complete(overrides: Partial<ChatResponse> = {}): StreamEvent {
  return {
    type: "complete", message_id: "m-9", answer: "Cheating is punished [C1].", source: "qdrant", request_id: "r1",
    conversation_id: "conv-1", persisted: true, status: "complete", refused: false, citations: [citation], bns_alerts: [],
    warnings: [], disclaimer: "Info only.", metadata: { request_id: "r1" },
    analysis: { intent: "statute_lookup", complexity: "SIMPLE", confidence: 0.9, route: "simple", retrieval_profile: "FAST",
      safety_decision: "allow", jurisdiction: "IN", outside_jurisdiction: false, decomposition_needed: false,
      comparison_required: false, provisions: ["Section 420 IPC"], follow_up: false },
    ...overrides,
  };
}

function send(state: ChatState = initialChatState()): ChatState {
  return chatReducer(state, { type: "send", query: "What is 420?", userId: "u1", assistantId: "a1", now: "2026-10-02T10:00:00Z" });
}

describe("chatReducer", () => {
  it("appends an optimistic user message and a streaming placeholder", () => {
    const s = send();
    expect(s.messages.map((m) => [m.role, m.status])).toEqual([["user", "complete"], ["assistant", "streaming"]]);
    expect(s.streamingId).toBe("a1");
    expect(s.phase).toBe("analyzing");
  });

  it("accumulates tokens, tracks phases from backend events and reconciles on complete without duplicates", () => {
    let s = send();
    const feed = (event: StreamEvent) => { s = chatReducer(s, { type: "event", event, assistantId: "a1" }); };
    feed({ type: "start", request_id: "r1", conversation_id: "conv-1", persisted: true, user_message_id: "um-1" });
    expect(s.conversationId).toBe("conv-1");
    expect(s.messages[0]?.serverId).toBe("um-1");
    feed({ type: "complexity", complexity: "SIMPLE", confidence: 0.9, reasons: [], profile: "FAST", route: "simple" });
    feed({ type: "plan", method: null, subqueries: [{ id: "q0", query: "x", purpose: "p" }] });
    expect(phaseLabel(s.phase, s.stage)).toBe("Searching legal sources");
    feed({ type: "retrieval", candidates: 12, sources: { dense: 8, sparse: 7 } });
    expect(phaseLabel(s.phase, s.stage)).toBe("Reviewing 12 passages");
    feed({ type: "evidence", count: 3, context_tokens: 500, citations: [citation] });
    expect(phaseLabel(s.phase, s.stage)).toBe("Preparing answer from 3 sources");
    feed({ type: "token", content: "Cheating " });
    feed({ type: "token", content: "is punished [C1]." });
    expect(s.messages[1]?.content).toBe("Cheating is punished [C1].");
    expect(s.phase).toBe("streaming");
    feed({ type: "citation", ...citation });
    feed({ type: "citation", ...citation }); // duplicate event
    expect(s.messages[1]?.citations).toHaveLength(1);
    feed(complete());
    expect(s.messages).toHaveLength(2); // no duplicate assistant message
    const assistant = s.messages[1]!;
    expect(assistant.serverId).toBe("m-9");
    expect(assistant.status).toBe("complete");
    expect(assistant.analysis?.complexity).toBe("SIMPLE");
    expect(s.streamingId).toBeNull();
    expect(s.phase).toBe("idle");
  });

  it("restarts the draft when a regeneration attempt starts", () => {
    let s = send();
    const feed = (event: StreamEvent) => { s = chatReducer(s, { type: "event", event, assistantId: "a1" }); };
    feed({ type: "token", content: "Bad draft [C9]", attempt: 0 });
    feed({ type: "token", content: "Good ", attempt: 1 });
    feed({ type: "token", content: "draft [C1]", attempt: 1 });
    expect(s.messages[1]?.content).toBe("Good draft [C1]");
  });

  it("marks failures, cancellations and backend error events without losing streamed text", () => {
    let s = send();
    s = chatReducer(s, { type: "event", event: { type: "token", content: "partial" }, assistantId: "a1" });
    const cancelled = chatReducer(s, { type: "cancelled", assistantId: "a1" });
    expect(cancelled.messages[1]).toMatchObject({ status: "incomplete", content: "partial" });
    expect(cancelled.streamingId).toBeNull();

    const errored = chatReducer(s, { type: "event", event: { type: "error", code: "llm_provider_error", message: "LLM down" }, assistantId: "a1" });
    expect(errored.messages[1]).toMatchObject({ status: "failed", error: { code: "llm_provider_error" } });

    const failed = chatReducer(s, { type: "failed", assistantId: "a1", error: { title: "t", message: "m", retryable: true, code: "network_error" } });
    expect(failed.messages[1]?.status).toBe("failed");
  });

  it("loads server history with stored citations and statuses", () => {
    const s = chatReducer(initialChatState(), {
      type: "load", conversationId: "conv-1", messages: [
        { id: "1", conversation_id: "conv-1", role: "user", content: "Q", status: "complete", request_id: null, complexity: null, intent: null, created_at: "2026-10-02T10:00:00Z", citations: [] },
        { id: "2", conversation_id: "conv-1", role: "assistant", content: "A [C1]", status: "complete", request_id: "r", complexity: "SIMPLE", intent: "statute_lookup", created_at: "2026-10-02T10:00:01Z",
          citations: [{ citation_id: "C1", document_id: "ipc", chunk_id: "c", source: "fixture", title: "IPC", act: "IPC", section: "420", page: null, excerpt: "Whoever…", score: 0.5 }] },
      ],
    });
    expect(s.persisted).toBe(true);
    expect(s.messages[1]?.citations[0]).toMatchObject({ citation_id: "C1", section: "420", excerpt: "Whoever…" });
  });

  it("reports insufficient evidence and refusals as distinct statuses", () => {
    let s = send();
    s = chatReducer(s, { type: "event", event: complete({ status: "insufficient_evidence", citations: [], answer: "I could not find…" }), assistantId: "a1" });
    expect(s.messages[1]?.status).toBe("insufficient_evidence");
    s = send(s);
    const id = s.streamingId!;
    s = chatReducer(s, { type: "event", event: complete({ status: "refused", refused: true, citations: [], answer: "Outside scope." }), assistantId: id });
    expect(s.messages[3]?.status).toBe("refused");
  });
});
