import type { Page, Request, Response } from '@playwright/test'

type Options = { scenario?: string; now?: () => number; write?: (line: string) => void }
type Entry = { phase: string; at: number }
type Event = { event: string; phase: string; ms: number; status?: number; elapsed_ms?: number }
const scenarios = new Set(['client_publications', 'templates', 'history_templates', 'field_keys', 'content_keys', 'diagrams', 'monitored_sources'])
const milestones = new Set(['template', 'pdf_download', 'monitored', 'keyed'])
const visibleControls = ['navigationPrompt', 'createTemplate', 'useTemplate', 'pdfDownload'] as const

function requestPhase(request: Request) {
  let url: URL
  try { url = new URL(request.url()) } catch { return null }
  const path = url.pathname
  if (!path.startsWith('/api/v1/')) return null
  const method = request.method()
  if (path.endsWith('/from-template') && method === 'POST') return 'template_create'
  if (path.includes('/template-rollouts')) return 'template_rollout'
  if (path.includes('/observations/') && path.endsWith('/apply')) return 'source_apply'
  if (path.endsWith('/remote-source') && method === 'PUT') return 'source_settings'
  if (path.endsWith('/content-graph/authoring')) return 'git_write'
  if (/^\/api\/v1\/workspaces\/organizations\/[^/]+$/.test(path)) return 'workspace_read'
  if (path.startsWith('/api/v1/portal/documents')) return 'portal_read'
  if (path.includes('/publications/') && path.endsWith('/approve')) return 'publication_approve'
  if (path.includes('/publications/') && path.endsWith('/withdraw')) return 'publication_withdraw'
  if (path.endsWith('/publications') && method === 'POST') return 'publication_create'
  if (path.includes('/export') || path.includes('/artifacts/')) return url.searchParams.get('export_format') === 'pdf' ? 'download_pdf' : 'download_file'
  if (path.includes('template')) return 'template_read'
  if (method === 'GET') {
    if (/^\/api\/v1\/workspaces\/(?:msp|organizations\/[^/]+)\/content-graph\/documents\/[^/]+$/.test(path)) return 'git_document_read'
    if (/^\/api\/v1\/(?:workspaces\/organizations\/[^/]+\/)?documents$/.test(path)) return 'document_list'
    if (/^\/api\/v1\/(?:workspaces\/organizations\/[^/]+\/)?documents\/[^/]+$/.test(path)) return 'document_read'
  }
  return null
}

/** Failure-only diagnostics: at most 128 events/32 pending requests, with no URL,
 * identity, header, body, filename, dialog message or page-error text retained.
 * A request_failed followed by download is normal Chromium download hand-off.
 */
export function attachPublicationDiagnostics(page: Pick<Page, 'on' | 'off'>, options: Options = {}) {
  const now = options.now ?? (() => performance.now())
  const write = options.write ?? ((line: string) => console.info('Publication acceptance diagnostics:', line))
  const started = now()
  const scenario = options.scenario && scenarios.has(options.scenario) ? options.scenario : 'unknown'
  const pending = new Map<Request, Entry>()
  const events: Event[] = []
  let droppedEvents = 0
  let evictedRequests = 0
  let finished = false
  const elapsed = (since: number) => Math.max(0, Math.round(now() - since))
  const record = (event: string, phase: string, extra: Pick<Event, 'status' | 'elapsed_ms'> = {}) => {
    if (finished) return
    if (events.length === 128) { events.shift(); droppedEvents += 1 }
    events.push({ event, phase, ms: elapsed(started), ...extra })
  }
  const onRequest = (request: Request) => {
    const phase = requestPhase(request)
    if (!phase) return
    if (pending.size === 32 && !pending.has(request)) {
      const oldest = pending.keys().next().value
      if (oldest) pending.delete(oldest)
      evictedRequests += 1
    }
    pending.set(request, { phase, at: now() })
    record('request', phase)
  }
  const onResponse = (response: Response) => {
    const entry = pending.get(response.request())
    if (entry) record('response', entry.phase, { status: response.status(), elapsed_ms: elapsed(entry.at) })
  }
  const complete = (request: Request, event: string) => {
    const entry = pending.get(request)
    if (entry) { record(event, entry.phase, { elapsed_ms: elapsed(entry.at) }); pending.delete(request) }
  }
  const onFinished = (request: Request) => complete(request, 'finished')
  const onFailed = (request: Request) => complete(request, 'request_failed')
  const onDownload = () => record('download', 'browser')
  const onDialog = () => record('dialog', 'browser')
  const onPageError = () => record('page_error', 'browser')
  page.on('request', onRequest)
  page.on('response', onResponse)
  page.on('requestfinished', onFinished)
  page.on('requestfailed', onFailed)
  page.on('download', onDownload)
  page.on('dialog', onDialog)
  page.on('pageerror', onPageError)
  return {
    mark(value: string) { if (milestones.has(value)) record('milestone', value) },
    finish(status: string, snapshot: Record<string, unknown> = {}) {
      if (finished) return
      finished = true
      if (status === 'passed' || status === 'skipped') return
      const result = ['failed', 'timedOut', 'interrupted'].includes(status) ? status : 'unknown'
      const visible: Record<string, boolean> = {}
      for (const key of visibleControls) if (typeof snapshot[key] === 'boolean') visible[key] = snapshot[key]
      write(JSON.stringify({
        schema_version: 1, scenario, result, elapsed_ms: elapsed(started),
        events, pending: [...pending.values()].map(entry => ({ phase: entry.phase, age_ms: elapsed(entry.at) })),
        visible, dropped_events: droppedEvents, evicted_requests: evictedRequests,
      }))
    },
    dispose() {
      page.off('request', onRequest)
      page.off('response', onResponse)
      page.off('requestfinished', onFinished)
      page.off('requestfailed', onFailed)
      page.off('download', onDownload)
      page.off('dialog', onDialog)
      page.off('pageerror', onPageError)
      pending.clear()
      events.length = 0
    },
  }
}
