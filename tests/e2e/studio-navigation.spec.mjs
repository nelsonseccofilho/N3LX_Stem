import { test, expect } from "@playwright/test";
import { seedLibrary, stubUpdateCheck } from "./helpers.mjs";

test("Studio navigation keeps music collections accessible", async ({ page }) => {
  await seedLibrary(page);
  await stubUpdateCheck(page);
  await page.goto("/");
  for (const selector of [".rail-favorites", ".rail-setlist", ".rail-trash", "#catalogSearch"]) {
    await expect(page.locator(selector)).toBeVisible();
  }
  await expect(page.locator("#githubStarBtn")).toHaveCount(0);
  await page.locator("#settingsBtn").click();
  await page.locator('.settings-tab[data-tab="storage"]').click();
  await expect(page.locator("#storageStemsPath")).toBeVisible();
  await expect(page.locator("#storageExportsChange, #storageStemsChange")).toHaveCount(0);
});
