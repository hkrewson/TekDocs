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
  created_at: string
  updated_at: string
}
export type DocumentInput = Pick<DocumentRecord, 'title' | 'markdown'>
export type DocumentResult = { results: DocumentRecord[]; count: number }

export interface DocumentsClient {
  list(scope: DocumentScope, signal?: AbortSignal): Promise<DocumentResult>
  create(scope: DocumentScope, input: DocumentInput): Promise<DocumentRecord>
  update(scope: DocumentScope, id: string, input: DocumentInput): Promise<DocumentRecord>
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
  archive: (scope, id) => mutate<void>(`${collectionPath(scope)}/${encodeURIComponent(id)}`, 'DELETE'),
  addReference: (documentId, organizationId) => mutate<void>(`/api/v1/documents/${encodeURIComponent(documentId)}/references`, 'POST', { organization_id: organizationId }),
}
