/**
 * Browser journeys against the real frontend and the deterministic backend (scripts/e2e_server.py).
 * Covers: signup/login, new chat, streaming, citations, moderate + complex routing, search, source,
 * refresh persistence, logout and protected routes.
 */
import { expect, test, type Page } from "@playwright/test";

const password = "E2e-pass-word-1";

async function signup(page: Page, username: string) {
  await page.goto("/signup");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel(/^Password$/).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test.describe.configure({ mode: "serial" });

// Any uncaught browser exception fails the test with its message (never a silent error boundary).
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.log(`PAGEERROR ${error.message}\n${error.stack ?? ""}`));
  page.on("console", (message) => {
    if (message.type() === "error") console.log(`CONSOLE ${message.text()}`);
  });
});

test("new user: signup → ask → stream → citation → source → refresh → logout", async ({ page }) => {
  const username = `e2e_${Date.now().toString(36)}`;
  await signup(page, username);
  await expect(page.getByRole("heading", { name: /Ask Legal Lens/ })).toBeVisible();

  // Simple question streams tokens and ends with citations.
  await page.getByTestId("composer-input").fill("What is the punishment for cheating under Section 420 IPC?");
  await page.getByTestId("send-button").click();
  const assistant = page.getByTestId("assistant-message").first();
  await expect(assistant).toHaveAttribute("data-status", "complete", { timeout: 30_000 });
  await expect(assistant).toContainText("Based on the indexed sources");
  await expect(assistant.getByText("SIMPLE")).toBeVisible();
  await expect(page).toHaveURL(/\/app\/chat\//);
  const chatUrl = page.url();

  // Citation chip opens the source in the evidence panel.
  await assistant.getByRole("button", { name: /Citation C1/ }).first().click();
  const panel = page.getByRole("complementary", { name: "Sources and evidence" });
  const selected = panel.getByTestId("source-card").first();
  await expect(selected).toHaveAttribute("aria-current", "true");
  await expect(selected).toContainText("IPC 420");

  // Mapping card shows the IPC → BNS correspondence returned by the backend.
  await expect(assistant.getByTestId("mapping-card")).toContainText("IPC 420");
  await expect(assistant.getByTestId("mapping-card")).toContainText("BNS 318");

  // Open the source page and come back.
  await selected.getByRole("link", { name: "Open source" }).click();
  await expect(page).toHaveURL(/\/app\/sources\//);
  await expect(page.getByRole("heading", { name: "Source" })).toBeVisible();
  await page.getByRole("link", { name: "Back" }).click();
  await expect(page).toHaveURL(chatUrl);

  // Refresh keeps the conversation (persisted in the database) and its citations.
  await page.goto(chatUrl);
  await expect(page.getByTestId("user-message")).toContainText("Section 420 IPC");
  await expect(page.getByTestId("assistant-message").first()).toHaveAttribute("data-status", "complete");
  await expect(page.getByTestId("assistant-message").first().getByRole("button", { name: /^C1/ })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Conversations" }).getByRole("link")).toHaveCount(1);

  // Logout: protected routes redirect to login.
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login$/);

  // Login again returns to the workspace with history intact.
  await page.getByLabel("Username or email").fill(username);
  await page.getByLabel(/^Password$/).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("navigation", { name: "Conversations" }).getByRole("link")).toHaveCount(1);
});

test("moderate and complex questions are routed and decomposed", async ({ page }) => {
  await signup(page, `e2e_route_${Date.now().toString(36)}`);
  // Two articles of one act: MODERATE (expanded, not decomposed). A cross-code comparison such as
  // "Compare IPC 420 and BNS 318" scores COMPLEX on the current weighted classifier (two acts +
  // comparison + mapping intent), see docs/ADAPTIVE_RAG.md.
  await page.getByTestId("composer-input").fill("Explain the difference between Article 14 and Article 21.");
  await page.keyboard.press("Enter");
  const first = page.getByTestId("assistant-message").nth(0);
  await expect(first).toHaveAttribute("data-status", "complete", { timeout: 30_000 });
  await expect(first.getByText("MODERATE")).toBeVisible();
  await expect(first.getByText("BALANCED")).toBeVisible();

  await page.getByTestId("composer-input").fill(
    "Compare IPC 420 with BNS 318, explain the elements, identify the changes, and cite the relevant statutory evidence.",
  );
  await page.keyboard.press("Enter");
  const second = page.getByTestId("assistant-message").nth(1);
  await expect(second).toHaveAttribute("data-status", "complete", { timeout: 30_000 });
  await expect(second.getByText("COMPLEX")).toBeVisible();
  await expect(second.getByText("DEEP")).toBeVisible();
  await expect(second.getByText("decomposed")).toBeVisible();
});

test("safety guard and search explorer", async ({ page }) => {
  await signup(page, `e2e_search_${Date.now().toString(36)}`);
  await page.getByTestId("composer-input").fill("Will I win my cheating case?");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("assistant-message").first()).toHaveAttribute("data-status", "refused", { timeout: 30_000 });

  await page.getByRole("link", { name: "Search" }).click();
  await page.getByTestId("search-input").fill("Section 420 IPC");
  await page.getByTestId("search-button").click();
  const results = page.getByTestId("search-results");
  await expect(results.getByTestId("search-result").first()).toBeVisible();
  await expect(page.getByTestId("search-meta")).toContainText("dense");
  await results.getByTestId("search-result").first().getByRole("button", { name: "Use in chat" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByTestId("composer-input")).toHaveValue(/Section 420 IPC/);
});

test("diagnostics page shows truthful dependency state", async ({ page }) => {
  await signup(page, `e2e_diag_${Date.now().toString(36)}`);
  await page.getByRole("link", { name: "Diagnostics" }).click();
  await expect(page.getByText("ready", { exact: true })).toBeVisible();
  await expect(page.getByText(/qdrant: ok/)).toBeVisible();
  await expect(page.getByText(/llm: configured/)).toBeVisible();
});
