import { beforeEach, expect, vi } from 'vitest'
import { browserRecycleBinClient } from './api'

describe('recycle-bin API client', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=recovery-token'
    vi.restoreAllMocks()
  })

  it('uses the selected organization boundary and bounded filters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ results: [], page: 1, page_size: 50, count: 0, has_more: false }), { status: 200 }))

    await browserRecycleBinClient.list({ organizationId: 'org-1' }, { query: 'floor', recordType: 'location' })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/workspaces/organizations/org-1/recycle-bin?page=1&page_size=50&q=floor&record_type=location', expect.objectContaining({ credentials: 'same-origin' }))
  })

  it('sends CSRF when restoring into the MSP workspace', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))

    await browserRecycleBinClient.restore({}, { id: 'site-1', record_type: 'site' })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/recycle-bin/site/site-1/restore')
    const options = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(options.method).toBe('POST')
    expect((options.headers as Record<string, string>)['X-CSRFToken']).toBe('recovery-token')
  })
})
