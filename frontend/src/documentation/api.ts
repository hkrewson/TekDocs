import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type DocumentScope = { organizationId?: string }
export type PlacementResolutionMode = 'live' | 'pinned'
export type DocumentPlacement = {
  id: string
  parent_id: string | null
  block_id: string
  block_name: string
  position: number
  depth: number
  resolution_mode: PlacementResolutionMode
  pinned_revision_id: string | null
  resolved_revision_id: string
  resolved_revision_number: number
  resolved_checksum: string
  is_primary: boolean
}
export type DocumentRecord = {
  id: string
  title: string
  owner_kind: 'msp' | 'organization'
  owner_organization_id: string | null
  owner_organization_name: string | null
  is_reference: boolean
  markdown: string
  block_id: string
  current_revision_id: string
  revision_number: number
  checksum: string
  resolved_markdown: string
  placements: DocumentPlacement[]
  placement_count: number
  created_at: string
  updated_at: string
}
export type DocumentInput = Pick<DocumentRecord, 'title' | 'markdown'>
export type DocumentUpdateInput = DocumentInput & { base_revision_id: string }
export type DocumentResult = { results: DocumentRecord[]; count: number }
export type BlockRevision = {
  id: string
  parent_id: string | null
  revision_number: number
  checksum: string
  created_by: string | null
  created_at: string
  is_current: boolean
}
export type BlockRevisionDetail = BlockRevision & { markdown: string; diff_from_parent: string }
export type RevisionResult = { results: BlockRevision[]; count: number }
export type RevisionConflictPayload = {
  code: 'revision_conflict'
  detail: string
  submitted_base_revision_id: string
  current_revision: BlockRevisionDetail
  diff: string
}
export type PlacementConflictPayload = { code: 'placement_conflict'; detail: string }
export type PlacementInput = {
  source_document_id: string
  resolution_mode: PlacementResolutionMode
  pinned_revision_id?: string | null
  parent_id?: string | null
}
export type PlacementUpdateInput = {
  resolution_mode: PlacementResolutionMode
  pinned_revision_id?: string | null
}
export type ReuseAudience = {
  relationship: 'source' | 'placement' | 'listing'
  document_id: string
  document_title: string
  workspace_kind: 'msp' | 'organization'
  workspace_id: string
  workspace_name: string
  resolution_mode: PlacementResolutionMode | null
  will_update: boolean
}
export type ReuseImpact = {
  block_id: string
  block_name: string
  revision_id: string
  revision_number: number
  checksum: string
  markdown: string
  audiences: ReuseAudience[]
  live_audience_count: number
  pinned_audience_count: number
  can_edit_shared: boolean
  can_detach: boolean
  requires_mfa: boolean
  truncated: boolean
}
export type EntityMentionOption = {
  id: string
  entity_type: string
  display_name: string
  workspace_label: string
}
export type EntityMentionResult = { results: EntityMentionOption[]; count: number; has_more: boolean }

export class RevisionConflictError extends AuthRequestError {
  constructor(readonly payload: RevisionConflictPayload) {
    super('This document changed in another session. Your draft was not overwritten.', 409)
    this.name = 'RevisionConflictError'
  }
}

export interface DocumentsClient {
  list(scope: DocumentScope, signal?: AbortSignal): Promise<DocumentResult>
  create(scope: DocumentScope, input: DocumentInput): Promise<DocumentRecord>
  update(scope: DocumentScope, id: string, input: DocumentUpdateInput): Promise<DocumentRecord>
  listRevisions(scope: DocumentScope, id: string): Promise<RevisionResult>
  getRevision(scope: DocumentScope, id: string, revisionId: string): Promise<BlockRevisionDetail>
  addPlacement(scope: DocumentScope, id: string, input: PlacementInput): Promise<DocumentRecord>
  updatePlacement(scope: DocumentScope, id: string, placementId: string, input: PlacementUpdateInput): Promise<DocumentRecord>
  removePlacement(scope: DocumentScope, id: string, placementId: string): Promise<DocumentRecord>
  getReuseImpact(scope: DocumentScope, id: string, placementId: string): Promise<ReuseImpact>
  updateSharedBlock(scope: DocumentScope, id: string, placementId: string, markdown: string, baseRevisionId: string): Promise<DocumentRecord>
  detachPlacement(scope: DocumentScope, id: string, placementId: string): Promise<DocumentRecord>
  searchMentionEntities(scope: DocumentScope, query: string, signal?: AbortSignal): Promise<EntityMentionResult>
  archive(scope: DocumentScope, id: string): Promise<void>
  addReference(documentId: string, organizationId: string): Promise<void>
}

