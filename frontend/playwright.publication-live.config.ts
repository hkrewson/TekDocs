import { readFileSync } from 'node:fs'
import { defineConfig, devices } from '@playwright/test'

const budget = JSON.parse(readFileSync(new URL('./publication-browser-budget.json', import.meta.url), 'utf8')) as { test_timeout_ms: number; suite_timeout_ms: number }

export default defineConfig({
  testDir: './e2e', testMatch: 'publication.live.ts', fullyParallel: false, retries: 0,
  workers: 1, timeout: budget.test_timeout_ms, globalTimeout: budget.suite_timeout_ms, reporter: [['list'], ['./safe-summary-reporter.ts']],
  outputDir: '/tmp/tekdocs-publication-live-results',
  use: { baseURL: 'http://localhost:8080', trace: 'off', screenshot: 'off', video: 'off' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
