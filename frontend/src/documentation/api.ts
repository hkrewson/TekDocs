import { AuthRequestError, browserCsrfToken, privilegedActionError } from '../auth/api'

export type DocumentScope = { organizationId?: string }
export type DocumentCategory = 'general' | 'policy' | 'procedure' | 'guide' | 'reference'
export type DocumentFilters = { q?: string; category?: DocumentCategory | ''; template?: 'all' | 'documents' | 'templates' }
export type PlacementResolutionMode = 'live' | 'pinned'
export type BlockKind = 'rich_text' | 'heading' | 'code' | 'url' | 'document_link' | 'entity_reference' | 'file_reference'
export type DocumentPlacement = {
  id: string
  parent_id: string | null
  block_id: string
  block_name: string
  block_kind: BlockKind
  position: number
  depth: number
  resolution_mode: PlacementResolutionMode
  pinned_revision_id: string | null
  resolved_revision_id: string
  resolved_revision_number: number
  resolved_checksum: string
  resolved_markdown: string
  is_primary: boolean
}
export type DocumentRecord = {
  id: string
  title: string
  owner_kind: 'msp' | 'organization'
  owner_organization_id: string | null
  owner_organization_name: string | null
  is_reference: boolean
  category: DocumentCategory
  is_template: boolean
  library_visible: boolean
  template_enrollment_id: string | null
  template_applied_revision_id: string | null
  template_source_id: string | null
  attachments: DocumentAttachment[]
  attachment_count: number
  publications: DocumentPublication[]
  publication_count: number
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
export type DocumentAttachment = { id: string; filename: string; media_type: string; size: number; checksum: string; scan_status: 'clean'; scan_engine: string; scanned_at: string; created_at: string }
export type PublicationVerification = { valid: boolean; digest_valid: boolean; signature_valid: boolean; key_fingerprint_valid: boolean }
export type PublicationAudience = 'msp_internal' | 'client_visible'
export type PublicationRetention = 'permanent' | 'review_on'
export type PublicationLifecycleState = 'pending_approval' | 'published' | 'superseded' | 'review_due' | 'withdrawn'
export type PublicationControlEvent = { id: string; action: 'submitted' | 'approved' | 'withdrawn'; reason: string; actor: string | null; occurred_at: string }
export type PublicationAudienceProjection = { audience: 'msp_staff' | 'client_portal'; available: boolean; state: string }
export type DocumentPublicationArtifact = { id: string; kind: 'pdf' | 'attachment'; filename: string; media_type: string; size: number; checksum: string; source_attachment_id: string | null }
export type DocumentPublicationInput = { reason: string; audience: PublicationAudience; retention: PublicationRetention; retention_review_on?: string | null; supersedes_id?: string | null }
export type DocumentPublication = {
  id: string
  source_document_id: string
  title: string
  category: DocumentCategory
  reason: string
  audience: PublicationAudience
  retention: PublicationRetention
  retention_review_on: string | null
  lifecycle_state: PublicationLifecycleState
  supersedes_id: string | null
  superseded_by_id: string | null
  control_events: PublicationControlEvent[]
  audience_projections: PublicationAudienceProjection[]
  artifacts: DocumentPublicationArtifact[]
  content_digest: string
  signature_algorithm: 'Ed25519'
  signature: string
  public_key: string
  key_fingerprint: string
  published_by: string | null
  published_at: string
  verification: PublicationVerification
}
export type DocumentPublicationDetail = DocumentPublication & {
  canonical_markdown: string
  sanitized_html: string
  manifest: Record<string, unknown>
}
export type DocumentInput = Pick<DocumentRecord, 'title' | 'markdown' | 'category' | 'is_template'> & { library_visible?: boolean }
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
export type RevisionResult = { results: BlockRevision[]; count: number; page: number; page_size: number; has_more: boolean }
export type RevisionConflictPayload = {
  code: 'revision_conflict'
  detail: string
  submitted_base_revision_id: string
  current_revision: BlockRevisionDetail
  diff: string
}
export type PlacementConflictPayload = { code: 'placement_conflict'; detail: string }
export type PublicationConflictPayload = { code: 'publication_conflict'; detail: string }
export type ReusedPlacementInput = {
  operation?: 'reuse_document'
  source_document_id: string
  resolution_mode: PlacementResolutionMode
  pinned_revision_id?: string | null
  parent_id?: string | null
  position?: number | null
}
export type ReusedBlockInput = {
  operation: 'reuse_block'
  source_block_id: string
  resolution_mode: PlacementResolutionMode
  pinned_revision_id?: string | null
  parent_id?: string | null
  position?: number | null
}
export type NewBlockInput = {
  operation: 'create_block'
  block_kind: BlockKind
  block_name?: string
  markdown: string
  parent_id?: string | null
  position?: number | null
  library_visible?: boolean
}
export type PlacementInput = ReusedPlacementInput | ReusedBlockInput | NewBlockInput
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
export type BlockLibraryItem = {
  id: string
  name: string
  kind: BlockKind
  markdown: string
  revision_id: string
  revision_number: number
  source_document_id: string
  source_document_title: string
  owner_kind: 'msp' | 'organization'
  owner_organization_id: string | null
}
export type BlockLibraryResult = { results: BlockLibraryItem[]; count: number }
export type TemplatePlacementMode = 'copy' | 'live' | 'pinned'
export type TemplateRolloutItem = {
  source_block_id: string
  source_revision_id: string
  checksum: string
  kind: BlockKind
  name: string
  depth: number
  mode?: TemplatePlacementMode
  reason?: string
}
export type TemplateRollout = {
  enrollment_id: string
  applied_revision_id: string
  current_revision: number
  available_revision: number
  up_to_date: boolean
  added: TemplateRolloutItem[]
  changed: TemplateRolloutItem[]
  removed: TemplateRolloutItem[]
  conflicts: TemplateRolloutItem[]
}

export class RevisionConflictError extends AuthRequestError {
  constructor(readonly payload: RevisionConflictPayload) {
    super('This document changed in another session. Your draft was not overwritten.', 409)
    this.name = 'RevisionConflictError'
  }
}

export interface DocumentsClient {
  list(scope: DocumentScope, signal?: AbortSignal, filters?: DocumentFilters): Promise<DocumentResult>
  create(scope: DocumentScope, input: DocumentInput): Promise<DocumentRecord>
  update(scope: DocumentScope, id: string, input: DocumentUpdateInput): Promise<DocumentRecord>
  listRevisions(scope: DocumentScope, id: string, page?: number): Promise<RevisionResult>
  getRevision(scope: DocumentScope, id: string, revisionId: string): Promise<BlockRevisionDetail>
  addPlacement(scope: DocumentScope, id: string, input: PlacementInput): Promise<DocumentRecord>
  updatePlacement(scope: DocumentScope, id: string, placementId: string, input: PlacementUpdateInput): Promise<DocumentRecord>
  removePlacement(scope: DocumentScope, id: string, placementId: string): Promise<DocumentRecord>
  getReuseImpact(scope: DocumentScope, id: string, placementId: string): Promise<ReuseImpact>
  updateSharedBlock(scope: DocumentScope, id: string, placementId: string, markdown: string, baseRevisionId: string): Promise<DocumentRecord>
  detachPlacement(scope: DocumentScope, id: string, placementId: string): Promise<DocumentRecord>
  searchMentionEntities(scope: DocumentScope, query: string, signal?: AbortSignal): Promise<EntityMentionResult>
  searchBlockLibrary(scope: DocumentScope, query: string, signal?: AbortSignal): Promise<BlockLibraryResult>
  listTemplateLibrary(scope: DocumentScope, signal?: AbortSignal): Promise<DocumentResult>
  instantiateTemplate(scope: DocumentScope, sourceDocumentId: string, title: string, category: DocumentCategory, placementRules?: Record<string, TemplatePlacementMode>): Promise<DocumentRecord>
  previewTemplateRollout(scope: DocumentScope, enrollmentId: string): Promise<TemplateRollout>
  applyTemplateRollout(scope: DocumentScope, enrollmentId: string, expectedRevisionId: string, placementRules?: Record<string, TemplatePlacementMode>): Promise<TemplateRollout>
  importMarkdown(scope: DocumentScope, file: File, title: string, category: DocumentCategory, isTemplate: boolean): Promise<DocumentRecord>
  uploadAttachment(scope: DocumentScope, id: string, file: File): Promise<DocumentAttachment>
  archiveAttachment(scope: DocumentScope, id: string, attachmentId: string): Promise<void>
  publish(scope: DocumentScope, id: string, input: DocumentPublicationInput): Promise<DocumentPublicationDetail>
  approvePublication(scope: DocumentScope, id: string, publicationId: string, reason: string): Promise<DocumentPublicationDetail>
  withdrawPublication(scope: DocumentScope, id: string, publicationId: string, reason: string): Promise<DocumentPublicationDetail>
  getPublication(scope: DocumentScope, id: string, publicationId: string): Promise<DocumentPublicationDetail>
  publicationMarkdownUrl(scope: DocumentScope, id: string, publicationId: string): string
  publicationManifestUrl(scope: DocumentScope, id: string, publicationId: string): string
  publicationArtifactUrl(scope: DocumentScope, id: string, publicationId: string, artifactId: string): string
  exportUrl(scope: DocumentScope, id: string): string
  attachmentDownloadUrl(scope: DocumentScope, id: string, attachmentId: string): string
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
      const payload = await response.json() as RevisionConflictPayload | PlacementConflictPayload | PublicationConflictPayload
      if (payload.code === 'revision_conflict') throw new RevisionConflictError(payload)
      if (payload.code === 'placement_conflict') throw new AuthRequestError(payload.detail, 409)
      if (payload.code === 'publication_conflict') throw new AuthRequestError(payload.detail, 409)
    }
    const message = response.status === 403
      ? 'Your account is not authorized to change documentation in this workspace.'
      : response.status === 404
        ? 'That document or workspace is no longer available.'
        : 'The documentation request was not completed.'
    throw await privilegedActionError(response, message)
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

async function mutateForm<T>(path: string, form: FormData) {
  return parse<T>(await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'X-CSRFToken': await csrfToken() },
    body: form,
  }))
}

