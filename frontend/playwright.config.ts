import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testIgnore: ['live-workspace.spec.ts', 'responsive.spec.ts'],
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['./safe-summary-reporter.ts']],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? '../artifacts/playwright-results',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3200',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  webServer: {
    command: 'npm run dev -- --strictPort',
    url: 'http://localhost:3200',
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chromium', testMatch: 'responsive.spec.ts', testIgnore: 'live-workspace.spec.ts', use: { ...devices['Pixel 7'] } },
    { name: 'mobile-webkit', testMatch: 'responsive.spec.ts', testIgnore: 'live-workspace.spec.ts', use: { ...devices['iPhone 15'] } },
  ],
})
