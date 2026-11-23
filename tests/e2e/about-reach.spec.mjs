// About this song can be opened at any window width (#735).
//
// Its button lived only on the Now Playing card, and daw.css hid that whole
// card below 1460 px, so a maximised laptop window had no way to open it. The
// card now gives way in steps instead: the artwork and the meta line go first,
// then the title, and the heart and the About button stay.

import { test, expect } from "@playwright/test";
import { openStudio } from "./helpers.mjs";

for (const width of [1024, 1280, 1366, 1600]) {
  test(`About this song opens from the card at ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await openStudio(page);
    const button = page.locator("#np-details-btn");
    await expect(button).toBeVisible();
    await expect(page.locator("#fav-btn")).toBeVisible();
    // On screen and inside the bar, not pushed past its edge.
    const box = await button.boundingBox();
    const bar = await page.locator(".daw-composer").boundingBox();
    expect(box.width).toBeGreaterThan(20);
    expect(box.x + box.width).toBeLessThanOrEqual(bar.x + bar.width + 0.5);
    await button.click();
    await expect(page.locator("#artistDialog")).toBeVisible();
  });
}

test("New extraction displays Detect structure and Extract stems side by side; chips stay on one line", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 800 });
  await openStudio(page);

  // The import workspace is intentionally collapsed while a song is open.
  // The previous test measured its hidden buttons and got null bounding boxes.
  const workspace = page.locator("#headerImportWorkspace");
  const openImport = page.locator("#importLayoutLabel");
  await expect(workspace).toBeHidden();
  await expect(openImport).toBeVisible();
  await openImport.click();
  await expect(page.locator("#importLayoutToggle")).toBeChecked();
  await expect(workspace).toBeVisible();

  const detect = workspace.locator("#autoSectionsBtn");
  const extract = workspace.locator("#submit");
  await expect(detect).toBeVisible();
  await expect(extract).toBeVisible();
  await expect(extract).toHaveText(/Extract stems/);

  const detectBox = await detect.boundingBox();
  const extractBox = await extract.boundingBox();
  expect(detectBox).not.toBeNull();
  expect(extractBox).not.toBeNull();
  // Current UI: both actions occupy row 3 of the import workspace grid.
  expect(Math.abs(detectBox.y - extractBox.y)).toBeLessThan(1);
  expect(extractBox.x).toBeGreaterThan(detectBox.x + detectBox.width - 1);
  await expect(workspace.locator("#stemChips")).toHaveCSS("flex-wrap", "nowrap");
});
