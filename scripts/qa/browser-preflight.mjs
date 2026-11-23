// Preflight the actual browser executable on Windows before any E2E workers.
// Prefer Playwright's own Chromium; fall back to an existing Edge/Chrome.
// Never installs, downloads, adopts an existing browser session or uses user data.
import { createRequire } from 'node:module';
import { join } from 'node:path';

const runtime = process.env.N3LX_RELEASE_TEST_RUNTIME;
if (!runtime) throw new Error('BLOCKED: existing Playwright runtime required');
const require = createRequire(join(runtime, 'package.json'));
const { chromium } = require('@playwright/test');

const choices = [
  { label: 'playwright-chromium', channel: null },
  { label: 'Microsoft Edge', channel: 'msedge' },
  { label: 'Google Chrome', channel: 'chrome' },
];
const failed = [];
let found;

for (const choice of choices) {
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      timeout: 15000,
      ...(choice.channel ? {channel: choice.channel} : {}),
    });
    const page = await browser.newPage();
    await page.goto('data:text/html,<title>QA browser preflight</title>', {timeout: 5000});
    if (await page.title() !== 'QA browser preflight') {
      throw new Error('Local data-page smoke check did not pass');
    }
    found = {
      status: 'PASS',
      browser: choice.label,
      channel: choice.channel,
      version: browser.version(),
      qa_only: true,
    };
    console.log(JSON.stringify(found));
    break;
  } catch (error) {
    const cause = String(error?.message || error).split('\n')[0];
    failed.push(choice.label + ': ' + cause);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}
if (!found) {
  console.error('BLOCKED: no supported browser launches for isolated Playwright QA');
  for (const error of failed) console.error('  ' + error);
  process.exitCode = 2;
}
