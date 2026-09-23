import { afterEach, describe, expect, it, vi } from 'vitest'

import { browserWorkspaceSearchClient } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('browserWorkspaceSearchClient', () => {
  it('requests MSP search with bounded pagination and an optional type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserWorkspaceSearchClient.search({}, 'firewall rules', 'document', 2, 50)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search?q=firewall+rules&page=2&page_size=50&result_type=document',
      expect.objectContaining({ credentials: 'same-origin', headers: { Accept: 'application/json' } }),
    )
  })

  it('uses the selected organization workspace endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserWorkspaceSearchClient.search({ organizationId: 'client/id' }, 'router', '', 1, 25)

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/workspaces/organizations/client%2Fid/search?q=router&page=1&page_size=25')
  })
})
