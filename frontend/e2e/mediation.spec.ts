import type { Page } from "@playwright/test";

import { expect, test } from "./support/test";

/** Opens a demo case from the cases list and starts the mediator on it. */
async function mediate(page: Page, id: string) {
  await page.goto("/cases");
  await page.getByRole("link", { name: id }).click();
  await expect(page.getByRole("heading", { name: id, level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Mediate", exact: true }).click();
}

/** The app's main navigation, in the sidebar. */
const nav = (page: Page) => page.getByRole("navigation", { name: "Main" });

const status = (page: Page) =>
  page.locator("header").getByText(/^(Open|Mediating|Needs you|Resolved|Rejected|Didn't finish)$/);

test("streams a mediation Settle can carry out alone, and records it", async ({ page }) => {
  await mediate(page, "FIXTURE-NAD-001");

  const reasoning = page.getByRole("list", { name: "Reasoning" });
  await expect(reasoning).toContainText("Classify the dispute");
  await expect(reasoning).toContainText("The shirt was delivered in the wrong size");
  await expect(page.getByText("Checks the mediator ran")).toBeVisible();

  const decision = page.getByRole("region", { name: "Decision" });
  await expect(decision).toContainText("Reship");
  await expect(decision).toContainText("91% confident");
  await expect(decision.getByText("Dry run")).toBeVisible();
  await expect(status(page)).toHaveText("Resolved");
  await expect(page.getByText("Settle carried out its decision")).toBeVisible();

  await nav(page).getByRole("link", { name: "Audit trail" }).click();
  const row = page.getByRole("row", { name: /FIXTURE-NAD-001/ });
  await expect(row).toContainText("Dry run");
  await expect(row).toContainText("Offered a replacement to the buyer");

  await row.getByRole("link").click();
  const sheet = page.getByRole("dialog", { name: /Decision on FIXTURE-NAD-001/ });
  await expect(sheet.getByRole("region", { name: "How Settle decided" })).toContainText(
    "Replace items sent in the wrong size.",
  );
  await expect(sheet.getByRole("region", { name: "Record", exact: true })).toContainText(
    "scripted-e2e-model",
  );
  await expect(page).toHaveURL(/[?&]entry=/);
});

test("sends a recommendation to the seller, who approves it", async ({ page }) => {
  await mediate(page, "FIXTURE-NR-001");

  const decision = page.getByRole("region", { name: "Decision" });
  await expect(decision).toContainText("Escalated to you");
  await expect(decision).toContainText("Why: Confidence 0.74 below threshold 0.80.");
  await expect(status(page)).toHaveText("Needs you");
  await expect(nav(page).getByRole("link", { name: "Cases, 1 waiting on you" })).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Approve this recommendation?" });
  await expect(confirm).toContainText("Settle will refund $59.99 to the buyer through PayPal.");
  await confirm.getByRole("button", { name: "Approve and refund $59.99" }).click();

  await expect(page.getByText("Recommendation approved", { exact: true })).toBeVisible();
  await expect(status(page)).toHaveText("Resolved");
  await expect(page.getByText("You approved, and Settle carried it out")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toBeHidden();
  await expect(nav(page).getByRole("link", { name: "Cases", exact: true })).toBeVisible();

  await nav(page).getByRole("link", { name: "Audit trail" }).click();
  await expect(page.getByRole("row", { name: /FIXTURE-NR-001/ })).toHaveCount(2);
  // Both entries can land in the same second on SQLite, which then has no order between them.
  await expect(
    page.getByRole("row", { name: /FIXTURE-NR-001/ }).filter({ hasText: "Approved by you" }),
  ).toHaveCount(1);
  await page.getByRole("tab", { name: "Sent to you" }).click();
  await expect(page).toHaveURL(/gate=escalate/);
  await expect(page.getByRole("row", { name: /FIXTURE-NR-001/ })).toHaveCount(1);
});

test("sends a case with no clear outcome to the seller, who rejects it", async ({ page }) => {
  await mediate(page, "FIXTURE-UNAUTH-001");

  const decision = page.getByRole("region", { name: "Decision" });
  await expect(decision).toContainText("No clear outcome");
  await expect(decision).toContainText(
    "Check the order against the buyer's account history before deciding.",
  );

  await page.getByRole("button", { name: "Reject" }).click();
  await page
    .getByRole("alertdialog", { name: "Reject this recommendation?" })
    .getByRole("button", { name: "Reject" })
    .click();

  await expect(page.getByText("Recommendation rejected", { exact: true })).toBeVisible();
  await expect(status(page)).toHaveText("Rejected");
  await expect(page.getByText("You rejected the recommendation")).toBeVisible();

  await nav(page).getByRole("link", { name: "Cases", exact: true }).click();
  await page.getByRole("tab", { name: /All/ }).click();
  await expect(page.getByRole("row", { name: /FIXTURE-UNAUTH-001/ })).toContainText("Rejected");
});
