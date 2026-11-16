import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'qa.spec.mjs', workers: 1, retries: 0,
  timeout: 60000, reporter: [['list']], outputDir: '../../test-results/c278',
  use: {baseURL: 'http://127.0.0.1:8160', channel: 'msedge', actionTimeout:10000, locale:'pt-BR',
    viewport: {width:1920,height:1080}, deviceScaleFactor:1,
    screenshot:'only-on-failure', trace:'retain-on-failure'},
});
