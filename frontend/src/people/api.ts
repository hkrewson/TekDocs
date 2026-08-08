import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type PersonKind = 'employee' | 'contact'
export type PersonSortField = 'full_name' | 'preferred_name' | 'kind' | 'role' | 'responsibility' | 'location' | 'office' | 'phone' | 'email'
export type PersonFilterField = Exclude<PersonSortField, 'full_name'>

export type PersonRecord = {
  id: string
  association_id: string
  organization_id: string | null
  full_name: string
  preferred_name: string
  kind: PersonKind
  role: string
  responsibility: string
  location: string
  office: string
  site_id: string | null
  structured_location_id: string | null
  phone: string
  email: string
  created_at: string
  updated_at: string
}

export type PersonInput = Pick<PersonRecord, 'full_name' | 'preferred_name' | 'kind' | 'role' | 'responsibility' | 'location' | 'office' | 'site_id' | 'structured_location_id' | 'phone' | 'email'>

export type PeopleQuery = {
  q: string
  filter_field: PersonFilterField | ''
  filter_value: string
  ordering: PersonSortField | `-${PersonSortField}`
  page: number
  page_size: number
}

export type PeopleResult = {
  results: PersonRecord[]
  page: number
  page_size: number
  count: number
  has_more: boolean
}

export type PeopleScope = { organizationId?: string }

export interface PeopleClient {
  list(scope: PeopleScope, query: PeopleQuery, signal?: AbortSignal): Promise<PeopleResult>
  create(scope: PeopleScope, input: PersonInput): Promise<PersonRecord>
  update(scope: PeopleScope, id: string, input: PersonInput): Promise<PersonRecord>
  archive(scope: PeopleScope, id: string): Promise<void>
}

function collectionPath(scope: PeopleScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/people`
    : '/api/v1/people'
}

function detailPath(scope: PeopleScope, id: string) {
  return `${collectionPath(scope)}/${encodeURIComponent(id)}`
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

function writeError(response: Response): AuthRequestError {
  const message = response.status === 400
    ? 'Review the person and contact details.'
    : response.status === 403
      ? 'Your account is not authorized to manage people in this workspace.'
      : response.status === 404
        ? 'That person or workspace is no longer available.'
        : 'The person change was not completed.'
  return new AuthRequestError(message, response.status)
}

async function mutation(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: PersonInput) {
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

export const browserPeopleClient: PeopleClient = {
  async list(scope, query, signal) {
    const params = new URLSearchParams({
      ordering: query.ordering,
      page: String(query.page),
      page_size: String(query.page_size),
    })
    if (query.q) params.set('q', query.q)
    if (query.filter_field && query.filter_value) {
      params.set('filter_field', query.filter_field)
      params.set('filter_value', query.filter_value)
    }
    const response = await fetch(`${collectionPath(scope)}?${params}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (!response.ok) throw new AuthRequestError('People could not be loaded.', response.status)
    return json<PeopleResult>(response)
  },

  async create(scope, input) {
    const response = await mutation(collectionPath(scope), 'POST', input)
    if (!response.ok) throw writeError(response)
    return json<PersonRecord>(response)
  },

  async update(scope, id, input) {
    const response = await mutation(detailPath(scope, id), 'PATCH', input)
    if (!response.ok) throw writeError(response)
    return json<PersonRecord>(response)
  },

  async archive(scope, id) {
    const response = await mutation(detailPath(scope, id), 'DELETE')
    if (!response.ok) throw writeError(response)
  },
}
