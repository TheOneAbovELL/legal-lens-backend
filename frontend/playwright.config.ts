import { defineConfig, devices } from "@playwright/test";

// E2E runs against a deterministic backend (scripts/e2e_server.py: in-memory index with the fixture
// corpus, temporary database, scripted LLM) so browser tests never depend on Qdrant Cloud or Groq.
const backendPort = Number(process.env.E2E_BACKEND_PORT || 8011);
const frontendPort = Number(process.env.E2E_FRONTEND_PORT || 5174);
const python = process.env.E2E_PYTHON || (process.platform === "win32" ? "..\\venv\\Scripts\\python.exe" : "../venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // Visual snapshots are rendered with local fonts/platform; they are generated and checked on the
  // developer machine (`--update-snapshots` to refresh) and skipped on CI runners.
  snapshotPathTemplate: "{testDir}/__snapshots__/{testFileName}/{arg}{ext}",
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: process.env.CI ? [/mobile\.spec\.ts/, /visual\.spec\.ts/] : /mobile\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `${python} ../scripts/e2e_server.py --port ${backendPort}`,
      url: `http://127.0.0.1:${backendPort}/ready`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: { VITE_DEV_PROXY_TARGET: `http://127.0.0.1:${backendPort}`, VITE_ENABLE_DIAGNOSTICS: "true" },
    },
  ],
});
