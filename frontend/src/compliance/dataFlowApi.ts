import type { WorkspaceContext } from '../workspaces/api'

export type DataFlowChoice = { value: string; label: string }
export type DataFlowChoices = {
  endpoint_kinds: DataFlowChoice[]
  directions: DataFlowChoice[]
  transfer_mechanisms: DataFlowChoice[]
  data_classifications: DataFlowChoice[]
  protections: DataFlowChoice[]
  provenance_states: DataFlowChoice[]
}

export type DataFlowRevision = {
  id: string
  revision_number: number
  source_kind: string
  source_entity_id: string | null
  source_display_name: string
  source_label: string
  destination_kind: string
  destination_entity_id: string | null
  destination_display_name: string
  destination_label: string
  direction: string
  transfer_mechanism: string
  data_classification: string
  purpose: string
  crosses_trust_boundary: boolean
  protection: string
  owner_entity_id: string | null
  owner_display_name: string
  review_due_on: string | null
  provenance: string
  content_digest: string
  created_at: string
}

export type DataFlow = {
  id: string
  name: string
  revision_count: number
  current_revision: DataFlowRevision | null
  created_at: string
  updated_at: string
}

export type DataFlowResult = {
  results: DataFlow[]
  page: number
  page_size: number
  count: number
  has_more: boolean
  can_manage: boolean
}

export type DataFlowDraft = {
  name: string
  source_kind: string
  source_entity_id?: string | null
  source_label?: string
  destination_kind: string
  destination_entity_id?: string | null
  destination_label?: string
  direction: string
  transfer_mechanism: string
  data_classification: string
  purpose: string
  crosses_trust_boundary: boolean
  protection: string
  owner_entity_id?: string | null
  review_due_on?: string | null
  provenance: string
}

export interface DataFlowClient {
  list(workspace: WorkspaceContext | null, page: number, signal?: AbortSignal): Promise<DataFlowResult>
  choices(workspace: WorkspaceContext | null, signal?: AbortSignal): Promise<DataFlowChoices>
  revisions(workspace: WorkspaceContext | null, id: string): Promise<{ results: DataFlowRevision[]; count: number }>
  create(workspace: WorkspaceContext | null, draft: DataFlowDraft): Promise<DataFlow>
  revise(workspace: WorkspaceContext | null, id: string, draft: DataFlowDraft): Promise<DataFlow>
  archive(workspace: WorkspaceContext | null, id: string): Promise<void>
}

function collectionPath(workspace: WorkspaceContext | null) {
  return workspace
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/compliance/data-flows`
    : '/api/v1/workspaces/msp/compliance/data-flows'
}

function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string
      error?: { fields?: Record<string, string[]>; message?: string }
    }
    // The server states why it refused a flow — an endpoint outside the workspace, an
    // unnamed external party. Replacing that with a generic sentence would leave the
    // author guessing at a rule the server already spelled out.
    const field = Object.values(body.error?.fields ?? {})[0]?.[0]
    throw new Error(field ?? body.detail ?? body.error?.message ?? 'The data-flow request was not completed.')
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

export const browserDataFlowClient: DataFlowClient = {
  async list(workspace, page, signal) {
    const parameters = new URLSearchParams({ page: String(page), page_size: '50' })
    return parse<DataFlowResult>(
      await fetch(`${collectionPath(workspace)}?${parameters}`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        signal,
      }),
    )
  },
  async choices(workspace, signal) {
    return parse<DataFlowChoices>(
      await fetch(`${collectionPath(workspace)}/choices`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        signal,
      }),
    )
  },
  async revisions(workspace, id) {
    return parse<{ results: DataFlowRevision[]; count: number }>(
      await fetch(`${collectionPath(workspace)}/${encodeURIComponent(id)}/revisions`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      }),
    )
  },
  create: (workspace, draft) => mutate(collectionPath(workspace), 'POST', draft),
  revise: (workspace, id, draft) => mutate(`${collectionPath(workspace)}/${encodeURIComponent(id)}`, 'PATCH', draft),
  archive: (workspace, id) => mutate(`${collectionPath(workspace)}/${encodeURIComponent(id)}`, 'DELETE'),
}
