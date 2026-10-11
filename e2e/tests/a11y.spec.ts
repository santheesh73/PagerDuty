import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Accessibility: no serious or critical axe violations on any main page (WCAG 2.1 A/AA rules).
// Minor and moderate findings are printed, not failed, so they are visible without blocking.
const PAGES = [
  "/",
  "/incidents",
  "/services",
  "/escalation-policies",
  "/schedules",
  "/analytics",
  "/notifications",
  "/settings/security",
  "/audit-log",
];

async function audit(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  for (const v of results.violations) {
    console.log(`${label}: [${v.impact}] ${v.id} (${v.nodes.length}) ${v.help}`);
  }
  expect(
    blocking.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`),
    `${label} has serious/critical accessibility violations`,
  ).toEqual([]);
}

test("sign-in, password reset and every main page have no serious accessibility violations", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await audit(page, "/login");
  await page.goto("/forgot-password");
  await expect(page.getByRole("button", { name: "Send reset link" })).toBeVisible();
  await audit(page, "/forgot-password");

  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@demo.local");
  await page.getByLabel("Password").fill("demo1234");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  for (const path of PAGES) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await audit(page, path);
  }
});
