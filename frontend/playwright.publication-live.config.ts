import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e', testMatch: 'publication.live.ts', fullyParallel: false, retries: 0,
  timeout: 120_000, reporter: [['list'], ['./safe-summary-reporter.ts']],
  outputDir: '/tmp/tekdocs-publication-live-results',
  use: { baseURL: 'http://localhost:8080', trace: 'off', screenshot: 'off', video: 'off' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
