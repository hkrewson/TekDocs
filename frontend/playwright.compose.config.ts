import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testIgnore: ['live-workspace.spec.ts', 'responsive.spec.ts'],
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['./safe-summary-reporter.ts']],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? '/tmp/tekdocs-playwright-results',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chromium', testMatch: 'responsive.spec.ts', testIgnore: 'live-workspace.spec.ts', use: { ...devices['Pixel 7'] } },
    { name: 'mobile-webkit', testMatch: 'responsive.spec.ts', testIgnore: 'live-workspace.spec.ts', use: { ...devices['iPhone 15'] } },
  ],
})
