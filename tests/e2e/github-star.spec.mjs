import { test, expect } from "@playwright/test";
import { seedLibrary, stubUpdateCheck } from "./helpers.mjs";

test("GitHub Star replaces We Recommend with an external repository link", async ({ page }) => {
  await seedLibrary(page);
  await stubUpdateCheck(page);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const link = page.locator("#githubStarBtn");
  await expect(link).toBeVisible();
  await expect(link).toHaveText("Star");
  await expect(link).toHaveAttribute("href", "https://github.com/nelsonseccofilho/N3LX_Stem");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  await expect(link).toHaveAccessibleName(/GitHub/);
  await expect(page.locator("#friendsBtn, #friendsDialog")).toHaveCount(0);
});
