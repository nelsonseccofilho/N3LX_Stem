import { test, expect } from "@playwright/test";
import { seedLibrary, stubUpdateCheck } from "./helpers.mjs";

test("GitHub Star replaces We Recommend with an external repository link", async ({ page }) => {
  await seedLibrary(page);
  await stubUpdateCheck(page);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const links = page.locator(".github-star-shortcut");
  await expect(links).toHaveCount(2);
  for (const link of await links.all()) {
  await expect(link).toBeVisible();
  await expect(link).toHaveText(/Star|Give a star/i);
  await expect(link).toHaveAttribute("href", "https://github.com/nelsonseccofilho/N3LX_Stem");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  await expect(link).toHaveAccessibleName(/GitHub/);
  }
  await expect(page.locator("#friendsBtn, #friendsDialog, .rail-github")).toHaveCount(0);
});
