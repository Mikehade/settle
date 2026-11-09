import { expect, test } from "./support/test";

test("saves a fairness policy that changes what Settle does alone", async ({ page }) => {
  await page.goto("/policy");
  await expect(page.getByRole("heading", { name: "Fairness policy", level: 1 })).toBeVisible();

  await page.getByLabel("Your rules").fill("Refund in full when an order never shipped.");
  await page.getByLabel("Confidence needed to act alone").fill("70");
  await page.getByRole("button", { name: "Save policy" }).click();
  await expect(page.getByText("Fairness policy saved")).toBeVisible();
  await expect(page.getByText(/^Saved /)).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Your rules")).toHaveValue(
    "Refund in full when an order never shipped.",
  );
  await expect(page.getByLabel("Confidence needed to act alone")).toHaveValue("70");

  // At 74% confident, the earbuds refund came to the seller under the default 80%. Now it doesn't.
  await page.goto("/cases/FIXTURE-NR-001");
  await page.getByRole("button", { name: "Mediate", exact: true }).click();
  const decision = page.getByRole("region", { name: "Decision" });
  await expect(decision).toContainText("Refund $59.99");
  await expect(decision.getByText("Dry run")).toBeVisible();
  await expect(decision).not.toContainText("Escalated to you");
});

test("asks before leaving unsaved changes", async ({ page }) => {
  await page.goto("/policy");
  await page.getByLabel("Your rules").fill("Be generous.");
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Audit trail" })
    .click();

  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page).toHaveURL(/\/policy$/);
  await expect(page.getByLabel("Your rules")).toHaveValue("Be generous.");

  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Audit trail" })
    .click();
  await page.getByRole("button", { name: "Leave" }).click();
  await expect(page).toHaveURL(/\/audit$/);
});
