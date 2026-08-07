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
}

export type BootstrapDetails = {
  deploymentToken: string
  tenantName: string
  ownerEmail: string
  ownerDisplayName: string
  password: string
}

export interface AuthClient {
  load(): Promise<{ bootstrapRequired: boolean; context: AuthenticatedContext | null }>
  bootstrapAndLogin(details: BootstrapDetails): Promise<AuthenticatedContext>
  login(email: string, password: string): Promise<AuthenticatedContext>
  logout(): Promise<void>
}

type AllauthSessionResponse = {
  meta?: { is_authenticated?: boolean }
}

export class AuthRequestError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message)
    this.name = 'AuthRequestError'
  }
}

function csrfToken(): string | null {
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

async function mutation(path: string, method: 'POST' | 'DELETE', body?: object): Promise<Response> {
  if (!csrfToken()) await session()
  const token = csrfToken()
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

async function login(email: string, password: string): Promise<AuthenticatedContext> {
  const response = await mutation('/_allauth/browser/v1/auth/login', 'POST', { email, password })
  if (!response.ok) {
    throw new AuthRequestError(
      response.status === 400 ? 'The email address or password is incorrect.' : 'Sign in was not completed.',
      response.status,
    )
  }
  return context()
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
    return login(details.ownerEmail, details.password)
  },

  login,

  async logout() {
    const response = await mutation('/_allauth/browser/v1/auth/session', 'DELETE')
    if (response.status !== 401) {
      throw new AuthRequestError('Sign out was not completed.', response.status)
    }
  },
}
