import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { clearTimeout, setTimeout } from 'node:timers'
import type { CDPSession, Page, Request } from '@playwright/test'

async function boundedProbe<T>(operation: Promise<T>): Promise<T | null> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      operation.catch(() => null),
      new Promise<null>((resolve) => { timer = setTimeout(() => resolve(null), 1_000) }),
    ])
  } finally {
    clearTimeout(timer)
  }
}

// Only fixed labels, counters and timing values leave this synthetic rehearsal.
// Never retain URLs, console/error text, request bodies, headers or DOM content.
export function performanceDiagnostics(page: Page, session: CDPSession) {
  const started = Date.now()
  const phases: { name: string; elapsedMs: number }[] = []
  const pending = new Set<Request>()
  const scripts: { editor: boolean; elapsedMs: number; failed: boolean }[] = []
  let pageErrors = 0
  let consoleErrors = 0
  let failedRequests = 0
  let httpErrors = 0
  page.on('pageerror', () => { pageErrors++ })
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors++ })
  page.on('response', (response) => { if (response.status() >= 400) httpErrors++ })
  page.on('request', (request) => { if (request.resourceType() === 'script') pending.add(request) })
  const finish = (request: Request, failed: boolean) => {
    if (failed) failedRequests++
    if (pending.delete(request)) scripts.push({
      editor: new URL(request.url()).pathname.includes('EditorSpike-'),
      elapsedMs: Date.now() - started,
      failed,
    })
  }
  page.on('requestfinished', (request) => finish(request, false))
  page.on('requestfailed', (request) => finish(request, true))
  return {
    phase(name: 'shell-start' | 'shell-ready' | 'document-open' | 'edit-clicked' | 'editor-ready' | 'budgets-passed') {
      phases.push({ name, elapsedMs: Date.now() - started })
    },
    async save(editor: 'legacy' | 'repository', width: number, repetition = 0) {
      const directory = process.env.TEKDOCS_PERFORMANCE_DIAGNOSTICS
      if (!directory) return
      const metricNames = new Set(['TaskDuration', 'ScriptDuration', 'LayoutDuration', 'RecalcStyleDuration', 'JSHeapUsedSize'])
      const metrics = await boundedProbe(session.send('Performance.getMetrics'))
      const editorState = await boundedProbe(page.evaluate(() => ({
        hostCount: document.querySelectorAll('.milkdown-host').length,
        editableCount: document.querySelectorAll('.milkdown-host [contenteditable="true"]').length,
      })))
      mkdirSync(directory, { recursive: true })
      writeFileSync(join(directory, `${editor}-${width}-${repetition}.json`), `${JSON.stringify({
        schema_version: 1, editor, width, repetition, phases, scripts, elapsedMs: Date.now() - started,
        pendingScripts: pending.size, pageErrors, consoleErrors, failedRequests, httpErrors, editorState,
        browserMetrics: metrics?.metrics.filter((metric) => metricNames.has(metric.name)) ?? null,
      }, null, 2)}\n`, { mode: 0o600 })
    },
  }
}
