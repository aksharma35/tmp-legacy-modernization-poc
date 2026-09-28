// @ts-check
// One browser suite, three targets. The tests only use what a user can see
// (labels, roles, text), so the same file runs against AngularJS and React.
const { defineConfig } = require('@playwright/test');
const path = require('path');

const targets = {
  legacy: process.env.LEGACY_WEB_URL || 'http://localhost:5001',
  modern: process.env.MODERN_WEB_URL || 'http://localhost:5173',
  hybrid: process.env.HYBRID_WEB_URL || 'http://localhost:8081',
};

module.exports = defineConfig({
  testDir: './tests',
  // All tests share one backend, so run them one at a time.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 20_000,
  expect: { timeout: 5_000 },
  reporter: [
    ['list'],
    ['json', { outputFile: process.env.PARITY_E2E_JSON || path.join(__dirname, '../../out/parity/e2e-results.json') }],
  ],
  use: {
    browserName: 'chromium',
    // A US time zone on purpose: date handling bugs show up west of UTC.
    timezoneId: 'America/Los_Angeles',
    locale: 'en-US',
    trace: 'retain-on-failure',
  },
  projects: Object.entries(targets).map(([name, baseURL]) => ({ name, use: { baseURL } })),
});
