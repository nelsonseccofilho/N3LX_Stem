import { defineConfig } from '@playwright/test';
// Start a disposable seed.py library on 8161 before running this config.
export default defineConfig({
  testDir: './c278', testMatch: 'qa.spec.mjs', workers: 1, retries: 0,
  timeout: 60000, reporter: [['list']], outputDir: '../test-results/c28-workflows',
  use: { baseURL: 'http://127.0.0.1:8161', channel: 'msedge', headless: true,
    actionTimeout: 10000, locale: 'pt-BR', deviceScaleFactor: 1,
    screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  projects: [[1920, 1080], [1440, 900], [1366, 786]].map(([width, height]) => ({
    name: `${width}x${height}`, use: { viewport: { width, height } },
  })),
});
