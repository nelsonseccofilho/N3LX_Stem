import { test, expect } from "@playwright/test";

test("Studio header keeps its controls inside the toolbar as the window resizes", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  const track = page.locator('.cat-item[data-id="e2e0cafebabe"]');
  await expect(track).toBeVisible();

  for (const selected of [false, true]) {
    if (selected) await track.dblclick();
    for (const [width, height] of [[1920,1080], [1440,900], [1399,900], [1366,786], [1190,960], [735,960], [1920,1080]]) {
      await test.step(`${width}×${height}, track selected: ${selected}`, async () => {
        await page.setViewportSize({ width, height });
        const toolbar = page.locator(".daw-topbar");
        await expect(toolbar.locator("#t-play")).toBeVisible();
        await expect.poll(() => toolbar.evaluate(bar => {
          const top = bar.getBoundingClientRect().top;
          const bottom = document.querySelector(".daw-body").getBoundingClientRect().top;
          return [...bar.querySelectorAll("#nowPlayingPanel button, #nowPlayingPanel input, #importLayoutToggle")]
            .filter(el => el.offsetWidth && el.offsetHeight && getComputedStyle(el).visibility !== "hidden")
            .filter(el => {
              const box = el.getBoundingClientRect();
              return box.top < top - 1 || box.bottom > bottom + 1 || box.left < -1 || box.right > innerWidth + 1;
            }).map(el => el.id || el.className);
        })).toEqual([]);
        if (width === 1920) await expect(toolbar).toHaveCSS("height", "54px");
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      });
    }
  }
});
