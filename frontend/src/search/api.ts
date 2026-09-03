import { AuthRequestError } from '../auth/api'

export const workspaceSearchResultTypes = [
  'organization',
  'person',
  'site',
  'location',
  'document',
  'file',
  'asset',
  'product',
  'model',
  'license',
  'service',
  'credential_reference',
  'domain',
  'certificate',
  'network',
  'data_flow',
  'external_ticket',
] as const

export type WorkspaceSearchResultType = typeof workspaceSearchResultTypes[number]
export type WorkspaceSearchScope = { organizationId?: string }

export type WorkspaceSearchHit = {
  id: string
  result_type: WorkspaceSearchResultType
  entity_type: string
  title: string
  excerpt: string
  workspace_label: string
  target: string
  score: number
  updated_at: string
  review_state: string | null
}

export type WorkspaceSearchFacet = {
  value: WorkspaceSearchResultType
  label: string
  count: number
}

export type WorkspaceSearchResult = {
  results: WorkspaceSearchHit[]
  facets: WorkspaceSearchFacet[]
  page: number
  page_size: number
  count: number
  has_more: boolean
  truncated: boolean
}

export interface WorkspaceSearchClient {
  search(
    scope: WorkspaceSearchScope,
    query: string,
    resultType: WorkspaceSearchResultType | '',
    page: number,
    signal?: AbortSignal,
  ): Promise<WorkspaceSearchResult>
}

function searchPath(scope: WorkspaceSearchScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/search`
    : '/api/v1/search'
}

function searchError(response: Response) {
  const message = response.status === 400
    ? 'The search query or filter is not valid.'
    : response.status === 403
      ? 'Your account is not authorized to search this workspace.'
      : response.status === 404
        ? 'The selected workspace is no longer available.'
        : 'Search results could not be loaded.'
  return new AuthRequestError(message, response.status)
}

export const browserWorkspaceSearchClient: WorkspaceSearchClient = {
  async search(scope, query, resultType, page, signal) {
    const parameters = new URLSearchParams({ q: query, page: String(page), page_size: '15' })
    if (resultType) parameters.set('result_type', resultType)
    const response = await fetch(`${searchPath(scope)}?${parameters}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (!response.ok) throw searchError(response)
    try {
      return await response.json() as WorkspaceSearchResult
    } catch {
      throw new AuthRequestError('The server returned unreadable search results.', response.status)
    }
  },
}
