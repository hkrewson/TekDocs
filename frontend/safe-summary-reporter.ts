import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'

import type { FullResult, Reporter, TestCase, TestResult } from '@playwright/test/reporter'

type SafeResult = {
  project: string
  title: string
  status: string
  duration_ms: number
  retry: number
}

export default class SafeSummaryReporter implements Reporter {
  private readonly tests: SafeResult[] = []

  onTestEnd(test: TestCase, result: TestResult) {
    this.tests.push({
      project: test.parent.project()?.name ?? 'unknown',
      title: test.titlePath().slice(1).join(' › '),
      status: result.status,
      duration_ms: result.duration,
      retry: result.retry,
    })
  }

  onEnd(result: FullResult) {
    const output = process.env.PLAYWRIGHT_SAFE_SUMMARY
    if (!output) return
    mkdirSync(dirname(output), { recursive: true })
    writeFileSync(output, `${JSON.stringify({ schema_version: 1, status: result.status, tests: this.tests }, null, 2)}\n`, { mode: 0o600 })
  }
}
