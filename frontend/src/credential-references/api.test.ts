import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browserCredentialReferencesClient } from './api'

describe('credential-reference API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=test-csrf' })
    vi.stubGlobal('fetch', vi.fn())
  })

  it('uses organization-scoped routes and never opens a provider URL supplied by the API', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ results: [], page: 2, page_size: 50, count: 0, has_more: false, can_manage: false }), { status: 200 }))
    const workspace = { id: 'org-1' } as never
    await browserCredentialReferencesClient.list(workspace, 'router', 2, 50)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/org-1/credential-references?q=router&page=2&page_size=50',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    expect(browserCredentialReferencesClient.openUrl(workspace, 'ref/1')).toBe(
      '/api/v1/workspaces/organizations/org-1/credential-references/ref%2F1/open',
    )
  })

  it('loads one record without exposing or requesting its provider link', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ id: 'ref-1', title: 'Router', provider: 'onepassword' }), { status: 200 }))
    await browserCredentialReferencesClient.retrieve(null, 'ref/1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/credential-references/ref%2F1',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
  })
})
