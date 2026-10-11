import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// The README's demo, as one recorded take: an alert pages the on-call, nobody answers so it
// escalates, then it is acknowledged, unacknowledged and resolved. Frames are screenshots taken
// about 8 times a second (no video encoder needed); scripts/record_demo.sh joins them into
// docs/img/demo.gif. Against the one-container demo, set TICK_SECRET so the escalation timer is
// driven while the recording waits.

const FRAMES = path.join(__dirname, "..", "demo-results", "frames");
const FRAME_MS = 125; // 8 fps
const SPEEDUP = 12; // while waiting for the escalation, keep one frame in twelve

class Recorder {
  fast = false;
  private stopped = false;
  private loop: Promise<void> | undefined;

  constructor(private page: Page) {}

  start() {
    rmSync(FRAMES, { recursive: true, force: true });
    mkdirSync(FRAMES, { recursive: true });
    this.loop = (async () => {
      let tick = 0;
      let frame = 0;
      while (!this.stopped) {
        const started = Date.now();
        if (!this.fast || tick % SPEEDUP === 0) {
          const name = `frame-${String(frame++).padStart(5, "0")}.png`;
          await this.page
            .screenshot({ path: path.join(FRAMES, name) })
            .catch(() => undefined);
        }
        tick++;
        await new Promise((r) =>
          setTimeout(r, Math.max(0, FRAME_MS - (Date.now() - started))),
        );
      }
    })();
  }

  async stop() {
    this.stopped = true;
    await this.loop;
  }
}

const pause = (page: Page, ms = 1200) => page.waitForTimeout(ms);

async function tick(page: Page) {
  const secret = process.env.TICK_SECRET;
  if (secret)
    await page.request.post("/internal/tick/", {
      headers: { "X-Tick-Secret": secret },
    });
}

test("record the demo", async ({ page }) => {
  const recorder = new Recorder(page);
  await page.goto("/login");
  recorder.start();
  await pause(page);
  await page.getByRole("button", { name: "Use" }).first().click(); // responder demo account
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await pause(page, 2000);

  await page
    .getByRole("link", { name: "Services", exact: true })
    .first()
    .click();
  await page.getByRole("link", { name: "checkout-api" }).click();
  await pause(page);
  await page.getByRole("button", { name: "Send test alert" }).click();
  await pause(page);
  await page.getByRole("button", { name: "Open incident" }).click();
  await page.waitForURL(/\/incidents\/\d+/);
  await expect(page.getByText("Level 1 · current")).toBeVisible();
  await pause(page, 2500);

  // Nobody answers. The seeded policy escalates after a minute, which plays 12x faster.
  recorder.fast = true;
  await expect(async () => {
    await tick(page);
    await expect(page.getByText("Level 2 · current")).toBeVisible({
      timeout: 5_000,
    });
  }).toPass({ timeout: 150_000, intervals: [5_000] });
  recorder.fast = false;
  await pause(page, 2500);

  await page.getByRole("button", { name: /^Acknowledge/ }).click();
  await expect(page.getByText(/^Acknowledged #/)).toBeVisible();
  await pause(page, 2000);
  await page.getByRole("button", { name: /^Unacknowledge/ }).click();
  await pause(page, 2000);
  await page.getByRole("button", { name: /Resolve/ }).click();
  await expect(page.getByText(/^Resolved #/)).toBeVisible();
  await pause(page, 3000);
  await recorder.stop();
});
