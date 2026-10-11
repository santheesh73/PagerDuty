import { expect, test } from "@playwright/test";

// The whole product in one pass, through the real browser and the real stack
// (nginx -> gunicorn -> Postgres, Celery worker and Beat, Redis):
//
//   sign in -> fire an alert -> the incident opens and pages level 1 -> nobody answers, so
//   the worker escalates to level 2 -> acknowledge -> resolve -> the timeline tells the story.
//
// The escalation step waits out the seeded policy's real one-minute delay on purpose: it is
// the only step that proves Beat, the worker and the broker are wired together.
test("alert -> page -> escalate -> acknowledge -> resolve", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Use" }).first().click(); // responder demo account
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.getByRole("link", { name: "Services", exact: true }).first().click();
  await page.getByRole("link", { name: "checkout-api" }).click();
  await page.getByRole("button", { name: "Send test alert" }).click();
  await page.getByRole("button", { name: "Open incident" }).click();

  await page.waitForURL(/\/incidents\/\d+/);
  const incidentId = page.url().split("/").pop();
  await expect(page.getByText("Level 1 · current")).toBeVisible();

  // Nobody acknowledges, so the worker escalates when the one-minute delay passes.
  await expect(page.getByText("Level 2 · current")).toBeVisible({ timeout: 120_000 });

  await page.getByRole("button", { name: /^Acknowledge/ }).click();
  await expect(page.getByText(/^Acknowledged #/)).toBeVisible();
  await page.getByRole("button", { name: /Resolve/ }).click();
  await expect(page.getByText(/^Resolved #/)).toBeVisible();

  // The browser session is authenticated, so read the timeline the way the UI does.
  const types = await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/incidents/${id}/timeline/`);
    const body = await response.json();
    return body.results.map((event: { type: string }) => event.type).reverse();
  }, incidentId);
  const story = types.filter((type: string) => type !== "notified");
  expect(story).toEqual(["triggered", "escalated", "acknowledged", "resolved"]);
});
