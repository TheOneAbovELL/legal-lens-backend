import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { App } from "@/app/App";
import { AppProviders } from "@/app/providers";
import { tokenStore } from "@/lib/auth/token";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
const me = { id: "u1", username: "alice", email: null, role: "citizen", created_at: "2026-10-02T00:00:00Z" };
const result = {
  document_id: "ipc-fixture", chunk_id: "chunk-420", title: "Indian Penal Code", snippet: "Whoever cheats and thereby dishonestly induces…",
  content: "420. Cheating and dishonestly inducing delivery of property. Whoever cheats…", score: 0.03, rerank_score: 0.8, relevance_score: 0.8,
  retrieval_sources: ["dense", "metadata"], metadata: { act: "IPC", section: "420", document_type: "statute" },
  citation: { citation_id: "C1", document_id: "ipc-fixture", chunk_id: "chunk-420", title: "Indian Penal Code", act: "IPC", section: "420", source: "fixture", retrieval_sources: ["dense"], excerpt: "Whoever cheats…" },
  bns_alert: { old: "IPC 420", new: "BNS 318(4)", effective: "2024-07-01", mapping_type: "exact", verification_status: "curated_unverified", provenance: "dataset" },
};

function mount(path: string, handler: (url: string, init?: RequestInit) => Promise<Response>) {
  tokenStore.set("tok", 3600);
  window.history.pushState({}, "", path);
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/auth/me")) return json(me);
    if (url.endsWith("/health")) return json({ status: "healthy" });
    if (url.endsWith("/ready")) return json({ status: "ready", checks: {}, failed: [], components: [] });
    if (url.endsWith("/conversations")) return json({ conversations: [], total: 0 });
    return handler(url, init);
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<AppProviders client={client}><App /></AppProviders>);
}

describe("search explorer", () => {
  it("runs a search, lists results with retrieval metadata and opens a result", async () => {
    const calls: unknown[] = [];
    mount("/app/search", async (url, init) => {
      if (url.endsWith("/search")) {
        calls.push(JSON.parse(init?.body as string));
        return json({ query: "Section 420 IPC", request_id: "r", results: [result], total: 1, processing_time_ms: 42, answer: null, bns_alerts: [], warnings: [],
          retrieval_metadata: { strategy: "FAST", complexity: "SIMPLE", route: "simple", reranker: "lexical", subqueries: 1, sources: { dense: 5, sparse: 4, metadata: 1 }, candidates: 7, latency_ms: 40 } });
      }
      return json({ error: { code: "not_found", message: "no" } }, 404);
    });
    const user = userEvent.setup();
    await user.type(await screen.findByTestId("search-input"), "Section 420 IPC");
    await user.click(screen.getByTestId("search-button"));
    const results = await screen.findByTestId("search-results");
    expect(within(results).getAllByTestId("search-result")).toHaveLength(1);
    expect(screen.getByTestId("search-meta")).toHaveTextContent("dense: 5");
    expect(screen.getByTestId("search-meta")).toHaveTextContent("SIMPLE");
    expect(calls[0]).toMatchObject({ query: "Section 420 IPC", top_k: 10, filters: null });
    await user.click(within(results).getByRole("heading", { name: /IPC 420/ }));
    expect(screen.getAllByTestId("source-card")).toHaveLength(1);
    expect(screen.getByTestId("source-card")).toHaveTextContent("420. Cheating and dishonestly inducing");
    await user.click(within(results).getByRole("link", { name: /open source/i }));
    await waitFor(() => expect(window.location.pathname).toBe("/app/sources/ipc-fixture"));
  });

  it("shows an empty state and a degraded state truthfully", async () => {
    let attempt = 0;
    mount("/app/search", async (url) => {
      if (url.endsWith("/search")) {
        attempt += 1;
        if (attempt === 1) return json({ error: { code: "vector_store_error", message: "The document index is unavailable." } }, 503);
        return json({ query: "nothing", request_id: "r", results: [], total: 0, processing_time_ms: 5, answer: null, bns_alerts: [], warnings: [],
          retrieval_metadata: { strategy: "FAST", complexity: "SIMPLE", route: "simple", reranker: null, subqueries: 1, sources: {}, candidates: 0, latency_ms: 5 } });
      }
      return json({ error: { code: "not_found", message: "no" } }, 404);
    });
    const user = userEvent.setup();
    await user.type(await screen.findByTestId("search-input"), "nothing");
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Legal search is temporarily unavailable/);
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText(/No matching legal evidence was found/)).toBeInTheDocument();
  });
});
