import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, request, setUnauthorizedHandler } from "@/lib/api/client";
import { tokenStore } from "@/lib/auth/token";

afterEach(() => setUnauthorizedHandler(null));

describe("api client", () => {
  it("sends bearer token, request id and JSON; parses the envelope on errors", async () => {
    tokenStore.set("tok-123", 3600);
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const headers = init.headers as Record<string, string>;
      expect(headers.Authorization).toBe("Bearer tok-123");
      expect(headers["X-Request-ID"]).toMatch(/^[0-9a-f]{20,}$/);
      expect(headers["Content-Type"]).toBe("application/json");
      return new Response(JSON.stringify({ error: { code: "not_found", message: "Conversation not found.", request_id: "rid" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(request("/api/v1/conversations/x", { body: { a: 1 } })).rejects.toMatchObject({ code: "not_found", status: 404, requestId: "rid" });
  });

  it("clears the session through the registered handler on 401", async () => {
    tokenStore.set("expired", 3600);
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { code: "authentication_failed", message: "expired" } }), { status: 401 })));
    await expect(request("/api/v1/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("maps network failures to a friendly ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(request("/health")).rejects.toMatchObject({ code: "network_error", status: 0, isNetwork: true });
  });

  it("drops expired tokens from storage", () => {
    tokenStore.set("old", -10);
    expect(tokenStore.get()).toBeNull();
  });
});
