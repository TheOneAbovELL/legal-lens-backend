import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => console.log(`PAGEERROR ${error.message}\n${error.stack ?? ""}`));
  page.on("console", (message) => {
    if (message.type() === "error") console.log(`CONSOLE ${message.text()}`);
  });
});

test("mobile: drawers for conversations and evidence, no horizontal overflow", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Username").fill(`e2e_mob_${Date.now().toString(36)}`);
  await page.getByLabel(/^Password$/).fill("E2e-pass-word-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // Sidebar is hidden; the menu button opens it as a drawer.
  await expect(page.getByRole("navigation", { name: "Conversations" })).toBeHidden();
  await page.getByRole("button", { name: "Open conversations" }).click();
  await expect(page.getByRole("dialog", { name: "Conversations" })).toBeVisible();
  await page.getByRole("button", { name: "Close Conversations" }).click();

  await page.getByTestId("composer-input").fill("What is Article 21 of the Constitution of India?");
  await page.getByTestId("send-button").click();
  const assistant = page.getByTestId("assistant-message").first();
  await expect(assistant).toHaveAttribute("data-status", "complete", { timeout: 30_000 });

  // Citation opens the evidence drawer on small screens.
  await assistant.getByRole("button", { name: /Citation C1/ }).first().click();
  const drawer = page.getByRole("dialog", { name: "Sources" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByTestId("source-card").first()).toHaveAttribute("aria-current", "true");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow).toBe(false);
});
