import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type OrganizationClassification = 'client' | 'vendor' | 'manufacturer' | 'partner'

export type Organization = {
  id: string
  name: string
  legal_name: string
  website: string
  classifications: OrganizationClassification[]
  created_at: string
  updated_at: string
}

export type OrganizationInput = Pick<Organization, 'name' | 'legal_name' | 'website' | 'classifications'>

export interface OrganizationClient {
  list(): Promise<Organization[]>
  create(input: OrganizationInput): Promise<Organization>
  update(id: string, input: OrganizationInput): Promise<Organization>
  archive(id: string): Promise<void>
}

async function json<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T
  } catch {
    throw new AuthRequestError('The server returned an unreadable response.', response.status)
  }
}

async function csrfToken(): Promise<string> {
  let token = browserCsrfToken()
  if (!token) {
    await fetch('/_allauth/browser/v1/auth/session', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    token = browserCsrfToken()
  }
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  return token
}

async function mutation(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: OrganizationInput) {
  return fetch(path, {
    method,
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': await csrfToken(),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
}

function writeError(response: Response): AuthRequestError {
  const message = response.status === 400
    ? 'Review the organization name, website, and classifications.'
    : response.status === 403
      ? 'Your account is not authorized for organization administration.'
      : response.status === 404
        ? 'That organization is no longer available.'
        : 'The organization change was not completed.'
  return new AuthRequestError(message, response.status)
}

export const browserOrganizationClient: OrganizationClient = {
  async list() {
    const response = await fetch('/api/v1/organizations', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new AuthRequestError('Organizations could not be loaded.', response.status)
    return json<Organization[]>(response)
  },

  async create(input) {
    const response = await mutation('/api/v1/organizations', 'POST', input)
    if (!response.ok) throw writeError(response)
    return json<Organization>(response)
  },

  async update(id, input) {
    const response = await mutation(`/api/v1/organizations/${encodeURIComponent(id)}`, 'PATCH', input)
    if (!response.ok) throw writeError(response)
    return json<Organization>(response)
  },

  async archive(id) {
    const response = await mutation(`/api/v1/organizations/${encodeURIComponent(id)}`, 'DELETE')
    if (!response.ok) throw writeError(response)
  },
}