function collectionPath(scope: DocumentScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/documents`
    : '/api/v1/documents'
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

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 409) {
      const payload = await response.json() as RevisionConflictPayload | PlacementConflictPayload
      if (payload.code === 'revision_conflict') throw new RevisionConflictError(payload)
      if (payload.code === 'placement_conflict') throw new AuthRequestError(payload.detail, 409)
    }
    const message = response.status === 403
      ? 'Your account is not authorized to change documentation in this workspace.'
      : response.status === 404
        ? 'That document or workspace is no longer available.'
        : 'The documentation request was not completed.'
    throw new AuthRequestError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function mutate<T>(path: string, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', body?: object) {
  return parse<T>(await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    body: body ? JSON.stringify(body) : undefined,
  }))
}

export const browserDocumentsClient: DocumentsClient = {
  async list(scope, signal) {
    const response = await fetch(collectionPath(scope), { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    return parse<DocumentResult>(response)
  },
  create: (scope, input) => mutate<DocumentRecord>(collectionPath(scope), 'POST', input),
  update: (scope, id, input) => mutate<DocumentRecord>(`${collectionPath(scope)}/${encodeURIComponent(id)}`, 'PUT', input),
  async listRevisions(scope, id) {
    return parse<RevisionResult>(await fetch(`${collectionPath(scope)}/${encodeURIComponent(id)}/revisions`, { credentials: 'same-origin', headers: { Accept: 'application/json' } }))
  },
  async getRevision(scope, id, revisionId) {
    return parse<BlockRevisionDetail>(await fetch(`${collectionPath(scope)}/${encodeURIComponent(id)}/revisions/${encodeURIComponent(revisionId)}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } }))
  },
  addPlacement: (scope, id, input) => mutate<DocumentRecord>(`${collectionPath(scope)}/${encodeURIComponent(id)}/placements`, 'POST', input),
  updatePlacement: (scope, id, placementId, input) => mutate<DocumentRecord>(`${collectionPath(scope)}/${encodeURIComponent(id)}/placements/${encodeURIComponent(placementId)}`, 'PATCH', input),
  removePlacement: (scope, id, placementId) => mutate<DocumentRecord>(`${collectionPath(scope)}/${encodeURIComponent(id)}/placements/${encodeURIComponent(placementId)}`, 'DELETE'),
  async getReuseImpact(scope, id, placementId) {
    return parse<ReuseImpact>(await fetch(`${collectionPath(scope)}/${encodeURIComponent(id)}/placements/${encodeURIComponent(placementId)}/reuse`, { credentials: 'same-origin', headers: { Accept: 'application/json' } }))
  },
  updateSharedBlock: (scope, id, placementId, markdown, baseRevisionId) => mutate<DocumentRecord>(`${collectionPath(scope)}/${encodeURIComponent(id)}/placements/${encodeURIComponent(placementId)}/reuse`, 'PUT', { markdown, base_revision_id: baseRevisionId }),
  detachPlacement: (scope, id, placementId) => mutate<DocumentRecord>(`${collectionPath(scope)}/${encodeURIComponent(id)}/placements/${encodeURIComponent(placementId)}/detach`, 'POST'),
  async searchMentionEntities(scope, query, signal) {
    return parse<EntityMentionResult>(await fetch(`${collectionPath(scope)}/mention-entities?q=${encodeURIComponent(query)}&page_size=20`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
  },
  archive: (scope, id) => mutate<void>(`${collectionPath(scope)}/${encodeURIComponent(id)}`, 'DELETE'),
  addReference: (documentId, organizationId) => mutate<void>(`/api/v1/documents/${encodeURIComponent(documentId)}/references`, 'POST', { organization_id: organizationId }),
}
