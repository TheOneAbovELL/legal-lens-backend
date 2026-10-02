import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { App } from "@/app/App";
import { AppProviders } from "@/app/providers";
import { validateSignup } from "@/features/auth/SignupPage";
import { tokenStore } from "@/lib/auth/token";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const me = { id: "u1", username: "alice", email: null, role: "citizen", created_at: "2026-10-02T00:00:00Z" };

function mountAt(path: string) {
  window.history.pushState({}, "", path);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<AppProviders client={client}><App /></AppProviders>);
}

describe("authentication", () => {
  it("validates the signup form before calling the backend", () => {
    expect(validateSignup({ username: "ab", email: "", password: "Secret-pass-1" })).toHaveProperty("username");
    expect(validateSignup({ username: "alice", email: "nope", password: "Secret-pass-1" })).toHaveProperty("email");
    expect(validateSignup({ username: "alice", email: "", password: "onlyletters" })).toHaveProperty("password");
    expect(validateSignup({ username: "alice", email: "a@b.io", password: "Secret-pass-1" })).toEqual({});
  });

  it("redirects anonymous users to login and returns them after signing in", async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/auth/login")) return json({ message: "ok", user: "alice", role: "citizen", access_token: "tok", token_type: "bearer", expires_in: 3600 });
      if (url.endsWith("/auth/me")) return json(me);
      if (url.endsWith("/health")) return json({ status: "healthy" });
      if (url.endsWith("/ready")) return json({ status: "ready", checks: {}, failed: [], components: [] });
      if (url.endsWith("/conversations")) return json({ conversations: [], total: 0 });
      return json({ error: { code: "not_found", message: "no" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    mountAt("/app/search");
    expect(await screen.findByText(/Continue your research/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/username or email/i), "alice");
    await user.type(screen.getByLabelText(/^password$/i), "Secret-pass-1");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(window.location.pathname).toBe("/app/search"));
    expect(tokenStore.get()).toBe("tok");
    const loginCall = fetchMock.mock.calls.find(([u]) => (u as string).endsWith("/auth/login"));
    expect((loginCall?.[1] as RequestInit | undefined)?.headers).not.toHaveProperty("Authorization");
  });

  it("shows invalid credentials without leaking which part was wrong", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/auth/login")) return json({ error: { code: "authentication_failed", message: "Invalid username or password." } }, 401);
      return json({ status: "healthy" });
    }));
    mountAt("/login");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/username or email/i), "alice");
    await user.type(screen.getByLabelText(/^password$/i), "wrong-pass-1");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
  });

  it("clears an expired stored token and explains why", async () => {
    tokenStore.set("stale", 3600);
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/auth/me")) return json({ error: { code: "authentication_failed", message: "expired" } }, 401);
      return json({ status: "healthy" });
    }));
    mountAt("/app");
    expect(await screen.findByText(/session expired/i)).toBeInTheDocument();
    expect(tokenStore.get()).toBeNull();
    expect(window.location.pathname).toBe("/login");
  });

  it("logs out from the account menu and protects routes again", async () => {
    tokenStore.set("tok", 3600);
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/auth/me")) return json(me);
      if (url.endsWith("/health")) return json({ status: "healthy" });
      if (url.endsWith("/ready")) return json({ status: "ready", checks: {}, failed: [], components: [] });
      if (url.endsWith("/conversations")) return json({ conversations: [], total: 0 });
      return json({ error: { code: "not_found", message: "no" } }, 404);
    }));
    mountAt("/app");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: /account menu/i }))[0]!);
    await user.click(screen.getByRole("menuitem", { name: /sign out/i }));
    await waitFor(() => expect(window.location.pathname).toBe("/login"));
    expect(tokenStore.get()).toBeNull();
  });
});
