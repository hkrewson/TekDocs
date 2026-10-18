import { EventEmitter } from 'node:events'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { CDPSession, Page } from '@playwright/test'
import { afterEach, expect, test, vi } from 'vitest'
import { performanceDiagnostics } from '../../e2e/performance-diagnostics'

let directory: string | undefined
afterEach(() => {
  vi.unstubAllEnvs()
  if (directory) rmSync(directory, { recursive: true, force: true })
  directory = undefined
})

function fixture(crashed: boolean | 'hung' = false) {
  directory = mkdtempSync(join(tmpdir(), 'tekdocs-performance-diagnostics-'))
  vi.stubEnv('TEKDOCS_PERFORMANCE_DIAGNOSTICS', directory)
  const page = Object.assign(new EventEmitter(), {
    evaluate: vi.fn(() => crashed === 'hung' ? new Promise<never>(() => undefined) : crashed ? Promise.reject(new Error('synthetic private error'))
      : Promise.resolve({ hostCount: 1, editableCount: 0 })),
  })
  const session = { send: vi.fn(() => crashed === 'hung' ? new Promise<never>(() => undefined) : crashed ? Promise.reject(new Error('synthetic private error'))
    : Promise.resolve({ metrics: [{ name: 'TaskDuration', value: 2 }, { name: 'unapproved', value: 42 }] })) }
  return { page, diagnostics: performanceDiagnostics(page as unknown as Page, session as unknown as CDPSession) }
}

test('retains phase and failed-download evidence without URL or error payloads', async () => {
  const { page, diagnostics } = fixture()
  const request = { resourceType: () => 'script', url: () => 'https://example.invalid/EditorSpike-build.js?private=sentinel' }
  diagnostics.phase('edit-clicked')
  page.emit('request', request)
  page.emit('requestfailed', request)
  page.emit('pageerror', new Error('synthetic private error'))
  page.emit('console', { type: () => 'error', text: () => 'synthetic private error' })
  await diagnostics.save('legacy', 390)
  const raw = readFileSync(join(directory!, 'legacy-390-0.json'), 'utf8')
  const report: unknown = JSON.parse(raw)
  expect(report).toMatchObject({ pendingScripts: 0, failedRequests: 1, pageErrors: 1, consoleErrors: 1,
    editorState: { hostCount: 1, editableCount: 0 }, browserMetrics: [{ name: 'TaskDuration', value: 2 }] })
  expect(report).toMatchObject({ phases: [{ name: 'edit-clicked' }], scripts: [{ editor: true, failed: true }] })
  expect(raw).not.toMatch(/sentinel|example.invalid|synthetic private|unapproved/)
  await diagnostics.save('legacy', 390, 1)
  expect(readFileSync(join(directory!, 'legacy-390-0.json'), 'utf8')).toBe(raw)
  expect(JSON.parse(readFileSync(join(directory!, 'legacy-390-1.json'), 'utf8'))).toMatchObject({ repetition: 1 })
})

test('retains pending-request counts even when the browser can no longer answer', async () => {
  const { page, diagnostics } = fixture(true)
  page.emit('request', { resourceType: () => 'script' })
  await diagnostics.save('legacy', 390)
  expect(JSON.parse(readFileSync(join(directory!, 'legacy-390-0.json'), 'utf8'))).toMatchObject({
    pendingScripts: 1, browserMetrics: null, editorState: null,
  })
})


test('writes diagnostics when both browser probes hang', async () => {
  const { diagnostics } = fixture('hung')
  await diagnostics.save('legacy', 390)
  expect(JSON.parse(readFileSync(join(directory!, 'legacy-390-0.json'), 'utf8'))).toMatchObject({
    browserMetrics: null, editorState: null,
  })
})
