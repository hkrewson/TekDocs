import type { WorkspaceContext } from '../workspaces/api'

export type RegisteredDomain = {
  id: string
  name: string
  registrar_id: string | null
  registrar: string | null
  registration_date: string | null
  expiration_date: string | null
  renewal_mode: 'manual' | 'auto' | 'external'
  owner_id: string | null
  owner: string | null
  status: 'active' | 'pending' | 'expired' | 'transferred'
  notes: string
  created_at: string
}

export type DomainDraft = Pick<RegisteredDomain, 'name' | 'registrar_id' | 'registration_date' | 'expiration_date' | 'renewal_mode' | 'owner_id' | 'status' | 'notes'>

export interface DomainsClient {
  list(workspace: WorkspaceContext | null, signal?: AbortSignal): Promise<RegisteredDomain[]>
  create(workspace: WorkspaceContext | null, draft: DomainDraft): Promise<RegisteredDomain>
}

function path(workspace: WorkspaceContext | null) {
  return workspace
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/domains`
    : '/api/v1/workspaces/msp/domains'
}

function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string; error?: { message?: string } }
    throw new Error(body.error?.message ?? body.detail ?? 'The domain request failed.')
  }
  return response.json() as Promise<T>
}

export const browserDomainsClient: DomainsClient = {
  async list(workspace, signal) {
    return parse(await fetch(path(workspace), { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
  },
  async create(workspace, draft) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    return parse(await fetch(path(workspace), {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(draft),
    }))
  },
}
