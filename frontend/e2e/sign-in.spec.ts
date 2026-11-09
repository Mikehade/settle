import { SELLER } from "./support/env";
import { expect, test } from "./support/test";

test.use({ seller: null });

test("signs in and returns to the page asked for, then signs out", async ({ page }) => {
  await page.goto("/audit");
  await expect(page).toHaveURL(/\/login\?redirect=%2Faudit/);
  await expect(page.getByRole("heading", { name: "Sign in", level: 1 })).toBeVisible();

  await page.getByLabel("Email").fill(SELLER.email);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("That email and password don't match")).toBeVisible();

  await page.getByLabel("Password", { exact: true }).fill(SELLER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/audit$/);
  await expect(page.getByRole("heading", { name: "Audit trail", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: new RegExp(SELLER.full_name) }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  // Signed out means signed out: the app's pages send you back to sign in.
  await page.goto("/cases");
  await expect(page).toHaveURL(/\/login\?redirect=%2Fcases/);
});
