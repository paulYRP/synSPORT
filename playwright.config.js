import { defineConfig, devices } from '@playwright/test';

const liveURL = process.env.LIVE_URL;
const baseURL = liveURL
  ? liveURL.replace(/\/?$/, '/')
  : 'http://127.0.0.1:4173/synSPORT/';

export default defineConfig({
  testDir: './tests',
  testMatch: liveURL ? '**/live.spec.js' : '**/site.spec.js',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  timeout: 45_000,
  expect: { timeout: 12_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 15_000,
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
    { name: 'reduced-motion', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 }, reducedMotion: 'reduce' } },
  ],
  webServer: liveURL ? undefined : {
    command: 'npm run preview',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
