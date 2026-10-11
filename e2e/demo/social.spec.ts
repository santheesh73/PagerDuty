import path from "node:path";
import { expect, test } from "@playwright/test";

// The repository's social preview (docs/img/social-preview.png, 1280x640, uploaded by hand in
// Settings -> General -> Social preview): the name and promise beside a real screenshot of the
// incident page, so the card shows the product as it is. Run by scripts/record_demo.sh.

const OUT = path.join(
  __dirname,
  "..",
  "..",
  "docs",
  "img",
  "social-preview.png",
);

test("social preview", async ({ page, browser }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Use" }).first().click(); // responder demo account
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page
    .getByRole("link", { name: "Incidents", exact: true })
    .first()
    .click();
  await page.locator('tbody a[href^="/incidents/"]').first().click();
  await page.waitForURL(/\/incidents\/\d+/);
  await expect(
    page.getByText(/Level \d · current|Resolved/).first(),
  ).toBeVisible();
  await page.waitForTimeout(500);
  const shot = (await page.screenshot()).toString("base64");

  const card = await browser.newPage({
    viewport: { width: 1280, height: 640 },
  });
  await card.setContent(`<!doctype html>
<html><head><style>
  body { margin: 0; width: 1280px; height: 640px; overflow: hidden; background: #0f172a;
         font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #f8fafc; }
  .text { position: absolute; left: 64px; top: 0; bottom: 0; width: 420px;
          display: flex; flex-direction: column; justify-content: center; }
  h1 { font-size: 88px; margin: 0 0 20px; letter-spacing: -2px; }
  h1 span { color: #f43f5e; }
  p { font-size: 28px; line-height: 1.35; margin: 0 0 28px; color: #cbd5e1; }
  ul { list-style: none; padding: 0; margin: 0; font-size: 20px; line-height: 1.8; color: #94a3b8; }
  img { position: absolute; left: 540px; top: 60px; width: 840px; border-radius: 12px;
        box-shadow: 0 24px 64px rgba(0, 0, 0, 0.55); }
</style></head><body>
  <div class="text">
    <h1>Pulse<span>.</span></h1>
    <p>Alerts in, the right human paged exactly once, every action on the record.</p>
    <ul><li>Restart-safe escalation timers</li><li>Race-free deduplication</li>
        <li>DST-correct on-call rotations</li></ul>
  </div>
  <img src="data:image/png;base64,${shot}" alt="">
</body></html>`);
  await card.screenshot({ path: OUT });
  await card.close();
});
