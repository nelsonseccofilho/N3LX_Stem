import { test, expect } from "@playwright/test";

for (const [width, height] of [[1920, 1080], [1440, 900], [1366, 786]]) {
  test(`edit loop bounds from the transport at ${width}×${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await page.locator('.cat-item[data-id="e2e0cafebabe"]').dblclick();
    const options = page.locator("#song-loop-more");
    const end = page.locator("#t-loop-end");
    const start = page.locator("#t-loop-start");
    await options.click();
    await end.click();
    await end.fill("1.500");
    await start.click();
    await start.fill("0.500");
    await end.click();
    await expect(page.locator("#t-loop")).toHaveClass(/active/);
    await end.press("Escape");
    await expect(options).toBeFocused();
    await options.click();
    await expect(start).toHaveValue("00.500");
    await expect(end).toHaveValue("01.500");
  });
}
