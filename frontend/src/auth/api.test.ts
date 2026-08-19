import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AuthRequestError,
  browserAuthClient,
  browserCsrfToken,
  privilegedActionError,
  responseErrorCode,
  takeInvitationFromLocation,
  takePasswordResetFromLocation,
} from './api'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

/** The request target as a string, whatever form the caller passed it in. */
function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  return input instanceof URL ? input.href : input.url
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

  it('recognizes and completes a pending two-factor sign-in flow', async () => {
    const csrf = crypto.randomUUID()
    document.cookie = `csrftoken=${csrf}; path=/`
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: { flows: [{ id: 'mfa_authenticate', is_pending: true }] } }, 401))
      .mockResolvedValueOnce(jsonResponse({ meta: { is_authenticated: true } }))
      .mockResolvedValueOnce(jsonResponse(context))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserAuthClient.login('owner@example.com', 'password')).resolves.toEqual({ mfaRequired: true })
    await expect(browserAuthClient.completeMfaLogin('recovery-code')).resolves.toEqual(context)

    expect(fetchMock).toHaveBeenNthCalledWith(2, '/_allauth/browser/v1/auth/2fa/authenticate', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ code: 'recovery-code' }),
    }))
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

  it('loads safe OIDC descriptors and updates the profile with CSRF protection', async () => {
    const csrf = crypto.randomUUID()
    document.cookie = `csrftoken=${csrf}; path=/`
    const providers = [{ id: 'company-sso', name: 'Company SSO' }]
    const updated = { ...context, user: { ...context.user, display_name: 'Operations Lead' } }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ providers }))
      .mockResolvedValueOnce(jsonResponse(updated))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserAuthClient.listOidcProviders()).resolves.toEqual(providers)
    await expect(browserAuthClient.updateProfile('Operations Lead')).resolves.toEqual(updated)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/auth/providers', expect.objectContaining({ credentials: 'same-origin' }))
    const [profilePath, profileOptions] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(profilePath).toBe('/api/v1/auth/profile')
    expect(profileOptions).toEqual(expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ display_name: 'Operations Lead' }),
    }))
    expect(profileOptions.headers).toEqual(expect.objectContaining({ 'X-CSRFToken': csrf }))
  })

  it('keeps authenticator secrets in protected request bodies and reads recovery codes once', async () => {
    const csrf = crypto.randomUUID()
    document.cookie = `csrftoken=${csrf}; path=/`
    const secret = 'JBSWY3DPEHPK3PXP'
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: [] }))
      .mockResolvedValueOnce(jsonResponse({ meta: { secret, totp_url: `otpauth://totp/TekDocs?secret=${secret}` } }, 404))
      .mockResolvedValueOnce(jsonResponse({ data: { type: 'totp' } }))
      .mockResolvedValueOnce(jsonResponse({ data: { unused_codes: ['one', 'two'] } }))
      .mockResolvedValueOnce(jsonResponse({ data: { unused_codes: ['three', 'four'] } }))
      .mockResolvedValueOnce(jsonResponse({ data: { reauthenticated: true } }))
      .mockResolvedValueOnce(jsonResponse({ data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserAuthClient.loadMfa()).resolves.toEqual({ totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 })
    await expect(browserAuthClient.beginTotp()).resolves.toEqual({ secret, totpUrl: `otpauth://totp/TekDocs?secret=${secret}` })
    await expect(browserAuthClient.activateTotp('123456')).resolves.toEqual(['one', 'two'])
    await expect(browserAuthClient.regenerateRecoveryCodes()).resolves.toEqual(['three', 'four'])
    await browserAuthClient.reauthenticate('current-password')
    await browserAuthClient.disableTotp()

    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>
    expect(calls[2][0]).toBe('/_allauth/browser/v1/account/authenticators/totp')
    expect(calls[2][1].body).toBe(JSON.stringify({ code: '123456' }))
    expect(calls[5][1].body).toBe(JSON.stringify({ password: 'current-password' }))
    expect(calls[6][1].method).toBe('DELETE')
    expect(calls[6][1].headers).toEqual(expect.objectContaining({ 'X-CSRFToken': csrf }))
  })

  it('loads recovery-code counts from the safe authenticator list after refresh', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({
      data: [
        { type: 'totp', created_at: 1_786_000_000, last_used_at: null },
        { type: 'recovery_codes', total_code_count: 10, unused_code_count: 7 },
      ],
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserAuthClient.loadMfa()).resolves.toEqual({
      totpEnabled: true,
      recoveryCodeTotal: 10,
      recoveryCodeUnused: 7,
    })
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledWith(
      '/_allauth/browser/v1/account/authenticators',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
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

  it('returns no error code rather than failing when a body is not an error envelope', async () => {
    await expect(responseErrorCode(new Response('not json', { status: 500 }))).resolves.toBeUndefined()
    await expect(responseErrorCode(new Response('{}', { status: 403 }))).resolves.toBeUndefined()
    await expect(
      responseErrorCode(new Response(JSON.stringify({ error: { code: 'privileged_mfa_required' } }), { status: 403 })),
    ).resolves.toBe('privileged_mfa_required')
  })

  it('reads an error envelope without consuming the body the caller still needs', async () => {
    const response = new Response(JSON.stringify({ error: { code: 'privileged_mfa_required' } }), { status: 403 })

    await responseErrorCode(response)

    // The envelope is read from a clone, so the caller's body is still intact.
    expect(response.bodyUsed).toBe(false)
    await expect(response.json()).resolves.toEqual({ error: { code: 'privileged_mfa_required' } })
  })

  it('names the missing second factor instead of repeating a generic denial', async () => {
    const required = await privilegedActionError(
      new Response(JSON.stringify({ error: { code: 'privileged_mfa_required' } }), { status: 403 }),
      'You are not allowed to do that.',
    )
    expect(required.message).toBe('Two-factor authentication is required for this action.')
    expect(required.code).toBe('privileged_mfa_required')
    expect(required.status).toBe(403)

    // Any other denial keeps the caller's wording: only the MFA case is rewritten.
    const denied = await privilegedActionError(new Response('{}', { status: 403 }), 'You are not allowed to do that.')
    expect(denied.message).toBe('You are not allowed to do that.')
    expect(denied.code).toBeUndefined()
  })

  it('reads the security token out of a cookie jar that holds other cookies', () => {
    document.cookie = 'sessionid=abc'
    document.cookie = 'theme=dark'
    document.cookie = 'csrftoken=token%2Fvalue'

    expect(browserCsrfToken()).toBe('token/value')

    document.cookie = 'csrftoken=; Max-Age=0; path=/'
    expect(browserCsrfToken()).toBeNull()
  })

  it('reports an unreadable session response rather than treating it as signed out', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(requestUrl(input).includes('/_allauth/')
        ? new Response('not json', { status: 200 })
        : jsonResponse({ bootstrap_required: false }))))

    await expect(browserAuthClient.load()).rejects.toThrow('The server returned an unreadable response.')
  })

  it('separates an unavailable session service from an unauthenticated one', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(requestUrl(input).includes('/_allauth/')
        ? jsonResponse({}, 503)
        : jsonResponse({ bootstrap_required: false }))))

    // 401 means signed out; anything else means the service failed, and the two must
    // not be collapsed into "please sign in".
    await expect(browserAuthClient.load()).rejects.toThrow('The session service is unavailable.')
  })

  it('reports a signed-out session without treating it as an error', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(requestUrl(input).includes('/_allauth/')
        ? jsonResponse({ meta: { is_authenticated: false } }, 401)
        : jsonResponse({ bootstrap_required: false }))))

    await expect(browserAuthClient.load()).resolves.toEqual({ bootstrapRequired: false, context: null })
  })

  it('refuses the workspace when the session is valid but the account cannot open it', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (requestUrl(input).includes('/_allauth/')) return Promise.resolve(jsonResponse({ meta: { is_authenticated: true } }))
      if (requestUrl(input).includes('/auth/context')) return Promise.resolve(jsonResponse({}, 403))
      return Promise.resolve(jsonResponse({ bootstrap_required: false }))
    }))

    await expect(browserAuthClient.load()).rejects.toThrow('This account cannot open the TekDocs workspace.')
  })

  it('reports an unavailable installation status instead of assuming a fresh install', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(requestUrl(input).includes('/_allauth/')
        ? jsonResponse({ meta: { is_authenticated: false } })
        : jsonResponse({}, 503))))

    await expect(browserAuthClient.load()).rejects.toThrow('Installation status is unavailable.')
  })

  it('stops at the bootstrap screen without asking for a context it cannot have', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(requestUrl(input).includes('/_allauth/')
        ? jsonResponse({ meta: { is_authenticated: false } })
        : jsonResponse({ bootstrap_required: true }))))

    await expect(browserAuthClient.load()).resolves.toEqual({ bootstrapRequired: true, context: null })
  })

  it.each([
    [400, 'The email address or password is incorrect.'],
    [429, 'Too many sign-in attempts. Wait a few minutes and try again.'],
    [500, 'Sign in was not completed.'],
  ])('turns a %i sign-in rejection into wording that discloses nothing about the account', async (status, message) => {
    document.cookie = 'csrftoken=login-csrf'
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({}, status))))

    await expect(browserAuthClient.login('owner@example.com', 'secret')).rejects.toThrow(message)
  })

  it('treats a 401 without a pending second factor as a failed sign-in, not a challenge', async () => {
    document.cookie = 'csrftoken=login-csrf'
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve(jsonResponse({ data: { flows: [{ id: 'password_reset_by_code', is_pending: true }] } }, 401))))

    await expect(browserAuthClient.login('owner@example.com', 'secret')).rejects.toThrow('Sign in was not completed.')
  })

  it('does not send a sign-in at all when no security token can be obtained', async () => {
    document.cookie = 'csrftoken=; Max-Age=0; path=/'
    const fetchMock = vi.fn((input: RequestInfo | URL) => Promise.resolve(jsonResponse({ meta: { is_authenticated: requestUrl(input) === '' } })))
    vi.stubGlobal('fetch', fetchMock)

    await expect(browserAuthClient.login('owner@example.com', 'secret')).rejects.toThrow(
      'The browser security token is unavailable. Refresh and try again.',
    )
    // Only the token-recovery attempt reached the network; the credentials never did.
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(['/_allauth/browser/v1/auth/session'])
  })

  it('reports no invitation or reset when the browser is on any other path', () => {
    window.history.replaceState({}, '', '/overview')

    expect(takeInvitationFromLocation()).toEqual({ isInvitationPath: false, token: null })
    expect(takePasswordResetFromLocation()).toEqual({ isPasswordResetPath: false, key: null })
  })

  it('reports the path without a token when the fragment carries none', () => {
    window.history.replaceState({}, '', '/auth/invitations/accept#other=value')
    expect(takeInvitationFromLocation()).toEqual({ isInvitationPath: true, token: null })

    window.history.replaceState({}, '', '/auth/reset-password#key=')
    expect(takePasswordResetFromLocation()).toEqual({ isPasswordResetPath: true, key: null })
  })
})
