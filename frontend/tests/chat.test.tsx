import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { App } from "@/app/App";
import { AppProviders } from "@/app/providers";
import { tokenStore } from "@/lib/auth/token";
import type { Citation } from "@/types/api";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
function sse(events: unknown[]): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(text, { status: 200, headers: { "content-type": "text/event-stream" } });
}

const me = { id: "u1", username: "alice", email: null, role: "citizen", created_at: "2026-10-02T00:00:00Z" };
const citation: Citation = { citation_id: "C1", document_id: "ipc-fixture", chunk_id: "chunk-1", title: "Indian Penal Code", act: "IPC",
  section: "420", source: "fixture", retrieval_sources: ["dense", "metadata"], score: 0.91, excerpt: "Whoever cheats and thereby dishonestly induces…" };
const analysis = { intent: "statute_lookup", complexity: "SIMPLE", confidence: 0.9, route: "simple", retrieval_profile: "FAST", safety_decision: "allow",
  jurisdiction: "IN", outside_jurisdiction: false, decomposition_needed: false, comparison_required: false, provisions: ["Section 420 IPC"], follow_up: false };

function backend(streamEvents: unknown[]) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/auth/me")) return json(me);
    if (url.endsWith("/health")) return json({ status: "healthy" });
    if (url.endsWith("/ready")) return json({ status: "ready", checks: {}, failed: [], components: [] });
    if (url.endsWith("/conversations") && (!init?.method || init.method === "GET")) return json({ conversations: [], total: 0 });
    if (url.endsWith("/chat/stream")) return sse(streamEvents);
    if (url.includes("/conversations/conv-1")) {
      return json({ id: "conv-1", title: "What is 420?", created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z", archived_at: null, messages: [] });
    }
    return json({ error: { code: "not_found", message: "no" } }, 404);
  });
}

function mount(path = "/app") {
  tokenStore.set("tok", 3600);
  window.history.pushState({}, "", path);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<AppProviders client={client}><App /></AppProviders>);
}

describe("chat workspace", () => {
  it("submits a question, renders streamed tokens, reconciles the final answer and opens the citation", async () => {
    const complete = { type: "complete", message_id: "m1", answer: "Cheating is punishable with imprisonment [C1].", source: "qdrant", request_id: "r1",
      conversation_id: "conv-1", persisted: true, status: "complete", refused: false, citations: [citation], bns_alerts: [
        { old: "IPC 420", new: "BNS 318(4)", effective: "2024-07-01", mapping_type: "exact", subject: "Cheating", notes: null, verification_status: "curated_unverified", provenance: "dataset" }],
      warnings: [], disclaimer: "Legal information, not advice.", metadata: { request_id: "r1" }, analysis };
    const fetchMock = backend([
      { type: "start", request_id: "r1", conversation_id: "conv-1", persisted: true, user_message_id: "um1" },
      { type: "complexity", complexity: "SIMPLE", confidence: 0.9, reasons: [], profile: "FAST", route: "simple" },
      { type: "analysis", ...analysis },
      { type: "retrieval", candidates: 5, sources: { dense: 3, sparse: 2 } },
      { type: "evidence", count: 1, context_tokens: 120, citations: [citation] },
      { type: "token", content: "Cheating is punishable " },
      { type: "token", content: "with imprisonment [C1]." },
      { type: "citation", ...citation },
      complete,
    ]);
    vi.stubGlobal("fetch", fetchMock);
    mount();
    const user = userEvent.setup();
    const input = await screen.findByTestId("composer-input");
    await user.type(input, "What is the punishment under Section 420 IPC?");
    await user.click(screen.getByTestId("send-button"));

    expect(await screen.findByTestId("user-message")).toHaveTextContent("What is the punishment under Section 420 IPC?");
    const assistant = await screen.findByTestId("assistant-message");
    await waitFor(() => expect(assistant).toHaveAttribute("data-status", "complete"));
    expect(assistant).toHaveTextContent("Cheating is punishable with imprisonment");
    expect(screen.getAllByTestId("assistant-message")).toHaveLength(1); // complete did not duplicate
    expect(within(assistant).getByText(/Based on 1 retrieved legal source/)).toBeInTheDocument();
    expect(within(assistant).getByTestId("mapping-card")).toHaveTextContent("IPC 420");
    await waitFor(() => expect(window.location.pathname).toBe("/app/chat/conv-1"));

    // Evidence panel shows the cited source; clicking the chip selects it.
    const panel = screen.getByRole("complementary", { name: /sources and evidence/i });
    expect(within(panel).getAllByTestId("source-card")).toHaveLength(1);
    await user.click(within(assistant).getAllByRole("button", { name: /citation C1/i })[0]!);
    expect(within(panel).getByTestId("source-card")).toHaveAttribute("aria-current", "true");
    expect(within(panel).getByTestId("source-card")).toHaveTextContent("Whoever cheats");

    const streamCall = fetchMock.mock.calls.find(([u]) => (u as string).endsWith("/chat/stream"));
    const body = JSON.parse((streamCall?.[1] as RequestInit).body as string);
    expect(body).toMatchObject({ query: "What is the punishment under Section 420 IPC?", conversation_id: null });
  });

  it("renders a backend error event as a retryable failure", async () => {
    vi.stubGlobal("fetch", backend([
      { type: "start", request_id: "r2", conversation_id: null, persisted: false, user_message_id: null },
      { type: "error", code: "llm_provider_error", message: "The language model provider failed to respond." },
    ]));
    mount();
    const user = userEvent.setup();
    await user.type(await screen.findByTestId("composer-input"), "Explain Section 420 IPC");
    await user.keyboard("{Enter}");
    const assistant = await screen.findByTestId("assistant-message");
    await waitFor(() => expect(assistant).toHaveAttribute("data-status", "failed"));
    expect(within(assistant).getByRole("alert")).toHaveTextContent("language model provider failed");
    expect(within(assistant).getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("shows the insufficient-evidence state instead of inventing sources", async () => {
    vi.stubGlobal("fetch", backend([
      { type: "start", request_id: "r3", conversation_id: null, persisted: false, user_message_id: null },
      { type: "token", content: "I could not find sufficient support for this question in the indexed legal sources." },
      { type: "complete", message_id: null, answer: "I could not find sufficient support for this question in the indexed legal sources.", source: "none", request_id: "r3",
        conversation_id: null, persisted: false, status: "insufficient_evidence", refused: false, citations: [], bns_alerts: [], warnings: [], disclaimer: null,
        metadata: { request_id: "r3" }, analysis },
    ]));
    mount();
    const user = userEvent.setup();
    await user.type(await screen.findByTestId("composer-input"), "Something not in the corpus");
    await user.keyboard("{Enter}");
    const assistant = await screen.findByTestId("assistant-message");
    await waitFor(() => expect(assistant).toHaveAttribute("data-status", "insufficient_evidence"));
    expect(within(assistant).getByText(/not enough evidence/i)).toBeInTheDocument();
    expect(screen.queryAllByTestId("source-card")).toHaveLength(0);
  });

  it("shows the backend-unavailable banner with a retry when health fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/auth/me")) return json(me);
      if (url.endsWith("/conversations")) return json({ conversations: [], total: 0 });
      throw new TypeError("Failed to fetch");
    }));
    mount();
    expect(await screen.findByText(/connection interrupted/i, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry now/i })).toBeInTheDocument();
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
  });
});
