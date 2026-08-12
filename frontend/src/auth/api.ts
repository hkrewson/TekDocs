export type AuthenticatedContext = {
  user: {
    id: string
    email: string
    display_name: string
  }
  tenant: {
    id: string
    name: string
  }
  role: 'owner' | 'administrator' | 'technician' | 'contributor' | 'read_only' | 'client_administrator' | 'client_user'
  permissions: string[]
  surface: 'msp' | 'client_portal'
  organization: { id: string; name: string } | null
}

export type BootstrapDetails = {
  deploymentToken: string
  tenantName: string
  ownerEmail: string
  ownerDisplayName: string
  password: string
}

export type InvitationAcceptance = {
  token: string
  displayName: string
  password: string
}

export type AuthSession = {
  id: number
  userAgent: string
  ip: string
  createdAt: number
  lastSeenAt: number
  isCurrent: boolean
}

export type MfaChallenge = { mfaRequired: true }

export type MfaStatus = {
  totpEnabled: boolean
  recoveryCodeTotal: number
  recoveryCodeUnused: number
}

export type TotpSetup = {
  secret: string
  totpUrl: string
}

export type ApiTokenPermission = {
  key: string
  label: string
  category: string
  requires_mfa: boolean
  service_eligible: boolean
}
export type ApiToken = {
  id: string
  kind: 'personal' | 'service'
  name: string
  display_prefix: string
  workspace_scope: 'msp' | 'organization'
  organization: { id: string; name: string } | null
  permissions: string[]
  status: 'active' | 'expired' | 'revoked'
  generation: number
  created_at: string
  expires_at: string
  last_used_at: string | null
  rotated_at: string | null
  revoked_at: string | null
}
export type IssuedApiToken = ApiToken & { token: string }
export type ApiTokenCatalog = { tokens: ApiToken[]; permissions: ApiTokenPermission[] }
export type ApiTokenInput = {
  name: string
  kind: ApiToken['kind']
  workspace_scope: ApiToken['workspace_scope']
  organization_id: string | null
  permissions: string[]
  expires_in_days: number
}
export type TokenOrganization = { id: string; name: string; classifications: string[] }

export type OidcProvider = {
  id: string
  name: string
}

export interface AuthClient {
  load(): Promise<{ bootstrapRequired: boolean; context: AuthenticatedContext | null }>
  bootstrapAndLogin(details: BootstrapDetails): Promise<AuthenticatedContext>
  login(email: string, password: string): Promise<AuthenticatedContext | MfaChallenge>
  completeMfaLogin(code: string): Promise<AuthenticatedContext>
  acceptInvitation(details: InvitationAcceptance): Promise<AuthenticatedContext>
  requestPasswordReset(email: string): Promise<void>
  validatePasswordReset(key: string): Promise<void>
  completePasswordReset(key: string, password: string): Promise<void>
  listOidcProviders(): Promise<OidcProvider[]>
  updateProfile(displayName: string): Promise<AuthenticatedContext>
  listSessions(): Promise<AuthSession[]>
  revokeSession(id: number): Promise<AuthSession[]>
  loadMfa(): Promise<MfaStatus>
  beginTotp(): Promise<TotpSetup>
  activateTotp(code: string): Promise<string[]>
  regenerateRecoveryCodes(): Promise<string[]>
  disableTotp(): Promise<void>
  reauthenticate(password: string): Promise<void>
  listApiTokens(): Promise<ApiTokenCatalog>
  issueApiToken(input: ApiTokenInput): Promise<IssuedApiToken>
  rotateApiToken(id: string, expiresInDays: number): Promise<IssuedApiToken>
  revokeApiToken(id: string): Promise<ApiToken>
  searchTokenOrganizations(query: string): Promise<TokenOrganization[]>
  logout(): Promise<void>
}

type AllauthSessionResponse = {
  meta?: { is_authenticated?: boolean }
}

type AllauthUserSession = {
  id: number
  user_agent: string
  ip: string
  created_at: number
  last_seen_at?: number
  is_current: boolean
}

type AllauthSessionsResponse = { data?: AllauthUserSession[] }

