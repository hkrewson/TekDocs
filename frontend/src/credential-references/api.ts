import type { WorkspaceContext } from '../workspaces/api'

export type CredentialReference = {
  id: string
  title: string
  provider: 'onepassword'
  provider_label: string
  updated_at: string
  can_manage: boolean
  can_open: boolean
}

export type CredentialReferenceResult = { results: CredentialReference[]; page: number; page_size: number; count: number; has_more: boolean; can_manage: boolean }
export type CredentialReferenceDraft = { title: string; provider: 'onepassword'; reference_url: string }

export interface CredentialReferencesClient {
  list(workspace: WorkspaceContext | null, query: string, page: number, signal?: AbortSignal): Promise<CredentialReferenceResult>
  create(workspace: WorkspaceContext | null, draft: CredentialReferenceDraft): Promise<CredentialReference>
  update(workspace: WorkspaceContext | null, id: string, draft: Partial<Pick<CredentialReferenceDraft, 'title' | 'reference_url'>>): Promise<CredentialReference>
  archive(workspace: WorkspaceContext | null, id: string): Promise<void>
  openUrl(workspace: WorkspaceContext | null, id: string): string
}

function collectionPath(workspace: WorkspaceContext | null) {
  return workspace ? `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/credential-references` : '/api/v1/credential-references'
}

function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string; reference_url?: string[] }
    throw new Error(body.reference_url?.[0] ?? body.detail ?? 'The credential-reference request failed.')
  }
  return response.json() as Promise<T>
}

async function mutate<T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (method === 'DELETE' && response.ok) return undefined as T
  return parse<T>(response)
}

export const browserCredentialReferencesClient: CredentialReferencesClient = {
  async list(workspace, query, page, signal) {
    const parameters = new URLSearchParams({ q: query, page: String(page), page_size: '50' })
    return parse<CredentialReferenceResult>(await fetch(`${collectionPath(workspace)}?${parameters}`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
  },
  create: (workspace, draft) => mutate(collectionPath(workspace), 'POST', draft),
  update: (workspace, id, draft) => mutate(`${collectionPath(workspace)}/${encodeURIComponent(id)}`, 'PATCH', draft),
  archive: (workspace, id) => mutate(`${collectionPath(workspace)}/${encodeURIComponent(id)}`, 'DELETE'),
  openUrl: (workspace, id) => `${collectionPath(workspace)}/${encodeURIComponent(id)}/open`,
}
