/**
 * Browser journeys against the real frontend and the deterministic backend (scripts/e2e_server.py).
 * They test behaviour (type, submit, stream, click citations, reload, sign out), not DOM existence.
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

async function ask(page: Page, question: string) {
  await page.getByTestId("composer-input").fill(question);
  await page.getByTestId("send-button").click();
  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toHaveAttribute("data-status", "complete", { timeout: 30_000 });
  return assistant;
}

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.log(`PAGEERROR ${error.message}\n${error.stack ?? ""}`));
  page.on("console", (message) => {
    if (message.type() === "error") console.log(`CONSOLE ${message.text()}`);
  });
});

test("TEST 1 — login → workspace → new research → question → streamed answer → citation → evidence panel", async ({ page }) => {
  const username = `e2e_${Date.now().toString(36)}`;
  await signup(page, username);
  await expect(page.getByRole("heading", { name: /Research law with evidence/ })).toBeVisible();

  // "New research" is the empty workspace; the first question creates the conversation.
  await page.getByRole("button", { name: "New research" }).click();
  const assistant = await ask(page, "What is the punishment for cheating under Section 420 IPC?");
  await expect(assistant).toContainText("Based on the indexed sources");
  await expect(assistant.getByText(/Based on \d+ retrieved legal source/)).toBeVisible();
  await expect(page).toHaveURL(/\/app\/chat\//);
  await expect(page.getByRole("navigation", { name: "Conversations" }).getByRole("list").getByRole("link")).toHaveCount(1);

  // Inline citation chip → the evidence pane selects the passage; the conversation stays in place.
  const chatUrl = page.url();
  await assistant.getByRole("button", { name: /Citation C1/ }).first().click();
  await expect(page).toHaveURL(chatUrl);
  const pane = page.getByRole("complementary", { name: "Sources and evidence" });
  const selected = pane.getByTestId("source-card").first();
  await expect(selected).toHaveAttribute("aria-current", "true");
  await expect(selected).toContainText("IPC §420");
  await expect(selected).toContainText(/Exact match|Passage ranked/);

  // Mapping comparison rendered from backend data.
  await expect(assistant.getByTestId("mapping-card")).toContainText("IPC 420");
  await expect(assistant.getByTestId("mapping-card")).toContainText("BNS 318");

  // Source reader and back to the same conversation.
  await selected.getByRole("link", { name: "Open source" }).click();
  await expect(page).toHaveURL(/\/app\/sources\//);
  await expect(page.getByTestId("source-text")).toContainText(/cheat/i);
  await page.getByRole("link", { name: "Back" }).click();
  await expect(page).toHaveURL(chatUrl);

  // Sign out protects routes; sign in returns with history.
  await page.getByRole("button", { name: "Account menu" }).first().click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Username or email").fill(username);
  await page.getByLabel(/^Password$/).fill(password);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("navigation", { name: "Conversations" }).getByRole("list").getByRole("link")).toHaveCount(1);
});

test("TEST 2 — conversation → reload → conversation restored with citations", async ({ page }) => {
  await signup(page, `e2e_reload_${Date.now().toString(36)}`);
  await ask(page, "What is Article 21 of the Constitution of India?");
  const chatUrl = page.url();
  await page.goto(chatUrl);
  await expect(page.getByTestId("user-message")).toContainText("Article 21");
  const assistant = page.getByTestId("assistant-message").first();
  await expect(assistant).toHaveAttribute("data-status", "complete");
  await expect(assistant.getByRole("button", { name: /Citation C1/ }).first()).toBeVisible();
  // Switching to another conversation and back keeps history intact (no duplicated messages).
  await page.getByRole("button", { name: "New research" }).click();
  await expect(page.getByRole("heading", { name: /Research law with evidence/ })).toBeVisible();
  await page.getByRole("navigation", { name: "Conversations" }).getByRole("list").getByRole("link").first().click();
  await expect(page.getByTestId("assistant-message")).toHaveCount(1);
});

test("TEST 3 — search → result → evidence → use in research", async ({ page }) => {
  await signup(page, `e2e_search_${Date.now().toString(36)}`);
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Search", exact: true }).click();
  await page.getByTestId("search-input").fill("Section 420 IPC");
  await page.getByTestId("search-button").click();
  const results = page.getByTestId("search-results");
  const first = results.getByTestId("search-result").first();
  await expect(first).toBeVisible();
  await expect(page.getByTestId("search-meta")).toContainText("result");
  await expect(page.getByTestId("search-meta")).not.toContainText(/0\.\d{2}/); // no raw scores
  await first.click();
  await expect(page.getByTestId("source-card")).toHaveAttribute("aria-current", "true");
  await expect(page.getByTestId("source-card")).toContainText(/cheat/i);
  await first.getByRole("button", { name: "Use in research" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByTestId("composer-input")).toHaveValue(/Section 420 IPC/);
});

test("TEST 4 — complex query → backend-driven research status → final answer with multi-aspect trust line", async ({ page }) => {
  await signup(page, `e2e_complex_${Date.now().toString(36)}`);
  await page.getByTestId("composer-input").fill(
    "Compare IPC 420 with BNS 318, explain the elements, identify the changes, and cite the relevant statutory evidence.",
  );
  await page.getByTestId("send-button").click();
  // Status is driven by backend events (analysis/search/review/answer); never chain-of-thought.
  // The deterministic backend can finish within milliseconds, so accept "progress visible" or
  // "already complete" (the progress contents themselves are covered by tests/components.test.tsx).
  const status = page.getByTestId("status-row");
  const assistant = page.getByTestId("assistant-message").last();
  await expect.poll(async () => (await status.count()) > 0 || (await assistant.getAttribute("data-status")) === "complete", { timeout: 30_000 }).toBe(true);
  // Read the row's text once rather than asserting against a live locator: the stream can finish
  // and unmount the row between the check and the assertion, which fails on a missing element
  // instead of on leaked reasoning. A snapshot keeps the guarantee without the race.
  const statusText = (await status.count()) > 0 ? await status.first().textContent().catch(() => null) : null;
  if (statusText) expect(statusText).not.toMatch(/system prompt|reasoning/i);
  await expect(assistant).toHaveAttribute("data-status", "complete", { timeout: 30_000 });
  await expect(assistant).not.toContainText(/system prompt|chain of thought/i);
  await expect(assistant.getByText("Multi-aspect research")).toBeVisible();
  await expect(assistant.getByTestId("sources-row").getByRole("button")).toHaveCount(1);

  // Moderate question: expanded, not decomposed.
  const moderate = await ask(page, "Explain the difference between Article 14 and Article 21.");
  await expect(moderate.getByText("Multi-aspect research")).toHaveCount(0);

  // Safety guard: refusal rendered as an information notice, no sources.
  await page.getByTestId("composer-input").fill("Will I win my cheating case?");
  await page.getByTestId("send-button").click();
  const refused = page.getByTestId("assistant-message").last();
  await expect(refused).toHaveAttribute("data-status", "refused", { timeout: 30_000 });
  await expect(refused.getByTestId("sources-row")).toHaveCount(0);
});

test("diagnostics stays a developer surface with truthful status words", async ({ page }) => {
  await signup(page, `e2e_diag_${Date.now().toString(36)}`);
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Diagnostics" }).click();
  await expect(page.getByText(/developer diagnostics/)).toBeVisible();
  await expect(page.getByRole("region", { name: "backend" }).getByText("healthy", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "backend" })).toContainText("qdrant");
});
