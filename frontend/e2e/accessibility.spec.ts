import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "./support/test";

/** Waits out entrance animations, so a sheet or dialog is checked as it ends up, not mid-fade. */
async function settle(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== "running"),
  );
}

/**
 * Checks the page as it stands against WCAG 2.1 A and AA, in light and dark mode, then at phone
 * width for anything that would make the page scroll sideways.
 */
async function checkPage(page: Page, ready: () => Promise<void>) {
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    await page.waitForFunction(
      (dark) => document.documentElement.classList.contains("dark") === dark,
      colorScheme === "dark",
    );
    await ready();
    await settle(page);
    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const found = violations.map(
      (violation) =>
        `${violation.id} (${violation.impact}): ${violation.help}\n` +
        violation.nodes
          .map((node) => `  ${node.target.join(" ")}: ${node.failureSummary ?? ""}`)
          .join("\n"),
    );
    expect(found, `${colorScheme} mode`).toEqual([]);
  }

  await page.setViewportSize({ width: 375, height: 812 });
  await ready();
  await settle(page);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "sideways scroll at phone width, in pixels").toBe(0);
}

/** Leaves the earbuds case waiting on the seller, so pages have a decision to show. */
async function escalateEarbuds(page: Page) {
  await page.goto("/cases/FIXTURE-NR-001");
  await page.getByRole("button", { name: "Mediate", exact: true }).click();
  await expect(page.getByRole("region", { name: "Decision" })).toContainText("Escalated to you");
}

test.describe("signed out", () => {
  test.use({ seller: null });

  test("the sign-in page", async ({ page }) => {
    await page.goto("/login");
    await checkPage(page, () =>
      expect(page.getByRole("button", { name: "Sign in" })).toBeVisible(),
    );
  });
});

test("the cases list", async ({ page }) => {
  await escalateEarbuds(page);
  await page.goto("/cases");
  await checkPage(page, () =>
    expect(page.getByRole("row", { name: /FIXTURE-NR-001/ })).toBeVisible(),
  );
});

test("a case waiting on the seller", async ({ page }) => {
  await escalateEarbuds(page);
  await page.reload();
  await checkPage(page, () => expect(page.getByRole("button", { name: "Approve" })).toBeVisible());
});

test("a case Settle hasn't mediated", async ({ page }) => {
  await page.goto("/cases/FIXTURE-NAD-001");
  await checkPage(page, () =>
    expect(page.getByRole("button", { name: "Mediate", exact: true })).toBeVisible(),
  );
});

test("the audit trail, with an entry open", async ({ page }) => {
  await escalateEarbuds(page);
  await page.goto("/audit");
  await page
    .getByRole("row", { name: /FIXTURE-NR-001/ })
    .getByRole("link")
    .click();
  await checkPage(page, () =>
    expect(page.getByRole("region", { name: "How Settle decided" })).toBeVisible(),
  );
});

test("the fairness policy", async ({ page }) => {
  await page.goto("/policy");
  await checkPage(page, () => expect(page.getByLabel("Your rules")).toBeVisible());
});
