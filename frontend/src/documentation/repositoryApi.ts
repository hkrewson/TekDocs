import { browserCsrfToken } from '../auth/api'
import { translate } from '../i18n/localization'

export type RepositorySummary = {
  id: string
  title: string
  kind: 'document' | 'fragment'
  path: string
}

export type RepositoryListing = {
  results: RepositorySummary[]
  accepted_commit: string | null
  indexed_commit: string | null
  count: number
  has_more: boolean
}

export type RepositorySource = {
  content_id: string
  path: string
  kind: 'document' | 'fragment'
  title: string
  markdown: string
  source: string
  source_blob: string
  accepted_commit: string | null
  indexed_commit: string | null
}

export type RepositoryMutation = {
  operation: 'create' | 'update' | 'move'
  content_id: string
  base_commit: string | null
  base_blob?: string | null
  kind?: 'document' | 'fragment'
  path?: string | null
  title?: string
  markdown?: string
  metadata_patch?: Record<string, unknown>
}

export type RepositoryConflict = {
  reason: string
  base: string | null
  current: string | null
  proposed: string | null
  base_commit: string | null
  current_commit: string | null
  current_blob: string | null
}

export class RepositoryConflictError extends Error {
  constructor(public readonly conflict: RepositoryConflict) {
    super('Repository source changed')
  }
}

function path(organizationId?: string) {
  return organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(organizationId)}/content-graph`
    : '/api/v1/workspaces/msp/content-graph'
}

async function token() {
  let value = browserCsrfToken()
  if (!value) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    value = browserCsrfToken()
  }
  if (!value) throw new Error(translate('repository.tokenUnavailable'))
  return value
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  if (response.status === 409) throw new RepositoryConflictError(await response.json() as RepositoryConflict)
  let detail: unknown
  try { detail = (await response.json() as { detail?: unknown }).detail } catch { /* An upstream error may be HTML. */ }
  throw new Error(typeof detail === 'string' && detail.length < 300 ? detail : translate('repository.requestFailed', { status: response.status }))
}

export const browserRepositoryClient = {
  async list(organizationId?: string, q = '', signal?: AbortSignal) {
    const query = new URLSearchParams({ page_size: '100' })
    if (q) query.set('q', q)
    const response = await fetch(`${path(organizationId)}/documents?${query}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    return parse<RepositoryListing>(response)
  },
  async source(contentId: string, organizationId?: string, signal?: AbortSignal) {
    const response = await fetch(`${path(organizationId)}/authoring/${encodeURIComponent(contentId)}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    })
    return parse<RepositorySource>(response)
  },
  async save(mutation: RepositoryMutation, organizationId?: string) {
    const response = await fetch(`${path(organizationId)}/authoring`, {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await token() },
      body: JSON.stringify(mutation),
    })
    return parse<RepositorySource>(response)
  },
}

export type RepositoryClient = typeof browserRepositoryClient
