// Playwright drives the real Electron development window against synthetic data.
import { createRequire } from 'node:module';
import { existsSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import assert from 'node:assert/strict';

const root = process.env.C32_ROOT;
const runtime = process.env.C32_RUNTIME;
const report = process.env.C32_REPORT;
const port = Number(process.env.C32_PORT);
if (!root || !runtime || !report || !Number.isInteger(port) || port === 8159 || port === 8162)
  throw new Error('Missing isolated QA parameters or reserved port');
for (const name of ['main.cjs', 'preload.cjs'])
  assert.ok(existsSync(join(report, 'shell/desktop-app', name)), 'Missing QA shell ' + name);
const { _electron: electron } = createRequire(join(runtime, 'package.json'))('playwright');
const executablePath = join(runtime, 'desktop-app/node_modules/electron/dist/electron.exe');
assert.ok(existsSync(executablePath), 'Electron executable is missing');
let app, page, failure;
const results = [];
const errors = [];
try {
  const cleanEnv = Object.fromEntries(Object.entries(process.env).filter(([name]) =>
    !name.startsWith('STEMDECK_') && !name.startsWith('N3LX_') && !name.startsWith('C32_')));
  app = await electron.launch({
    executablePath,
    args: [join(report, 'shell/desktop-app'), '--port=' + port],
    cwd: root,
    timeout: 45000,
    env: {
      ...cleanEnv,
      N3LX_STEM_RUNTIME_DIR: runtime,
      N3LX_STEM_DATA_DIR: join(report, 'data'),
      N3LX_STEM_PROFILE_DIR: join(report, 'profile'),
    },
  });
  page = await app.firstWindow();
  page.on('pageerror', error => errors.push(String(error)));
  await page.route('**/*', route => {
    const req = route.request();
    const url = new URL(req.url());
    if (!['http:', 'https:'].includes(url.protocol)) return route.continue();
    if (url.hostname !== '127.0.0.1' || Number(url.port) !== port) return route.abort();
    if (!['GET', 'HEAD'].includes(req.method()) &&
      /\/karaoke\/generate|\/lyrics\/retime|\/guitar-detail|\/api\/jobs\/?$/.test(url.pathname))
      return route.abort();
    return route.continue();
  });
  const track = page.locator('.cat-item[data-id="e2e0cafebabe"]');
  await track.waitFor({ timeout: 30000 });
  await track.dblclick();
  for (const [width, height] of [[1920,1080],[1440,900],[1366,786]]) {
    // Renderer viewports; NOT physical window resizes or installed-package QA.
    await page.setViewportSize({ width, height });
    const metrics = await page.evaluate(() => {
      const bar = document.querySelector('.daw-topbar');
      const play = document.querySelector('#t-play');
      return {
        width: innerWidth, height: innerHeight,
        overflow: document.documentElement.scrollWidth - innerWidth,
        playVisible: Boolean(play && play.getBoundingClientRect().width > 0),
        headerHeight: bar?.getBoundingClientRect().height ?? 0,
      };
    });
    assert.equal(metrics.width, width);
    assert.equal(metrics.height, height);
    assert.ok(metrics.overflow <= 1, 'Horizontal overflow at ' + width);
    assert.ok(metrics.playVisible && metrics.headerHeight > 0);
    await page.screenshot({ path: join(report, 'studio-' + width + 'x' + height + '.png') });
    await page.locator('#studioKaraokeTab').click();
    await page.locator('#lyricsSettingsOpen').click();
    await page.locator('#karaokeSettings').waitFor({ state: 'visible' });
    await page.locator('#karaokeTab-generate').click();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#karaokeTab-search').getAttribute('aria-selected'), 'true');
    await page.screenshot({ path: join(report, 'karaoke-' + width + 'x' + height + '.png') });
    await page.locator('#lyricsSettingsClose').click();
    results.push({ resolution: width + 'x' + height, ...metrics, result: 'PASS' });
    console.log('PASS Electron renderer ' + width + 'x' + height);
  }
  assert.deepEqual(errors, []);
} catch (error) {
  failure = String(error.stack || error);
  console.error(failure);
  if (page) await page.screenshot({ path: join(report, 'failure.png') }).catch(() => {});
} finally {
  if (page && !page.isClosed()) {
    try {
      // The Studio owns a persistent /api/queue/events SSE connection.
      // Explicitly close it before Electron exits so it cannot block
      // backend_control.py's safe in-flight request gate during QA teardown.
      await page.evaluate(async () => {
        const { stopQueueStream } = await import('/js/queue.js');
        stopQueueStream();
      });
    } catch (error) {
      failure ||= 'Queue SSE could not be closed cooperatively: ' + String(error);
    }
  }
  if (app) {
    try { await app.close(); }
    catch (error) { failure ||= 'Electron close failed: ' + String(error); }
  }
  writeFileSync(join(report, 'electron-qa.json'), JSON.stringify({
    revision: process.env.C32_REVISION,
    execution: 'Electron development renderer, not installed Windows package',
    viewport: 'emulated renderer size',
    library: 'synthetic', passed: !failure, results, errors,
    ...(failure ? { failure } : {}),
  }, null, 2));
}
if (failure) process.exitCode = 1;
