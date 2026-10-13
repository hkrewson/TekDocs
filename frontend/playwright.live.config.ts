import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'live-workspace.spec.ts',
  fullyParallel: false,
  retries: 0,
  reporter: [['list'], ['./safe-summary-reporter.ts']],
  outputDir: '/tmp/tekdocs-playwright-live-results',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
