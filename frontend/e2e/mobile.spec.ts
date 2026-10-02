/** TEST 5 — phone viewport: drawer sidebar, chat, citation → evidence bottom sheet → close. */
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.log(`PAGEERROR ${error.message}\n${error.stack ?? ""}`));
  page.on("console", (message) => {
    if (message.type() === "error") console.log(`CONSOLE ${message.text()}`);
  });
});

test("mobile: open sidebar → chat → open citation → evidence sheet → close; no horizontal overflow", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Username").fill(`e2e_mob_${Date.now().toString(36)}`);
  await page.getByLabel(/^Password$/).fill("E2e-pass-word-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // Sidebar is a drawer on phones.
  await expect(page.getByRole("navigation", { name: "Conversations" })).toBeHidden();
  await page.getByRole("button", { name: "Open conversations" }).click();
  const drawer = page.getByRole("dialog", { name: "Conversations" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("button", { name: "New research" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  await page.getByTestId("composer-input").fill("What is Article 21 of the Constitution of India?");
  await page.getByTestId("send-button").click();
  const assistant = page.getByTestId("assistant-message").first();
  await expect(assistant).toHaveAttribute("data-status", "complete", { timeout: 30_000 });

  // Citation opens the evidence bottom sheet; Close returns to the conversation.
  await assistant.getByRole("button", { name: /Citation C1/ }).first().click();
  const sheet = page.getByRole("dialog", { name: "Evidence" });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByTestId("source-card").first()).toHaveAttribute("aria-current", "true");
  await sheet.getByRole("button", { name: "Close Evidence" }).click();
  await expect(sheet).toBeHidden();
  await expect(assistant).toBeVisible();

  // Composer remains reachable and the page never scrolls sideways.
  await expect(page.getByTestId("composer-input")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow).toBe(false);
});
