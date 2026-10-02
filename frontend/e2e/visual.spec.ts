/**
 * Visual regression for the important UI states, plus full-page captures used by the design report.
 * Snapshots live next to this file (platform-specific); regenerate with `npx playwright test e2e/visual.spec.ts --update-snapshots`.
 */
import { expect, test, type Page } from "@playwright/test";

const SHOTS = "../docs/screenshots";
const VIEWPORTS = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "laptop-1280", width: 1280, height: 800 },
  { name: "tablet-1024", width: 1024, height: 768 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "phone-430", width: 430, height: 932 },
  { name: "phone-390", width: 390, height: 844 },
  { name: "phone-375", width: 375, height: 812 },
];

async function signup(page: Page) {
  await page.goto("/signup");
  await page.getByLabel("Username").fill(`e2e_vis_${Date.now().toString(36)}`);
  await page.getByLabel(/^Password$/).fill("E2e-pass-word-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

/** Hide time-dependent text so snapshots stay stable. */
async function freeze(page: Page) {
  await page.addStyleTag({ content: ".turn__time, .conv__meta { visibility: hidden !important; }" });
}

test.describe("visual states", () => {
  test("login, empty workspace, conversation, evidence, search, mobile workspace", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/login.png`, fullPage: true });
    await expect(page).toHaveScreenshot("login.png", { maxDiffPixelRatio: 0.03 });

    await signup(page);
    await expect(page.getByRole("heading", { name: /Research law with evidence/ })).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/workspace-empty.png` });
    await expect(page).toHaveScreenshot("workspace-empty.png", { maxDiffPixelRatio: 0.03 });

    await page.getByTestId("composer-input").fill("Compare IPC 420 with BNS 318, explain the elements, identify the changes, and cite the relevant statutory evidence.");
    await page.getByTestId("send-button").click();
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "complete", { timeout: 30_000 });
    await freeze(page);
    await page.screenshot({ path: `${SHOTS}/conversation.png` });
    await expect(page).toHaveScreenshot("conversation.png", { maxDiffPixelRatio: 0.03 });

    await assistant.getByRole("button", { name: /Citation C1/ }).first().click();
    await expect(page.getByRole("complementary", { name: "Sources and evidence" }).getByTestId("source-card").first()).toHaveAttribute("aria-current", "true");
    await page.screenshot({ path: `${SHOTS}/evidence.png` });
    await expect(page).toHaveScreenshot("evidence.png", { maxDiffPixelRatio: 0.03 });

    await page.goto("/app/search?q=Section%20420%20IPC");
    await expect(page.getByTestId("search-results").getByTestId("search-result").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/search.png` });
    await expect(page).toHaveScreenshot("search.png", { maxDiffPixelRatio: 0.03 });

    // Dark theme of the conversation (designed separately, not inverted).
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goBack();
    await expect(page.getByTestId("assistant-message").last()).toHaveAttribute("data-status", "complete");
    await freeze(page);
    await page.screenshot({ path: `${SHOTS}/conversation-dark.png` });
    await page.emulateMedia({ colorScheme: "light" });

    // Responsive captures (no snapshot assertions beyond overflow; sizes are documented in the report).
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/app");
      await expect(page.getByTestId("composer-input")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      expect(overflow, `${vp.name} overflows horizontally`).toBe(false);
      await page.screenshot({ path: `${SHOTS}/workspace-${vp.name}.png` });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link").first().click();
    await page.getByTestId("composer-input").fill("What is Article 21 of the Constitution of India?");
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("assistant-message").last()).toHaveAttribute("data-status", "complete", { timeout: 30_000 });
    await freeze(page);
    await page.screenshot({ path: `${SHOTS}/mobile-conversation.png` });
    await expect(page).toHaveScreenshot("mobile-conversation.png", { maxDiffPixelRatio: 0.04 });
    await page.getByTestId("assistant-message").last().getByRole("button", { name: /Citation C1/ }).first().click();
    await expect(page.getByRole("dialog", { name: "Evidence" })).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/mobile-evidence-sheet.png` });
  });
});
