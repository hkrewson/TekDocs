import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type LocationKind = 'building' | 'floor' | 'suite' | 'room' | 'office' | 'desk' | 'area'

export type LocationRecord = {
  id: string
  site_id: string
  parent_id: string | null
  name: string
  kind: LocationKind
  code: string
  created_at: string
  updated_at: string
}

export type SiteRecord = {
  id: string
  organization_id: string | null
  name: string
  code: string
  address_line_1: string
  address_line_2: string
  city: string
  region: string
  postal_code: string
  country_code: string
  timezone: string
  phone: string
  locations: LocationRecord[]
  created_at: string
  updated_at: string
}

export type SiteInput = Pick<SiteRecord, 'name' | 'code' | 'address_line_1' | 'address_line_2' | 'city' | 'region' | 'postal_code' | 'country_code' | 'timezone' | 'phone'>
export type LocationInput = Pick<LocationRecord, 'name' | 'kind' | 'code' | 'parent_id'>
export type SiteScope = { organizationId?: string }
export type SiteResult = { results: SiteRecord[]; count: number }

export interface SitesClient {
  list(scope: SiteScope, query?: string, signal?: AbortSignal): Promise<SiteResult>
  create(scope: SiteScope, input: SiteInput): Promise<SiteRecord>
  update(scope: SiteScope, id: string, input: Partial<SiteInput>): Promise<SiteRecord>
  archive(scope: SiteScope, id: string): Promise<void>
  createLocation(scope: SiteScope, siteId: string, input: LocationInput): Promise<LocationRecord>
  updateLocation(scope: SiteScope, siteId: string, id: string, input: Partial<LocationInput>): Promise<LocationRecord>
  archiveLocation(scope: SiteScope, siteId: string, id: string): Promise<void>
}

function collectionPath(scope: SiteScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/sites`
    : '/api/v1/sites'
}

function sitePath(scope: SiteScope, id: string) {
  return `${collectionPath(scope)}/${encodeURIComponent(id)}`
}

function locationPath(scope: SiteScope, siteId: string, id?: string) {
  const base = `${sitePath(scope, siteId)}/locations`
  return id ? `${base}/${encodeURIComponent(id)}` : base
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
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    token = browserCsrfToken()
  }
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  return token
}

function writeError(response: Response) {
  const message = response.status === 400
    ? 'Review the site or location details.'
    : response.status === 403
      ? 'Your account is not authorized to manage sites in this workspace.'
      : response.status === 404
        ? 'That site, location, or workspace is no longer available.'
        : 'The site change was not completed.'
  return new AuthRequestError(message, response.status)
}

async function mutation(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: SiteInput | Partial<SiteInput> | LocationInput | Partial<LocationInput>) {
  return fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    body: body ? JSON.stringify(body) : undefined,
  })
}

export const browserSitesClient: SitesClient = {
  async list(scope, query = '', signal) {
    const parameters = new URLSearchParams()
    if (query) parameters.set('q', query)
    const suffix = parameters.size ? `?${parameters}` : ''
    const response = await fetch(`${collectionPath(scope)}${suffix}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (!response.ok) throw new AuthRequestError('Sites could not be loaded.', response.status)
    return json<SiteResult>(response)
  },
  async create(scope, input) {
    const response = await mutation(collectionPath(scope), 'POST', input)
    if (!response.ok) throw writeError(response)
    return json<SiteRecord>(response)
  },
  async update(scope, id, input) {
    const response = await mutation(sitePath(scope, id), 'PATCH', input)
    if (!response.ok) throw writeError(response)
    return json<SiteRecord>(response)
  },
  async archive(scope, id) {
    const response = await mutation(sitePath(scope, id), 'DELETE')
    if (!response.ok) throw writeError(response)
  },
  async createLocation(scope, siteId, input) {
    const response = await mutation(locationPath(scope, siteId), 'POST', input)
    if (!response.ok) throw writeError(response)
    return json<LocationRecord>(response)
  },
  async updateLocation(scope, siteId, id, input) {
    const response = await mutation(locationPath(scope, siteId, id), 'PATCH', input)
    if (!response.ok) throw writeError(response)
    return json<LocationRecord>(response)
  },
  async archiveLocation(scope, siteId, id) {
    const response = await mutation(locationPath(scope, siteId, id), 'DELETE')
    if (!response.ok) throw writeError(response)
  },
}
