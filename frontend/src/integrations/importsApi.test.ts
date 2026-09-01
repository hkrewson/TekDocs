import { afterEach, describe, expect, it, vi } from 'vitest'

import type { WorkspaceContext } from '../workspaces/api'
import type { ImportBatch } from './importsApi'
import { browserImportsClient } from './importsApi'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client/one', name: 'Acme Dental', classifications: ['client'],
  capabilities: ['overview', 'integrations'], organization: null,
}

const batch = { id: 'batch/one' } as ImportBatch

afterEach(() => vi.restoreAllMocks())

function path(input: RequestInfo | URL) {
  if (typeof input === 'string') return input
  return input instanceof URL ? input.href : input.url
}

describe('imports API', () => {
  it('uses exact workspace routes for history, rows, templates, and reports', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => (
      Promise.resolve(new Response(JSON.stringify({ results: [] }), { status: 200 }))
    ))
    await browserImportsClient.list(workspace)
    await browserImportsClient.rows(workspace, batch)

    expect(fetchMock.mock.calls.map(([input]) => path(input))).toEqual([
      '/api/v1/workspaces/organizations/client%2Fone/integrations/imports?page=1&page_size=25',
      '/api/v1/workspaces/organizations/client%2Fone/integrations/imports/batch%2Fone/rows?page=1&page_size=100',
    ])
    expect(browserImportsClient.templateUrl(workspace, 'sites')).toContain('/imports/templates/sites')
    expect(browserImportsClient.reportUrl(workspace, batch)).toContain('/imports/batch%2Fone/report')
  })

  it('sends an upload as multipart and protects every mutation with CSRF', async () => {
    document.cookie = 'csrftoken=import-csrf; path=/'
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      if (path(input) === '/_allauth/browser/v1/auth/session') return Promise.resolve(new Response('{}', { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify(batch), { status: 200 }))
    })
    const file = new File(['external_key,name\nsite-1,HQ\n'], 'sites.csv', { type: 'text/csv' })

    await browserImportsClient.preview(workspace, file, 'tekdocs_csv', 'sites')
    await browserImportsClient.apply(workspace, batch, { 'row-1': 'entity-1' })
    await browserImportsClient.cancel(workspace, batch)

    const mutations = fetchMock.mock.calls.filter(([input]) => path(input) !== '/_allauth/browser/v1/auth/session')
    expect(mutations).toHaveLength(3)
    expect(mutations[0]?.[1]?.body).toBeInstanceOf(FormData)
    for (const [, request] of mutations) expect(new Headers(request?.headers).get('X-CSRFToken')).toBe('import-csrf')
  })
})
