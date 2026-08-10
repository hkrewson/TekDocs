import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browserCredentialReferencesClient } from './api'

describe('credential-reference API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=test-csrf' })
    vi.stubGlobal('fetch', vi.fn())
  })

  it('uses organization-scoped routes and never opens a provider URL supplied by the API', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ results: [], can_manage: false }), { status: 200 }))
    const workspace = { id: 'org-1' } as never
    await browserCredentialReferencesClient.list(workspace, 'router')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/org-1/credential-references?q=router',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    expect(browserCredentialReferencesClient.openUrl(workspace, 'ref/1')).toBe(
      '/api/v1/workspaces/organizations/org-1/credential-references/ref%2F1/open',
    )
  })
})
