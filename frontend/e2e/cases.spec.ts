import { expect, test } from "./support/test";

test("searches the cases, and keeps the search in the address", async ({ page }) => {
  await page.goto("/cases");
  await expect(page.getByRole("row", { name: /FIXTURE-/ })).toHaveCount(3);

  const search = page.getByRole("searchbox", { name: "Search cases" });
  await search.fill("nothing like this");
  await expect(page.getByRole("row", { name: /FIXTURE-/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Clear search" })).toBeVisible();

  await search.fill("described");
  await expect(page).toHaveURL(/[?&]q=described/);
  await expect(page.getByRole("row", { name: /FIXTURE-/ })).toHaveCount(1);

  await page.reload();
  await expect(search).toHaveValue("described");
  await page.getByRole("link", { name: "FIXTURE-NAD-001" }).click();
  await expect(page.getByRole("heading", { name: "FIXTURE-NAD-001", level: 1 })).toBeVisible();
  await expect(page.getByText("Cotton shirt", { exact: true })).toBeVisible();
});

test("says so when a case doesn't exist", async ({ page }) => {
  await page.goto("/cases/FIXTURE-NOPE-999");
  // The backend answers an unknown id with a 500, which the app retries before giving up.
  await expect(page.getByText("No case FIXTURE-NOPE-999")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("link", { name: "Back to cases" }).click();
  await expect(page.getByRole("heading", { name: "Cases", level: 1 })).toBeVisible();
});
