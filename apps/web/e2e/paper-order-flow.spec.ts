import { expect, test } from "@playwright/test";

/**
 * The one Playwright journey this app ships (ADR-030): propose a paper
 * order, confirm it through the human-confirmation gate, and see it
 * transition off DRAFT. Drives routers/orders.py's simple,
 * broker-agnostic manual-entry lifecycle (POST /orders,
 * POST /orders/{id}/confirm) — that router's own module docstring is
 * explicit that neither account type reaches a real broker here (a
 * prior version of this comment claimed otherwise; corrected in
 * Revision Prompt 16, task: release-gate tests). The endpoint that
 * actually reaches a broker (POST /order-approvals/{id}/submit, a
 * separate recommendation-driven governance flow) is covered by
 * tests/test_release_gate_journeys.py instead, over the API directly.
 * Runs against whatever real dev + API servers + seeded data are
 * already up locally — see playwright.config.ts's header comment.
 */
test("propose and confirm a paper order for a seeded liquid symbol", async ({ page }) => {
  await page.goto("/portfolio");

  await expect(page.getByRole("heading", { name: "Portfolio" })).toBeVisible();

  await page.getByPlaceholder("AAPL").fill("AAPL");
  await page.getByRole("button", { name: "Propose order" }).click();

  const row = page.locator("tr", { hasText: "AAPL" }).first();
  await expect(row).toBeVisible();
  await expect(row.getByText("DRAFT")).toBeVisible();

  // First click reveals the ConfirmButton's inline gate (principle 11) —
  // nothing has reached Alpaca yet.
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(row.getByText("Are you sure?")).toBeVisible();

  // Second click is the actual confirmation, which submits to the real
  // Alpaca paper-trading API.
  await row.getByRole("button", { name: "Confirm" }).click();

  await expect(row.getByText("DRAFT")).toHaveCount(0, { timeout: 15_000 });
  await expect(row.getByText(/SUBMITTED|FILLED/)).toBeVisible();
});
