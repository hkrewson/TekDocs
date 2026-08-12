import type { WorkspaceContext } from '../workspaces/api'

export type ComplianceControlRevision = {
  control_id: string
  revision_number: number
  identifier: string
  title: string
  description: string
  guidance: string
  content_digest: string
  created_at: string
}

export type ComplianceCatalogRevision = {
  revision_number: number
  version_label: string
  description: string
  source_url: string
  content_digest: string
  created_at: string
  created_by: string
  entries: { position: number; control: ComplianceControlRevision }[]
}

export type ComplianceFramework = {
  id: string
  name: string
  current_revision: ComplianceCatalogRevision
  revision_count: number
  can_manage: boolean
}

export type ComplianceControlDraft = {
  control_id?: string
  identifier: string
  title: string
  description: string
  guidance: string
}

export type ComplianceCatalogDraft = {
  version_label: string
  description: string
  source_url: string
  controls: ComplianceControlDraft[]
}

export type ComplianceFrameworkDraft = ComplianceCatalogDraft & { name: string }
export type ComplianceFrameworkResult = {
  results: ComplianceFramework[]; page: number; page_size: number; count: number; has_more: boolean; can_manage: boolean
}

export interface ComplianceClient {
  list(workspace: WorkspaceContext | null, query: string, page: number, signal?: AbortSignal): Promise<ComplianceFrameworkResult>
  create(workspace: WorkspaceContext | null, draft: ComplianceFrameworkDraft): Promise<ComplianceFramework>
  revisions(workspace: WorkspaceContext | null, frameworkId: string, signal?: AbortSignal): Promise<ComplianceCatalogRevision[]>
  createVersion(workspace: WorkspaceContext | null, frameworkId: string, draft: ComplianceCatalogDraft): Promise<ComplianceCatalogRevision>
}

function collectionPath(workspace: WorkspaceContext | null) {
  return workspace
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/compliance/frameworks`
    : '/api/v1/workspaces/msp/compliance/frameworks'
}

function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string; error?: { message?: string } }
    throw new Error(body.error?.message ?? body.detail ?? 'The compliance catalog request failed.')
  }
  return response.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse<T>(await fetch(path, {
    method: 'POST', credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: JSON.stringify(body),
  }))
}

export const browserComplianceClient: ComplianceClient = {
  async list(workspace, query, page, signal) {
    const parameters = new URLSearchParams({ q: query, page: String(page), page_size: '50' })
    return parse(await fetch(`${collectionPath(workspace)}?${parameters}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    }))
  },
  create: (workspace, draft) => post(collectionPath(workspace), draft),
  async revisions(workspace, frameworkId, signal) {
    return parse(await fetch(`${collectionPath(workspace)}/${encodeURIComponent(frameworkId)}/revisions`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    }))
  },
  createVersion: (workspace, frameworkId, draft) => post(
    `${collectionPath(workspace)}/${encodeURIComponent(frameworkId)}/revisions`, draft,
  ),
}