type AllauthFlowResponse = { data?: { flows?: Array<{ id?: string; is_pending?: boolean }> } }
type AllauthAuthenticator = {
  type?: string
  total_code_count?: number
  unused_code_count?: number
}
type AllauthAuthenticatorsResponse = { data?: AllauthAuthenticator[] }
type AllauthRecoveryResponse = {
  data?: { total_code_count?: number; unused_code_count?: number; unused_codes?: string[] }
}

export class AuthRequestError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message)
    this.name = 'AuthRequestError'
  }
}

export function browserCsrfToken(): string | null {
  const value = document.cookie
    .split('; ')
    .find((part) => part.startsWith('csrftoken='))
    ?.slice('csrftoken='.length)
  return value ? decodeURIComponent(value) : null
}

async function responseJson<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T
  } catch {
    throw new AuthRequestError('The server returned an unreadable response.', response.status)
  }
}

async function session(): Promise<boolean> {
  const response = await fetch('/_allauth/browser/v1/auth/session', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
  const payload = await responseJson<AllauthSessionResponse>(response)
  if (response.status === 401) return false
  if (!response.ok) throw new AuthRequestError('The session service is unavailable.', response.status)
  return payload.meta?.is_authenticated === true
}

async function context(): Promise<AuthenticatedContext> {
  const response = await fetch('/api/v1/auth/context', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new AuthRequestError('This account cannot open the TekDocs workspace.', response.status)
  return responseJson<AuthenticatedContext>(response)
}

async function mutation(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: object): Promise<Response> {
  if (!browserCsrfToken()) await session()
  const token = browserCsrfToken()
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  return fetch(path, {
    method,
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': token,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
}

async function login(email: string, password: string): Promise<AuthenticatedContext | MfaChallenge> {
  const response = await mutation('/_allauth/browser/v1/auth/login', 'POST', { email, password })
  if (response.status === 401) {
    const payload = await responseJson<AllauthFlowResponse>(response)
    if (payload.data?.flows?.some((flow) => flow.id === 'mfa_authenticate' && flow.is_pending)) {
      return { mfaRequired: true }
    }
  }
  if (!response.ok) {
    throw new AuthRequestError(
      response.status === 400
        ? 'The email address or password is incorrect.'
        : response.status === 429
          ? 'Too many sign-in attempts. Wait a few minutes and try again.'
          : 'Sign in was not completed.',
      response.status,
    )
  }
  return context()
}

async function recoveryCodes(response: Response): Promise<string[]> {
  const payload = await responseJson<AllauthRecoveryResponse>(response)
  return payload.data?.unused_codes ?? []
}

function authSessions(payload: AllauthSessionsResponse): AuthSession[] {
  return (payload.data ?? []).map((item) => ({
    id: item.id,
    userAgent: item.user_agent,
    ip: item.ip,
    createdAt: item.created_at,
    lastSeenAt: item.last_seen_at ?? item.created_at,
    isCurrent: item.is_current,
  }))
}

export function takeInvitationFromLocation(): { isInvitationPath: boolean; token: string | null } {
  const isInvitationPath = window.location.pathname === '/auth/invitations/accept'
  if (!isInvitationPath) return { isInvitationPath: false, token: null }
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token')
  window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`)
  return { isInvitationPath: true, token: token || null }
}

export function takePasswordResetFromLocation(): { isPasswordResetPath: boolean; key: string | null } {
  const isPasswordResetPath = window.location.pathname === '/auth/reset-password'
  if (!isPasswordResetPath) return { isPasswordResetPath: false, key: null }
  const key = new URLSearchParams(window.location.hash.slice(1)).get('key')
  window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`)
  return { isPasswordResetPath: true, key: key || null }
}

export const browserAuthClient: AuthClient = {
  async load() {
    const [bootstrapResponse, authenticated] = await Promise.all([
      fetch('/api/v1/bootstrap/status', {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      }),
      session(),
    ])
    if (!bootstrapResponse.ok) {
      throw new AuthRequestError('Installation status is unavailable.', bootstrapResponse.status)
    }
    const bootstrapStatus = await responseJson<{ bootstrap_required: boolean }>(bootstrapResponse)
    if (bootstrapStatus.bootstrap_required) return { bootstrapRequired: true, context: null }
    if (!authenticated) return { bootstrapRequired: false, context: null }
    return { bootstrapRequired: false, context: await context() }
  },

  async bootstrapAndLogin(details) {
    const response = await fetch('/api/v1/bootstrap/owner', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-TekDocs-Bootstrap-Token': details.deploymentToken,
      },
      body: JSON.stringify({
        tenant_name: details.tenantName,
        owner_email: details.ownerEmail,
        owner_display_name: details.ownerDisplayName,
        password: details.password,
      }),
    })
    if (!response.ok) {
      const messages: Record<number, string> = {
        400: 'Review the setup details and password requirements.',
        403: 'The deployment token was not accepted.',
        409: 'This installation has already been set up. Refresh to continue.',
      }
      throw new AuthRequestError(messages[response.status] ?? 'Setup was not completed.', response.status)
    }
    const result = await login(details.ownerEmail, details.password)
    if ('mfaRequired' in result) throw new AuthRequestError('Setup sign in requires an unexpected second factor.')
    return result
  },

  login,

  async completeMfaLogin(code) {
    const response = await mutation('/_allauth/browser/v1/auth/2fa/authenticate', 'POST', { code })
    if (!response.ok) {
      throw new AuthRequestError(
        response.status === 400
          ? 'That authentication or recovery code was not accepted.'
          : response.status === 429
            ? 'Too many code attempts. Wait a few minutes and try again.'
            : 'Two-factor sign in was not completed.',
        response.status,
      )
    }
    return context()
  },

  async acceptInvitation(details) {
    const response = await mutation('/api/v1/invitations/accept', 'POST', {
      token: details.token,
      display_name: details.displayName,
      password: details.password,
    })
    if (!response.ok) {
      const messages: Record<number, string> = {
        400: 'Review the account details and password requirements.',
        409: 'Sign out before accepting this invitation.',
        410: 'This invitation is no longer available. Ask the TekDocs owner for a new invitation.',
      }
      throw new AuthRequestError(messages[response.status] ?? 'The invitation was not accepted.', response.status)
    }
    return responseJson<AuthenticatedContext>(response)
  },

  async requestPasswordReset(email) {
    const response = await mutation('/_allauth/browser/v1/auth/password/request', 'POST', { email })
    if (!response.ok) {
      throw new AuthRequestError(
        response.status === 400
          ? 'Enter a valid email address.'
          : response.status === 429
            ? 'Too many reset requests. Wait before trying again.'
            : 'The reset request was not completed.',
        response.status,
      )
    }
  },

  async validatePasswordReset(key) {
    const response = await fetch('/_allauth/browser/v1/auth/password/reset', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-Password-Reset-Key': key },
    })
    if (!response.ok) throw new AuthRequestError('This password reset link is invalid or has expired.', response.status)
  },

  async completePasswordReset(key, password) {
    const response = await mutation('/_allauth/browser/v1/auth/password/reset', 'POST', { key, password })
    if (!response.ok && response.status !== 401) {
      throw new AuthRequestError(
        response.status === 400 ? 'Review the password requirements or request a new reset link.' : 'The password was not changed.',
        response.status,
      )
    }
  },

  async listOidcProviders() {
    const response = await fetch('/api/v1/auth/providers', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new AuthRequestError('Single sign-on providers could not be loaded.', response.status)
    const payload = await responseJson<{ providers?: OidcProvider[] }>(response)
    return payload.providers ?? []
  },

  async updateProfile(displayName) {
    const response = await mutation('/api/v1/auth/profile', 'PATCH', { display_name: displayName })
    if (!response.ok) {
      throw new AuthRequestError(
        response.status === 400 ? 'Enter a display name between 1 and 160 characters.' : 'Your profile could not be updated.',
        response.status,
      )
    }
    return responseJson<AuthenticatedContext>(response)
  },

  async listSessions() {
    const response = await fetch('/_allauth/browser/v1/auth/sessions', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new AuthRequestError('Active sessions could not be loaded.', response.status)
    return authSessions(await responseJson<AllauthSessionsResponse>(response))
  },

  async revokeSession(id) {
    const response = await mutation('/_allauth/browser/v1/auth/sessions', 'DELETE', { sessions: [id] })
    if (!response.ok) throw new AuthRequestError('The session could not be revoked.', response.status)
    return authSessions(await responseJson<AllauthSessionsResponse>(response))
  },

  async loadMfa() {
    const response = await fetch('/_allauth/browser/v1/account/authenticators', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new AuthRequestError('Two-factor settings could not be loaded.', response.status)
    const payload = await responseJson<AllauthAuthenticatorsResponse>(response)
    const authenticators = payload.data ?? []
    const totpEnabled = authenticators.some((item) => item.type === 'totp')
    if (!totpEnabled) return { totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 }
    const recovery = authenticators.find((item) => item.type === 'recovery_codes')
    return {
      totpEnabled: true,
      recoveryCodeTotal: recovery?.total_code_count ?? 0,
      recoveryCodeUnused: recovery?.unused_code_count ?? 0,
    }
  },

  async beginTotp() {
    const response = await fetch('/_allauth/browser/v1/account/authenticators/totp', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    const payload = await responseJson<{ meta?: { secret?: string; totp_url?: string } }>(response)
    if (response.status !== 404 || !payload.meta?.secret || !payload.meta.totp_url) {
      throw new AuthRequestError('Authenticator setup could not be started.', response.status)
    }
    return { secret: payload.meta.secret, totpUrl: payload.meta.totp_url }
  },

  async activateTotp(code) {
    const response = await mutation('/_allauth/browser/v1/account/authenticators/totp', 'POST', { code })
    if (!response.ok) throw new AuthRequestError('That authenticator code was not accepted.', response.status)
    const recoveryResponse = await fetch('/_allauth/browser/v1/account/authenticators/recovery-codes', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!recoveryResponse.ok) throw new AuthRequestError('Recovery codes could not be displayed.', recoveryResponse.status)
    return recoveryCodes(recoveryResponse)
  },

  async regenerateRecoveryCodes() {
    const response = await mutation('/_allauth/browser/v1/account/authenticators/recovery-codes', 'POST', {})
    if (!response.ok) throw new AuthRequestError('Recovery codes could not be replaced.', response.status)
    return recoveryCodes(response)
  },

  async disableTotp() {
    const response = await mutation('/_allauth/browser/v1/account/authenticators/totp', 'DELETE')
    if (!response.ok) throw new AuthRequestError('Two-factor authentication could not be disabled.', response.status)
  },

  async reauthenticate(password) {
    const response = await mutation('/_allauth/browser/v1/auth/reauthenticate', 'POST', { password })
    if (!response.ok) throw new AuthRequestError('The current password was not accepted.', response.status)
  },

  async listApiTokens() {
    const response = await fetch('/api/v1/auth/api-tokens', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new AuthRequestError('API tokens could not be loaded.', response.status)
    return responseJson<ApiTokenCatalog>(response)
  },

  async issueApiToken(input) {
    const response = await mutation('/api/v1/auth/api-tokens', 'POST', input)
    if (!response.ok) throw new AuthRequestError(response.status === 403 ? 'Enable MFA and confirm your password before issuing a token.' : 'The API token could not be issued.', response.status)
    return responseJson<IssuedApiToken>(response)
  },

  async rotateApiToken(id, expiresInDays) {
    const response = await mutation(`/api/v1/auth/api-tokens/${encodeURIComponent(id)}/rotate`, 'POST', { expires_in_days: expiresInDays })
    if (!response.ok) throw new AuthRequestError(response.status === 403 ? 'Confirm your password again before rotating this token.' : 'The API token could not be rotated.', response.status)
    return responseJson<IssuedApiToken>(response)
  },

  async revokeApiToken(id) {
    const response = await mutation(`/api/v1/auth/api-tokens/${encodeURIComponent(id)}`, 'DELETE')
    if (!response.ok) throw new AuthRequestError('The API token could not be revoked.', response.status)
    return responseJson<ApiToken>(response)
  },

  async searchTokenOrganizations(query) {
    const parameters = new URLSearchParams({ q: query, page: '1', page_size: '15' })
    const response = await fetch(`/api/v1/workspaces/organizations/search?${parameters}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new AuthRequestError('Organizations could not be searched.', response.status)
    const payload = await responseJson<{ results?: TokenOrganization[] }>(response)
    return payload.results ?? []
  },

  async logout() {
    const response = await mutation('/_allauth/browser/v1/auth/session', 'DELETE')
    if (response.status !== 401) {
      throw new AuthRequestError('Sign out was not completed.', response.status)
    }
  },
}
