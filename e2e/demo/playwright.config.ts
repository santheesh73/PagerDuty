import { defineConfig } from "@playwright/test";

// Records the README's demo GIF (scripts/record_demo.sh). Separate from playwright.config.ts so
// a normal `npx playwright test` never runs it.
export default defineConfig({
  testDir: ".",
  timeout: 240_000,
  retries: 0,
  reporter: [["list"]],
  outputDir: "../demo-results",
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:8080",
    viewport: { width: 1280, height: 800 },
    launchOptions: {
      executablePath: process.env.PW_CHROMIUM_PATH || undefined,
    },
  },
});
