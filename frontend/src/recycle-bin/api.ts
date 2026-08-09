import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type RecycleBinRecordType = 'organization' | 'person_association' | 'site' | 'location' | 'custom_field_definition'

export type RecycleBinItem = {
  id: string
  record_type: RecycleBinRecordType
  label: string
  archived_at: string
  workspace_kind: 'msp' | 'organization'
  workspace_id: string
  workspace_name: string
  cascade_count: number
  can_restore: boolean
}

export type RecycleBinScope = { organizationId?: string }
export type RecycleBinQuery = { query?: string; recordType?: RecycleBinRecordType | '' }
export type RecycleBinResult = { results: RecycleBinItem[]; page: number; page_size: number; count: number; has_more: boolean }

export interface RecycleBinClient {
  list(scope: RecycleBinScope, query?: RecycleBinQuery, signal?: AbortSignal): Promise<RecycleBinResult>
  restore(scope: RecycleBinScope, item: Pick<RecycleBinItem, 'id' | 'record_type'>): Promise<void>
}

function collectionPath(scope: RecycleBinScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/recycle-bin`
    : '/api/v1/recycle-bin'
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

async function errorFor(response: Response) {
  let detail = ''
  try { detail = (await response.json() as { detail?: string }).detail ?? '' } catch { /* response had no JSON detail */ }
  const fallback = response.status === 403
    ? 'Your account is not authorized to recover this record. Recent MFA may be required.'
    : response.status === 404
      ? 'That archived record is no longer available in this workspace.'
      : response.status === 409
        ? 'Restore the required parent record first.'
        : 'The recovery request could not be completed.'
  return new AuthRequestError(detail || fallback, response.status)
}

export const browserRecycleBinClient: RecycleBinClient = {
  async list(scope, query = {}, signal) {
    const parameters = new URLSearchParams({ page: '1', page_size: '50' })
    if (query.query) parameters.set('q', query.query)
    if (query.recordType) parameters.set('record_type', query.recordType)
    const response = await fetch(`${collectionPath(scope)}?${parameters}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (!response.ok) throw await errorFor(response)
    try { return await response.json() as RecycleBinResult } catch { throw new AuthRequestError('The server returned an unreadable recycle-bin response.', response.status) }
  },
  async restore(scope, item) {
    const response = await fetch(`${collectionPath(scope)}/${item.record_type}/${encodeURIComponent(item.id)}/restore`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    })
    if (!response.ok) throw await errorFor(response)
  },
}
