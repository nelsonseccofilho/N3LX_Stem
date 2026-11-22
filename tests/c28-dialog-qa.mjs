// Real Edge + real backend. Only run against the disposable E2E fixture library.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
const base = process.env.C28_BASE_URL || 'http://127.0.0.1:8161';
const out = process.env.C28_EVIDENCE || 'test-results/c28';
const phase = process.env.C28_PHASE || 'pilot';
const jobs = await fetch(base + '/api/jobs').then(r => r.json());
assert.deepEqual(jobs.map(j => j.job_id).sort(), ['e2e0cafebabe', 'e2e0deadbeef']);
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const results = [];
function contrast(a, b) {
  const luminance = value => value.match(/[\d.]+/g).slice(0, 3).map(Number).map(c => {
    c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
  const x = luminance(a), y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
try {
  for (const [width, height] of [[1920, 1080], [1440, 900], [1366, 786]]) {
    for (const theme of ['dark', 'light']) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [], generation = [];
      page.on('pageerror', e => errors.push(String(e)));
      await page.route('**/*', route => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin !== base) return route.abort();
        if (phase === 'baseline' && url.pathname === '/css/karaoke-settings.css') return route.fulfill({ contentType: 'text/css', body: '' });
        if (request.method() === 'POST' && /\/karaoke\/generate|\/lyrics\/retime|\/guitar-detail/.test(url.pathname)) {
          generation.push(url.pathname); return route.abort();
        }
        if (url.pathname.endsWith('/lyrics/lookup')) return route.fulfill({ json: { others: Array.from({ length: 15 }, (_, i) => ({
          source: 'lrclib', lrclib_id: 100 + i, track: 'QA Song ' + i, artist: 'QA Band', album: 'Studio', duration: 2,
          synced: '[00:00.20] Test first line\n[00:01.20] Test second line', plain: 'Test first line\nTest second line',
        })) } });
        return route.continue();
      });
      await page.goto(base + '/');
      await page.locator('.cat-item[data-id="e2e0cafebabe"]').dblclick();
      await page.locator('#studioKaraokeTab').click();
      await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
      await page.locator('#lyricsSettingsOpen').click();
      await page.locator('#karaokeTab-generate').waitFor({ state: 'visible' });
      const snapshots = [];
      for (const tab of ['generate', 'search', 'sync']) {
        await page.locator('#karaokeTab-' + tab).click();
        assert.equal(await page.locator('#karaokeTab-' + tab).getAttribute('aria-selected'), 'true');
        assert.equal(await page.locator('#karaokePanel-' + tab).isVisible(), true);
        const geometry = await page.locator('#karaokeSettings').evaluate(dialog => {
          const r = dialog.getBoundingClientRect();
          return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height,
            scrollWidth: dialog.scrollWidth, clientWidth: dialog.clientWidth,
            documentOverflow: document.documentElement.scrollWidth - innerWidth,
            fg: getComputedStyle(dialog).color, bg: getComputedStyle(dialog).backgroundColor };
        });
        assert.ok(geometry.x >= 0 && geometry.y >= 0 && geometry.right <= width && geometry.bottom <= height, JSON.stringify(geometry));
        assert.equal(geometry.documentOverflow, 0);
        assert.ok(geometry.scrollWidth <= geometry.clientWidth + 1);
        await page.screenshot({ path: `${out}/${phase}-${width}-${theme}-${tab}.png` });
        snapshots.push({ tab, ...geometry });
      }
      const colors = await page.locator('#karaokeSettings').evaluate(dialog => {
        const bg = getComputedStyle(dialog).backgroundColor;
        return [...dialog.querySelectorAll('h2, .lyrics-note, .karaoke-tab, input:not([type="hidden"]), select')]
          .filter(el => el.getBoundingClientRect().height > 0 && !el.disabled).map(el => {
            const css = getComputedStyle(el); let background = css.backgroundColor, parent = el.parentElement;
            while (background === 'rgba(0, 0, 0, 0)' && parent) {
              background = getComputedStyle(parent).backgroundColor; parent = parent.parentElement;
            }
            return { id: el.id || el.className, fg: css.color, bg: background, dialogBg: bg };
          });
      });
      if (phase !== 'baseline') for (const color of colors) {
        assert.ok(contrast(color.fg, color.bg) >= 4.5, JSON.stringify(color));
      }
      await page.locator('#karaokeTab-generate').click();
      await page.keyboard.press('ArrowRight');
      assert.equal(await page.locator('#karaokeTab-search').getAttribute('aria-selected'), 'true');
      if (phase !== 'baseline') {
        assert.equal(await page.locator('#karaokeTab-search').evaluate(el => el === document.activeElement), true);
        const focus = await page.locator('#karaokeTab-search').evaluate(el => {
          const css = getComputedStyle(el);
          return { width: css.outlineWidth, color: css.outlineColor, bg: getComputedStyle(el.parentElement).backgroundColor };
        });
        assert.equal(focus.width, '2px'); assert.ok(contrast(focus.color, focus.bg) >= 3);
        await page.screenshot({ path: `${out}/${phase}-${width}-${theme}-keyboard-focus.png` });
        const selectors = await page.evaluate(() => [...[...document.styleSheets].find(s => s.href?.endsWith('/css/karaoke-settings.css')).cssRules]
          .map(rule => rule.selectorText));
        assert.ok(selectors.length > 0 && selectors.every(s => s?.startsWith('#karaokeSettings.sd-dialog')));
      }
      await page.locator('#karaokeTab-sync').focus();
      await page.keyboard.press('Home');
      assert.equal(await page.locator('#karaokeTab-generate').evaluate(el => el === document.activeElement), true);
      await page.keyboard.press('End');
      assert.equal(await page.locator('#karaokeTab-sync').evaluate(el => el === document.activeElement), true);
      // Native modal focus confinement in both directions.
      for (const key of ['Tab', 'Shift+Tab']) for (let i = 0; i < 14; i++) {
        await page.keyboard.press(key);
        const focus = await page.locator('#karaokeSettings').evaluate(el => ({ inside: el.contains(document.activeElement), documentFocused: document.hasFocus(), active: document.activeElement?.outerHTML.slice(0,250) }));
        assert.ok(focus.inside || !focus.documentFocused, JSON.stringify({ key, i, focus }));
      }
      await page.locator('#karaokeTab-search').click();
      await page.locator('#lyricsSearchArtist').fill('QA Band');
      await page.locator('#lyricsSearchTitle').fill('QA Song');
      await page.locator('#lyricsSearchSubmitBtn').click();
      await page.locator('#lyricsSearchResults .lyrics-version').last().waitFor();
      await page.locator('#lyricsSearchResults .lyrics-version').last().click();
      assert.match(await page.locator('.karaoke-lookup-preview').innerText(), /Test first line/);
      await page.getByRole('button', { name: /Cancelar seleção|Cancel selection/, exact: true }).click();
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#karaokeSettings').isVisible(), false);
      assert.equal(await page.locator('#lyricsSettingsOpen').evaluate(el => el === document.activeElement), true);
      assert.deepEqual(generation, []); assert.deepEqual(errors, []);
      results.push({ width, height, theme, snapshots, colors: colors.map(c => ({ ...c, ratio: contrast(c.fg, c.bg) })), keyboard: 'PASS', generation, errors });
      await page.close();
    }
  }
  // Effective viewports at 125% / 150% of the minimum supported desktop.
  for (const zoom of [1.25, 1.5]) {
    const page = await browser.newPage({ viewport: { width: Math.floor(1366 / zoom), height: Math.floor(786 / zoom) } });
    await page.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await page.goto(base + '/');
    await page.locator('.cat-item[data-id="e2e0cafebabe"]').dblclick();
    await page.locator('#studioKaraokeTab').click(); await page.locator('#lyricsSettingsOpen').click();
    await page.locator('#karaokeTab-search').click();
    await page.locator('#lyricsSettingsClose').scrollIntoViewIfNeeded();
    assert.equal(await page.locator('#lyricsSettingsClose').isVisible(), true);
    await page.screenshot({ path: `${out}/${phase}-effective-${zoom}.png` });
    await page.locator('#lyricsSettingsClose').click();
    results.push({ zoom, effectiveViewport: page.viewportSize(), close: 'PASS' }); await page.close();
  }
  await writeFile(`${out}/results.json`, JSON.stringify(results, null, 2));
  console.log(`PASS ${phase}: 6 desktop/theme combinations, 18 tab states, 2 effective viewports; no generation.`);
} finally { await browser.close(); }
