import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type DocumentScope = { organizationId?: string }
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
      const payload = await response.json() as RevisionConflictPayload
      if (payload.code === 'revision_conflict') throw new RevisionConflictError(payload)
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

async function mutate<T>(path: string, method: 'POST' | 'PUT' | 'DELETE', body?: object) {
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
  archive: (scope, id) => mutate<void>(`${collectionPath(scope)}/${encodeURIComponent(id)}`, 'DELETE'),
  addReference: (documentId, organizationId) => mutate<void>(`/api/v1/documents/${encodeURIComponent(documentId)}/references`, 'POST', { organization_id: organizationId }),
}