export const browserDocumentsClient: DocumentsClient = {
  async list(scope, signal, filters = {}) {
    const query = new URLSearchParams()
    if (filters.q) query.set('q', filters.q)
    if (filters.category) query.set('category', filters.category)
    if (filters.template && filters.template !== 'all') query.set('template', filters.template)
    const response = await fetch(`${collectionPath(scope)}${query.size ? `?${query}` : ''}`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    return parse<DocumentResult>(response)
  },
  create: (scope, input) => mutate<DocumentRecord>(collectionPath(scope), 'POST', input),
  update: (scope, id, input) => mutate<DocumentRecord>(`${collectionPath(scope)}/${encodeURIComponent(id)}`, 'PUT', input),
  async listRevisions(scope, id, page = 1) {
    return parse<RevisionResult>(await fetch(`${collectionPath(scope)}/${encodeURIComponent(id)}/revisions?page=${page}&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' } }))
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
  async searchBlockLibrary(scope, query, signal) {
    const parameters = new URLSearchParams({ q: query, page_size: '20' })
    return parse<BlockLibraryResult>(await fetch(`${collectionPath(scope)}/block-library?${parameters}`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    }))
  },
  async listTemplateLibrary(scope, signal) {
    if (!scope.organizationId) return { results: [], count: 0 }
    return parse<DocumentResult>(await fetch(`${collectionPath(scope)}/template-library`, {
      credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
    }))
  },
  instantiateTemplate: (scope, sourceDocumentId, title, category, placementRules = {}) => mutate<DocumentRecord>(`${collectionPath(scope)}/from-template`, 'POST', { source_document_id: sourceDocumentId, title, category, placement_rules: placementRules }),
  previewTemplateRollout: (scope, enrollmentId) => mutate<TemplateRollout>(`${collectionPath(scope)}/template-rollouts/preview`, 'POST', { enrollment_id: enrollmentId }),
  applyTemplateRollout: (scope, enrollmentId, expectedRevisionId, placementRules = {}) => mutate<TemplateRollout>(`${collectionPath(scope)}/template-rollouts/apply`, 'POST', { enrollment_id: enrollmentId, expected_applied_revision_id: expectedRevisionId, placement_rules: placementRules }),
  async importMarkdown(scope, file, title, category, isTemplate) {
    const form = new FormData()
    form.set('file', file)
    form.set('title', title)
    form.set('category', category)
    form.set('is_template', isTemplate ? 'true' : 'false')
    return mutateForm<DocumentRecord>(`${collectionPath(scope)}/import`, form)
  },
  async uploadAttachment(scope, id, file) {
    const form = new FormData()
    form.set('file', file)
    return mutateForm<DocumentAttachment>(`${collectionPath(scope)}/${encodeURIComponent(id)}/attachments`, form)
  },
  archiveAttachment: (scope, id, attachmentId) => mutate<void>(`${collectionPath(scope)}/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`, 'DELETE'),
  publish: (scope, id, input) => mutate<DocumentPublicationDetail>(`${collectionPath(scope)}/${encodeURIComponent(id)}/publications`, 'POST', input),
  approvePublication: (scope, id, publicationId, reason) => mutate<DocumentPublicationDetail>(`${collectionPath(scope)}/${encodeURIComponent(id)}/publications/${encodeURIComponent(publicationId)}/approve`, 'POST', { reason }),
  withdrawPublication: (scope, id, publicationId, reason) => mutate<DocumentPublicationDetail>(`${collectionPath(scope)}/${encodeURIComponent(id)}/publications/${encodeURIComponent(publicationId)}/withdraw`, 'POST', { reason }),
  async getPublication(scope, id, publicationId) {
    return parse<DocumentPublicationDetail>(await fetch(`${collectionPath(scope)}/${encodeURIComponent(id)}/publications/${encodeURIComponent(publicationId)}`, { credentials: 'same-origin', headers: { Accept: 'application/json' } }))
  },
  publicationMarkdownUrl: (scope, id, publicationId) => `${collectionPath(scope)}/${encodeURIComponent(id)}/publications/${encodeURIComponent(publicationId)}/markdown`,
  publicationManifestUrl: (scope, id, publicationId) => `${collectionPath(scope)}/${encodeURIComponent(id)}/publications/${encodeURIComponent(publicationId)}/manifest`,
  publicationArtifactUrl: (scope, id, publicationId, artifactId) => `${collectionPath(scope)}/${encodeURIComponent(id)}/publications/${encodeURIComponent(publicationId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
  exportUrl: (scope, id) => `${collectionPath(scope)}/${encodeURIComponent(id)}/export`,
  attachmentDownloadUrl: (scope, id, attachmentId) => `${collectionPath(scope)}/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}/download`,
  archive: (scope, id) => mutate<void>(`${collectionPath(scope)}/${encodeURIComponent(id)}`, 'DELETE'),
  addReference: (documentId, organizationId) => mutate<void>(`/api/v1/documents/${encodeURIComponent(documentId)}/references`, 'POST', { organization_id: organizationId }),
}
