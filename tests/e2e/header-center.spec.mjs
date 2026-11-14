// Regression for PR #26: the header must have ONE vertical centre line.
// This intentionally checks computed browser geometry instead of CSS tokens.
// The standard E2E server seeds an isolated library; real user jobs are untouched.
import { test, expect } from "@playwright/test";

test("desktop header: extraction, title, view tabs and playback share one vertical centre", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 900 });
  await page.goto("/");
  await expect(page.locator("#app.header-v3")).toBeVisible();
  await expect(page.locator("#nowPlayingPanel .studio-mode-tabs")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);

  const geometry = await page.evaluate(() => {
    const selectors = {
      topbar: ".daw-topbar",
      row: "#job-form.header-compact",
      import: "#importLayoutToggle",
      reextract: "#reextractCurrentTrack",
      player: "#nowPlayingPanel",
      titleGroup: "#nowPlayingPanel .track-panel-head",
      title: "#nowPlayingPanel .track-panel-title",
      controls: "#nowPlayingPanel .song-controls",
      views: "#nowPlayingPanel .studio-mode-tabs",
      stop: "#t-stop",
      play: "#t-play",
      speed: "#nowPlayingPanel .footer-group-speed",
      key: "#nowPlayingPanel .footer-group-key",
      metronome: "#nowPlayingPanel .footer-group-click",
      position: "#nowPlayingPanel .footer-group-position",
      export: "#t-export-btn",
    };
    const boxes = {};
    for (const [name, selector] of Object.entries(selectors)) {
      const node = document.querySelector(selector);
      if (!node) { boxes[name] = null; continue; }
      const rect = node.getBoundingClientRect();
      const css = getComputedStyle(node);
      boxes[name] = {
        top: rect.top, bottom: rect.bottom, height: rect.height,
        center: rect.top + rect.height / 2,
        display: css.display, gridRows: css.gridTemplateRows,
      };
    }
    const card = document.querySelector("#nowPlayingPanel");
    const divider = document.querySelector("#nowPlayingPanel > .song-controls");
    return {
      boxes, viewport: window.innerWidth,
      cardRows: card ? getComputedStyle(card).gridTemplateRows : "",
      dividerHeight: divider ? getComputedStyle(divider, "::before").height : "",
    };
  });

  // Visible failures show actual pixel centres, not just "toBeCloseTo".
  const baseline = geometry.boxes.row?.center;
  expect(baseline, JSON.stringify(geometry, null, 2)).toBeDefined();
  const parts = [
    "import", "reextract", "player", "titleGroup", "title",
    "controls", "views", "stop", "play", "speed", "key",
    "metronome", "position", "export",
  ];
  const offsets = {};
  for (const key of parts) {
    const rect = geometry.boxes[key];
    expect(rect, "Missing header element: " + key).not.toBeNull();
    offsets[key] = Number((rect.center - baseline).toFixed(2));
  }
  console.log("HEADER_CENTRE_OFFSETS_PX " + JSON.stringify(offsets));
  console.log("HEADER_CARD_GRID_ROWS " + geometry.cardRows);

  for (const [key, offset] of Object.entries(offsets)) {
    expect(Math.abs(offset), key + ": offset " + offset + "px").toBeLessThanOrEqual(1.5);
  }
  expect(geometry.boxes.player.height).toBeCloseTo(40, 0);
  expect(geometry.boxes.titleGroup.height).toBeCloseTo(38, 0);
  expect(geometry.boxes.controls.height).toBeCloseTo(38, 0);
  expect(geometry.dividerHeight).toBe("24px");
});
