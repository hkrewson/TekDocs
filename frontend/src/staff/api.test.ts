import { beforeEach, expect, vi } from 'vitest'
import { browserStaffAdministrationClient } from './api'

describe('staff administration API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(document, 'cookie', { configurable: true, writable: true, value: 'csrftoken=staff-csrf' })
  })

  it('issues an invitation through a same-origin CSRF request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id: 'invitation' }), { status: 201 }))

    await browserStaffAdministrationClient.issue('new@example.com')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/invitations', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      body: JSON.stringify({ email: 'new@example.com' }),
    }))
    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect(request.headers).toMatchObject({ 'X-CSRFToken': 'staff-csrf' })
  })

  it('returns a safe owner-only denial without exposing server detail', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'internal policy detail' }), { status: 403 }))

    await expect(browserStaffAdministrationClient.invitations()).rejects.toThrow('Only the installation owner can manage MSP staff invitations.')
  })
})
