// Structure detection is a persistent, enabled-by-default import preference.
import { test, expect } from "@playwright/test";
import { seedLibrary, stubExportEndpoints, stubUpdateCheck, JOB_ID } from "./helpers.mjs";
const button = page => page.locator("#autoSectionsBtn");
const setting = page => page.evaluate(() => fetch("/api/settings", {cache:"no-store"}).then(r=>r.json()).then(d=>d.auto_sections));
async function choose(page, value) {
  await page.evaluate(on => fetch("/api/settings", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({auto_sections:on})}), value);
}
async function setup(page) {
  await seedLibrary(page); await stubExportEndpoints(page); await stubUpdateCheck(page);
  await page.goto("/", {waitUntil:"domcontentloaded"});
}
async function expand(page) {
  if (!await button(page).isVisible()) await page.locator("#importLayoutToggle").click();
}
test("the saved setting survives reload and opening a song", async ({page}) => {
  await setup(page); await choose(page,true); await page.reload({waitUntil:"domcontentloaded"});
  await expect(button(page)).toHaveAttribute("aria-pressed","true");
  await page.locator(`.cat-item[data-id="${JOB_ID}"]`).first().click(); await expand(page);
  await expect(button(page)).toHaveAttribute("aria-pressed","true");
  expect(await setting(page)).toBe(true);
  await button(page).click(); await expect.poll(()=>setting(page)).toBe(false);
  await page.reload({waitUntil:"domcontentloaded"});
  await expect(button(page)).toHaveAttribute("aria-pressed","false");
});
test("detecting structure is independent from showing its timeline", async ({page}) => {
  await setup(page); await choose(page,true); await page.reload({waitUntil:"domcontentloaded"});
  const ribbon=page.locator(".timeline-sections"), toggle=page.locator('.daw-panel-toggle[data-panel="sections"]');
  await expect(ribbon).toBeVisible();
  await button(page).click(); await expect(button(page)).toHaveAttribute("aria-pressed","false");
  await expect(ribbon).toBeVisible();
  await toggle.click(); await expect(ribbon).toBeHidden();
  await toggle.click(); await expect(ribbon).toBeVisible();
});
test("the label describes import detection without an experimental badge", async ({page}) => {
  await setup(page);
  await expect(button(page)).toContainText(/detect/i);
  await expect(button(page)).toHaveAttribute("aria-label",/import/i);
  await expect(button(page)).toHaveAttribute("title",/next import/i);
  await expect(button(page)).not.toContainText(/experimental/i);
  await expect(button(page)).not.toHaveAttribute("aria-label",/experimental/i);
});
