import { defineConfig } from "@playwright/test";

// PW_CHROMIUM_PATH lets a machine that already has a Chromium (but not Playwright's own
// download) run the suite. CI installs the browser with `npx playwright install chromium`.
const executablePath = process.env.PW_CHROMIUM_PATH || undefined;

export default defineConfig({
  testDir: "./tests",
  timeout: 180_000,
  retries: 0, // a retry would hide exactly the flakiness this test exists to expose
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:8080",
    viewport: { width: 1280, height: 900 },
    trace: "retain-on-failure",
    launchOptions: { executablePath },
  },
  outputDir: "test-results",
});
