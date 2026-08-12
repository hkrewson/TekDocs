import { afterEach, describe, expect, it, vi } from 'vitest'

import type { WorkspaceContext } from '../workspaces/api'
import { browserComplianceClient } from './api'

const organization: WorkspaceContext = {
  id: 'client/entity',
  name: 'Client One',
  kind: 'organization',
  classifications: ['client'],
  capabilities: [],
  organization: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('browserComplianceClient', () => {
  it('uses the explicit MSP collection for list requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: false,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await browserComplianceClient.list(null, 'security', 2)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/workspaces/msp/compliance/frameworks?q=security&page=2&page_size=50', expect.any(Object))
  })

  it('encodes organization identity and sends the CSRF token on mutation', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=test-token' })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'framework-1' }), {
        status: 201, headers: { 'Content-Type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)

    await browserComplianceClient.create(organization, {
      name: 'Baseline', version_label: '1', description: '', source_url: '', controls: [],
    })

    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fentity/compliance/frameworks')
    const request = fetchMock.mock.calls[1]?.[1] as RequestInit | undefined
    expect(request?.method).toBe('POST')
    expect(request?.headers).toMatchObject({ 'X-CSRFToken': 'test-token' })
  })

  it('uses the structured API error message when a request is denied', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ error: { message: 'Compliance access denied.' } }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(browserComplianceClient.revisions(null, 'framework-1')).rejects.toThrow('Compliance access denied.')
  })
})
