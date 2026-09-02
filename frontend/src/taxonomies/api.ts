import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type TaxonomyBinding = 'document_tags' | 'technology' | 'service_family' | 'platform' | 'risk_level' | 'support_tier' | 'compliance_domain' | 'document_subject'
export type TaxonomyTerm = {
  id: string
  stable_key: string
  label: string
  description: string
  parent_key: string
  aliases: string[]
  status: 'active' | 'retired'
  replacement_key: string
  sort_order: number
  local?: boolean
  impact?: { documents: number; templates: number }
}
export type TaxonomyVersionInput = {
  label: string
  description: string
  allow_local_terms: boolean
  terms: Omit<TaxonomyTerm, 'id' | 'impact'>[]
}
export type Taxonomy = {
  id: string
  key: string
  binding: TaxonomyBinding
  archived: boolean
  current_version: Omit<TaxonomyVersionInput, 'terms'> & { id: string; version: number; created_at: string; terms: TaxonomyTerm[] }
  versions: { id: string; version: number; label: string; created_at: string }[]
  impact: { documents: number; templates: number }
}
export type TaxonomyInput = TaxonomyVersionInput & { key: string; binding: TaxonomyBinding }
export type TaxonomyResult = { results: Taxonomy[]; count: number }
export type TaxonomyMigration = {
  counts: { matched: number; unmatched: number; ambiguous: number }
  rows: { document_id: string; document_title: string; tag: string; status: 'matched' | 'unmatched' | 'ambiguous'; term_id: string | null; term_label: string | null }[]
}

export interface TaxonomiesClient {
  list(organizationId?: string, signal?: AbortSignal): Promise<TaxonomyResult>
  create(input: TaxonomyInput): Promise<Taxonomy>
  revise(id: string, input: TaxonomyVersionInput): Promise<Taxonomy>
  archive(id: string): Promise<void>
  migration(apply: boolean): Promise<TaxonomyMigration>
  createLocalTerm?(organizationId: string, taxonomyId: string, input: { stable_key: string; label: string; description: string; aliases: string[] }): Promise<Taxonomy>
}

async function decode<T>(response: Response): Promise<T> {
  try { return await response.json() as T } catch { throw new AuthRequestError('The server returned an unreadable taxonomy response.', response.status) }
}

async function csrfToken() {
  let token = browserCsrfToken()
  if (!token) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    token = browserCsrfToken()
  }
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  return token
}

async function mutation<T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const payload: { detail?: string } = await decode<{ detail?: string }>(response).catch(() => ({}))
    throw new AuthRequestError(payload.detail ?? 'The taxonomy change was not completed.', response.status)
  }
  return response.status === 204 ? undefined as T : decode<T>(response)
}

export const browserTaxonomiesClient: TaxonomiesClient = {
  async list(organizationId, signal) {
    const path = organizationId ? `/api/v1/workspaces/organizations/${encodeURIComponent(organizationId)}/taxonomies` : '/api/v1/taxonomies'
    const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    if (!response.ok) throw new AuthRequestError('Taxonomies could not be loaded.', response.status)
    return decode<TaxonomyResult>(response)
  },
  create: (input) => mutation<Taxonomy>('/api/v1/taxonomies', 'POST', input),
  revise: (id, input) => mutation<Taxonomy>(`/api/v1/taxonomies/${encodeURIComponent(id)}`, 'PATCH', input),
  archive: (id) => mutation<void>(`/api/v1/taxonomies/${encodeURIComponent(id)}`, 'DELETE'),
  migration: (apply) => mutation<TaxonomyMigration>('/api/v1/taxonomies/migration', 'POST', { apply }),
  createLocalTerm: (organizationId, taxonomyId, input) => mutation<Taxonomy>(`/api/v1/workspaces/organizations/${encodeURIComponent(organizationId)}/taxonomies/${encodeURIComponent(taxonomyId)}/terms`, 'POST', input),
}
