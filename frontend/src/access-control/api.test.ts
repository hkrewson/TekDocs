import { afterEach, expect, vi } from 'vitest'
import { browserAccessControlClient } from './api'

function response(body: object, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
})

describe('access-control API', () => {
  it('loads each bounded administration resource', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ permissions: [], roles: [] }))
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response([]))
    vi.stubGlobal('fetch', fetchMock)

    await browserAccessControlClient.catalog()
    await browserAccessControlClient.members()
    await browserAccessControlClient.organizations()

    const paths = fetchMock.mock.calls.map((call) => (call as [string, RequestInit?])[0])
    expect(paths).toEqual([
      '/api/v1/access-control/catalog',
      '/api/v1/access-control/members',
      '/api/v1/access-control/organizations',
    ])
  })

  it('sends role and access-mode changes with same-origin CSRF', async () => {
    document.cookie = 'csrftoken=policy-token; path=/'
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ id: 'member-1', role: 'technician' }))
      .mockResolvedValueOnce(response({ id: 'org-1', access_mode: 'assigned_only' }))
    vi.stubGlobal('fetch', fetchMock)

    await browserAccessControlClient.assignRole('member-1', 'technician')
    await browserAccessControlClient.changeAccessMode('org-1', 'assigned_only')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/access-control/members/member-1', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ role: 'technician' }),
    }))
    const firstRequest = fetchMock.mock.calls[0][1] as RequestInit
    expect(firstRequest.headers).toMatchObject({ 'X-CSRFToken': 'policy-token' })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/access-control/organizations/org-1', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ access_mode: 'assigned_only' }),
    }))
  })
})
