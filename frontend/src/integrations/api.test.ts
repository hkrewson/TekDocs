import { afterEach, describe, expect, it, vi } from 'vitest'

import type { WorkspaceContext } from '../workspaces/api'
import { browserWebhooksClient } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client/one', name: 'Acme Dental', classifications: ['client'],
  capabilities: ['overview', 'integrations'], organization: null,
}

afterEach(() => vi.restoreAllMocks())

describe('webhooks API', () => {
  it('scopes delivery inspection and protects mutations with CSRF', async () => {
    document.cookie = 'csrftoken=webhook-csrf; path=/'
    const endpoint = {
      id: 'endpoint/one', direction: 'outbound' as const, name: 'PSA', url: 'https://hooks.example.com/tekdocs',
      inbound_path: null, topics: ['document_publication.available'], secret_prefix: 'tdwhsec_sample',
      secret_generation: 1, active: true, created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [], page: 2, page_size: 25, count: 0, has_more: false }), { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...endpoint, signing_secret: 'tdwhsec_once' }), { status: 200 }))

    await browserWebhooksClient.listDeliveries(workspace, 2, 'dead_letter')
    await browserWebhooksClient.rotate(workspace, endpoint)

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fone/integrations/webhooks/deliveries?page=2&page_size=25&state=dead_letter')
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fone/integrations/webhooks/endpoints/endpoint%2Fone/rotate')
    const rotateRequest = fetchMock.mock.calls[2]?.[1]
    expect(rotateRequest?.method).toBe('POST')
    expect(rotateRequest?.body).toBeUndefined()
    expect(new Headers(rotateRequest?.headers).get('X-CSRFToken')).toBe('webhook-csrf')
  })

  it('surfaces structured and safe fallback errors', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: 'Endpoint denied.' } }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Endpoint unavailable.' }), { status: 404 }))
      .mockResolvedValueOnce(new Response('not-json', { status: 500 }))

    await expect(browserWebhooksClient.listEndpoints(workspace)).rejects.toThrow('Endpoint denied.')
    await expect(browserWebhooksClient.listEndpoints(workspace)).rejects.toThrow('Endpoint unavailable.')
    await expect(browserWebhooksClient.listEndpoints(workspace)).rejects.toThrow('The webhook request failed.')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
