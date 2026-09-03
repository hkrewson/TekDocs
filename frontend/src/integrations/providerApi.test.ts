import { afterEach, describe, expect, it, vi } from 'vitest'

import type { WorkspaceContext } from '../workspaces/api'
import type { IntegrationConflict, IntegrationConnection, IntegrationJob } from './providerApi'
import { browserIntegrationsClient } from './providerApi'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client/one', name: 'Acme Dental', classifications: ['client'],
  capabilities: ['overview', 'integrations'], organization: null,
}

afterEach(() => vi.restoreAllMocks())

function requestPath(input: RequestInfo | URL) {
  if (typeof input === 'string') return input
  return input instanceof URL ? input.href : input.url
}

describe('provider integrations API', () => {
  it('uses exact encoded workspace routes and does not send credentials on reads', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )

    await browserIntegrationsClient.listProviders(workspace)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2Fone/integrations/providers',
      expect.objectContaining({ credentials: 'same-origin', headers: { Accept: 'application/json' } }),
    )
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('api_token')
  })

  it('builds a same-workspace download URL without a remote Git credential', () => {
    const bundle = {
      id: 'bundle/one', selection_manifest: { documents: [], publications: [] },
      content_digest: 'a'.repeat(64), byte_size: 1, created_at: '2026-08-12T00:00:00Z',
    }
    expect(browserIntegrationsClient.gitExportDownloadUrl(workspace, bundle)).toBe(
      '/api/v1/workspaces/organizations/client%2Fone/integrations/git-exports/bundle%2Fone/download',
    )
  })

  it('protects provider mutations with CSRF and exact workspace object routes', async () => {
    document.cookie = 'csrftoken=integration-csrf; path=/'
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const path = requestPath(input)
      if (path === '/_allauth/browser/v1/auth/session') return Promise.resolve(new Response('{}', { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ id: 'result' }), { status: 200 }))
    })
    const connection = { id: 'connection/one', active: true, sync_interval_minutes: 60 } as IntegrationConnection
    const conflict = { id: 'conflict/one' } as IntegrationConflict
    const job = { id: 'job/one' } as IntegrationJob

    await browserIntegrationsClient.createConnection(workspace, {
      provider: 'netbox', name: 'Primary', base_url: 'https://netbox.example.com/api/',
      credentials: { api_token: 'one-time-token' }, sync_interval_minutes: 60,
    })
    await browserIntegrationsClient.updateConnection(workspace, connection, false)
    await browserIntegrationsClient.rotateConnection(workspace, connection, { api_token: 'replacement-token' })
    await browserIntegrationsClient.startSync(workspace, connection)
    await browserIntegrationsClient.cancelJob(workspace, job)
    await browserIntegrationsClient.resolveConflict(workspace, conflict, 'keep_local')
    await browserIntegrationsClient.createGitExport(workspace, ['document-1'], [])

    const mutations = fetchMock.mock.calls.filter(([path]) => requestPath(path) !== '/_allauth/browser/v1/auth/session')
    expect(mutations).toHaveLength(7)
    for (const [, request] of mutations) {
      expect(new Headers(request?.headers).get('X-CSRFToken')).toBe('integration-csrf')
    }
    expect(requestPath(mutations[2][0])).toContain('/connections/connection%2Fone/rotate')
    expect(requestPath(mutations[4][0])).toContain('/jobs/job%2Fone/cancel')
    expect(requestPath(mutations[5][0])).toContain('/conflicts/conflict%2Fone/resolve')
    expect(JSON.stringify(mutations[0]?.[1]?.body)).toContain('one-time-token')
  })

  it('loads operational collections and surfaces safe errors', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: 'Provider denied.' } }), { status: 403 }))

    await browserIntegrationsClient.listJobs(workspace)
    await browserIntegrationsClient.listLogs(workspace)
    await browserIntegrationsClient.listConflicts(workspace)
    await browserIntegrationsClient.listGitExports(workspace)
    await expect(browserIntegrationsClient.listConnections(workspace)).rejects.toThrow('Provider denied.')
    expect(fetchMock.mock.calls.map(([path]) => requestPath(path))).toEqual([
      '/api/v1/workspaces/organizations/client%2Fone/integrations/jobs?page=1&page_size=50',
      '/api/v1/workspaces/organizations/client%2Fone/integrations/logs?page=1&page_size=50',
      '/api/v1/workspaces/organizations/client%2Fone/integrations/conflicts?page=1&page_size=50',
      '/api/v1/workspaces/organizations/client%2Fone/integrations/git-exports',
      '/api/v1/workspaces/organizations/client%2Fone/integrations/connections',
    ])
  })
})
