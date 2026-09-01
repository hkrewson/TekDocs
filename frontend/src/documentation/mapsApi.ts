import { browserCsrfToken, privilegedActionError } from '../auth/api'
import type { WorkspaceContext } from '../workspaces/api'

export type MapAudience = 'msp_internal' | 'client_visible'
export type MapType = 'operating_manual' | 'disaster_recovery' | 'onboarding' | 'compliance' | 'handoff' | 'general'
export type MapEntryKind = 'document' | 'document_revision' | 'publication' | 'map' | 'external'
export type MapChoice = { id: string; title: string; kind: string; detail: string; current_revision_id?: string | null }
export type MapChoices = { documents: MapChoice[]; publications: MapChoice[]; maps: MapChoice[]; owners: MapChoice[] }
export type MapEntry = { id: string; parent_id: string | null; position: number; kind: MapEntryKind; label: string; title: string; document_id: string | null; document_revision_id: string | null; publication_id: string | null; map_id: string | null; external_url: string }
export type MapRevision = { id: string; revision_number: number; title: string; purpose: string; map_type: MapType; audience: MapAudience; content_digest: string; created_by: string; created_at: string; entries: MapEntry[] }
export type MapBaseline = { id: string; revision_id: string; revision_number: number; content_digest: string; byte_size: number; formats: string[]; created_by: string; created_at: string }
export type DocumentationMap = { id: string; title: string; purpose: string; map_type: MapType; audience: MapAudience; owner_id: string | null; owner_name: string | null; review_state: 'unreviewed' | 'approved' | 'changes_requested'; current_revision: MapRevision; revision_count: number; baselines: MapBaseline[]; created_at: string; updated_at: string }
export type MapEntryInput = { parent_index: number | null; position: number; kind: MapEntryKind; label: string; document_id?: string | null; document_revision_id?: string | null; publication_id?: string | null; map_id?: string | null; external_url?: string }
export type MapInput = { title: string; purpose: string; map_type: MapType; audience: MapAudience; owner_id: string | null; entries: MapEntryInput[] }
export type MapFinding = { code: string; severity: 'information' | 'warning' | 'blocker'; entry_id: string | null; detail: string }
export type MapPreview = { map: DocumentationMap; findings: MapFinding[]; blocker_count: number; warning_count: number }

function base(workspace: WorkspaceContext | null) {
  return workspace ? `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/documentation-maps` : '/api/v1/documentation-maps'
}

async function csrfToken() {
  let token = browserCsrfToken()
  if (token) return token
  await fetch('/api/v1/auth/csrf', { credentials: 'same-origin' })
  token = browserCsrfToken()
  if (!token) throw new Error('A secure session could not be prepared.')
  return token
}

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = ''
    try {
      const payload = await response.clone().json() as { detail?: string; error?: { detail?: string; fields?: Record<string, string[]> } }
      detail = payload.detail ?? payload.error?.detail ?? Object.values(payload.error?.fields ?? {}).flat()[0] ?? ''
    } catch { /* use the safe fallback */ }
    throw await privilegedActionError(response, detail || 'The documentation map request was not completed.')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function mutate<T>(path: string, method: 'POST' | 'PUT' | 'DELETE', body?: object) {
  return decode<T>(await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    body: body ? JSON.stringify(body) : undefined,
  }))
}

export const documentationMapsClient = {
  async list(workspace: WorkspaceContext | null) { return decode<{ results: DocumentationMap[]; count: number }>(await fetch(base(workspace), { credentials: 'same-origin' })) },
  async choices(workspace: WorkspaceContext | null) { return decode<MapChoices>(await fetch(`${base(workspace)}/choices`, { credentials: 'same-origin' })) },
  create(workspace: WorkspaceContext | null, input: MapInput) { return mutate<DocumentationMap>(base(workspace), 'POST', input) },
  update(workspace: WorkspaceContext | null, id: string, input: MapInput, revisionId: string) { return mutate<DocumentationMap>(`${base(workspace)}/${encodeURIComponent(id)}`, 'PUT', { ...input, expected_revision_id: revisionId }) },
  archive(workspace: WorkspaceContext | null, id: string) { return mutate<void>(`${base(workspace)}/${encodeURIComponent(id)}`, 'DELETE') },
  review(workspace: WorkspaceContext | null, id: string, state: 'approved' | 'changes_requested') { return mutate<DocumentationMap>(`${base(workspace)}/${encodeURIComponent(id)}/review`, 'POST', { state }) },
  async preview(workspace: WorkspaceContext | null, id: string) { return decode<MapPreview>(await fetch(`${base(workspace)}/${encodeURIComponent(id)}/preview`, { credentials: 'same-origin' })) },
  baseline(workspace: WorkspaceContext | null, id: string, revisionId: string, formats: string[]) { return mutate<MapBaseline>(`${base(workspace)}/${encodeURIComponent(id)}/baselines`, 'POST', { expected_revision_id: revisionId, formats }) },
  baselineUrl(workspace: WorkspaceContext | null, id: string, baselineId: string) { return `${base(workspace)}/${encodeURIComponent(id)}/baselines/${encodeURIComponent(baselineId)}/download` },
}
