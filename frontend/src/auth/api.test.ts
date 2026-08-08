import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthRequestError, browserAuthClient, takeInvitationFromLocation, takePasswordResetFromLocation } from './api'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

function jsonResponse(body: object, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
  window.history.replaceState({}, '', '/')
})

describe('browser authentication client', () => {
  it('loads the authenticated context only after server session confirmation', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ bootstrap_required: false }))
      .mockResolvedValueOnce(jsonResponse({ meta: { is_authenticated: true } }))
      .mockResolvedValueOnce(jsonResponse(context))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserAuthClient.load()).resolves.toEqual({ bootstrapRequired: false, context })
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/v1/auth/context', expect.objectContaining({ credentials: 'same-origin' }))
  })

  it('sends the browser CSRF token with login and never puts credentials in a URL', async () => {
    const token = crypto.randomUUID()
    const password = `${crypto.randomUUID()}Aa7!`
    document.cookie = `csrftoken=${token}; path=/`
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ meta: { is_authenticated: true } }))
      .mockResolvedValueOnce(jsonResponse(context))
    vi.stubGlobal('fetch', fetchMock)

    await browserAuthClient.login('owner@example.com', password)

    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/_allauth/browser/v1/auth/login')
    expect(path).not.toContain(password)
    expect(options.credentials).toBe('same-origin')
    expect(options.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': token }))
    expect(JSON.parse(options.body as string)).toEqual({ email: 'owner@example.com', password })
  })

  it('sends the deployment token only in the bootstrap header', async () => {
    const deploymentToken = crypto.randomUUID()
    const password = `${crypto.randomUUID()}Aa7!`
    document.cookie = `csrftoken=${crypto.randomUUID()}; path=/`
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ tenant: {}, owner: {} }, 201))
      .mockResolvedValueOnce(jsonResponse({ meta: { is_authenticated: true } }))
      .mockResolvedValueOnce(jsonResponse(context))
    vi.stubGlobal('fetch', fetchMock)

    await browserAuthClient.bootstrapAndLogin({
      deploymentToken,
      tenantName: 'Example MSP',
      ownerEmail: 'owner@example.com',
      ownerDisplayName: 'Primary Owner',
      password,
    })

    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/api/v1/bootstrap/owner')
    expect(path).not.toContain(deploymentToken)
    expect(options.headers).toEqual(expect.objectContaining({ 'X-TekDocs-Bootstrap-Token': deploymentToken }))
    expect(options.body as string).not.toContain(deploymentToken)
  })

  it('takes the invitation token from the fragment and removes it from browser history', () => {
    const token = `${crypto.randomUUID().replaceAll('-', '')}${crypto.randomUUID().replaceAll('-', '')}`
    window.history.replaceState({}, '', `/auth/invitations/accept#token=${token}`)

    expect(takeInvitationFromLocation()).toEqual({ isInvitationPath: true, token })
    expect(window.location.pathname).toBe('/auth/invitations/accept')
    expect(window.location.hash).toBe('')
  })

  it('submits invitation secrets only in a CSRF-protected request body', async () => {
    const csrf = crypto.randomUUID()
    const token = `${crypto.randomUUID().replaceAll('-', '')}${crypto.randomUUID().replaceAll('-', '')}`
    const password = `${crypto.randomUUID()}Aa7!`
    document.cookie = `csrftoken=${csrf}; path=/`
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(context))
    vi.stubGlobal('fetch', fetchMock)

    await browserAuthClient.acceptInvitation({ token, displayName: 'Invited Technician', password })

    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/api/v1/invitations/accept')
    expect(path).not.toContain(token)
    expect(options.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': csrf }))
    expect(JSON.parse(options.body as string)).toEqual({
      token,
      display_name: 'Invited Technician',
      password,
    })
  })

  it('takes a password reset key from the fragment and removes it immediately', () => {
    const key = `${crypto.randomUUID()}-${crypto.randomUUID()}`
    window.history.replaceState({}, '', `/auth/reset-password#key=${encodeURIComponent(key)}`)

    expect(takePasswordResetFromLocation()).toEqual({ isPasswordResetPath: true, key })
    expect(window.location.href).not.toContain(key)
    expect(window.location.hash).toBe('')
  })

  it('sends reset credentials through protected allauth interfaces', async () => {
    const csrf = crypto.randomUUID()
    const key = `${crypto.randomUUID()}-${crypto.randomUUID()}`
    const password = `${crypto.randomUUID()}Aa7!`
    document.cookie = `csrftoken=${csrf}; path=/`
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await browserAuthClient.requestPasswordReset('owner@example.com')
    await browserAuthClient.validatePasswordReset(key)
    await browserAuthClient.completePasswordReset(key, password)

    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>
    const requestCall = calls[0]
    expect(requestCall[0]).toBe('/_allauth/browser/v1/auth/password/request')
    expect(requestCall[0]).not.toContain('owner@example.com')
    expect(requestCall[1]).toEqual(expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ email: 'owner@example.com' }),
    }))
    expect(requestCall[1].headers).toEqual(expect.objectContaining({ 'X-CSRFToken': csrf }))
    expect(calls[1][1]?.headers).toEqual(expect.objectContaining({ 'X-Password-Reset-Key': key }))
    expect(calls[2][0]).not.toContain(key)
    expect(calls[2][1]).toEqual(expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ key, password }),
    }))
  })

  it('lists and revokes only selected browser sessions through CSRF-protected requests', async () => {
    const csrf = crypto.randomUUID()
    document.cookie = `csrftoken=${csrf}; path=/`
    const response = {
      data: [{ id: 42, user_agent: 'Test browser', ip: '192.0.2.1', created_at: 10, last_seen_at: 20, is_current: false }],
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(response))
      .mockResolvedValueOnce(jsonResponse({ data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserAuthClient.listSessions()).resolves.toEqual([{
      id: 42,
      userAgent: 'Test browser',
      ip: '192.0.2.1',
      createdAt: 10,
      lastSeenAt: 20,
      isCurrent: false,
    }])
    await expect(browserAuthClient.revokeSession(42)).resolves.toEqual([])

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/_allauth/browser/v1/auth/sessions', expect.objectContaining({ credentials: 'same-origin' }))
    const [revokePath, revokeOptions] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(revokePath).toBe('/_allauth/browser/v1/auth/sessions')
    expect(revokeOptions.method).toBe('DELETE')
    expect(revokeOptions.body).toBe(JSON.stringify({ sessions: [42] }))
    expect(revokeOptions.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': csrf }))
  })

  it('turns authentication rate limits into safe wait-and-retry messages', async () => {
    document.cookie = `csrftoken=${crypto.randomUUID()}; path=/`
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ status: 429 }, 429)))

    await expect(browserAuthClient.login('owner@example.com', 'not-a-real-password')).rejects.toEqual(
      new AuthRequestError('Too many sign-in attempts. Wait a few minutes and try again.', 429),
    )
    await expect(browserAuthClient.requestPasswordReset('owner@example.com')).rejects.toEqual(
      new AuthRequestError('Too many reset requests. Wait before trying again.', 429),
    )
  })
})
