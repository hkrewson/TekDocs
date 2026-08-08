import { AuthRequestError } from '../auth/api'
import type { Organization, OrganizationClassification } from '../organizations/api'

export type WorkspaceCapability =
  | 'overview'
  | 'organizations'
  | 'people'
  | 'sites'
  | 'custom_fields'
  | 'documentation'
  | 'files'
  | 'assets'
  | 'licenses'
  | 'networks'
  | 'domains'
  | 'certificates'
  | 'credentials'
  | 'services'
  | 'tickets'
  | 'vendors'
  | 'products'
  | 'compliance'
  | 'activity'
  | 'integrations'
  | 'accounting'

export type WorkspaceContext = {
  kind: 'msp' | 'organization'
  id: string
  name: string
  classifications: OrganizationClassification[]
  capabilities: WorkspaceCapability[]
  organization: Organization | null
}

export type WorkspaceOption = Pick<WorkspaceContext, 'id' | 'name' | 'classifications' | 'capabilities'>

export type WorkspaceSearchResult = {
  results: WorkspaceOption[]
  page: number
  page_size: number
  has_more: boolean
}

export interface WorkspaceClient {
  loadMsp(): Promise<WorkspaceContext>
  loadOrganization(id: string, signal?: AbortSignal): Promise<WorkspaceContext>
  searchOrganizations(query: string, page?: number, signal?: AbortSignal, classification?: OrganizationClassification): Promise<WorkspaceSearchResult>
}

async function load<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) {
    const message = response.status === 403
      ? 'Your account is not authorized to open this organization workspace.'
      : response.status === 404
        ? 'That organization workspace is no longer available.'
        : 'The workspace could not be loaded.'
    throw new AuthRequestError(message, response.status)
  }
  try {
    return await response.json() as T
  } catch {
    throw new AuthRequestError('The server returned an unreadable workspace response.', response.status)
  }
}

export const browserWorkspaceClient: WorkspaceClient = {
  loadMsp: () => load<WorkspaceContext>('/api/v1/workspaces/msp'),
  loadOrganization: (id, signal) => load<WorkspaceContext>(`/api/v1/workspaces/organizations/${encodeURIComponent(id)}`, signal),
  searchOrganizations: (query, page = 1, signal, classification) => {
    const parameters = new URLSearchParams({ q: query, page: String(page), page_size: '15' })
    if (classification) parameters.set('classification', classification)
    return load<WorkspaceSearchResult>(`/api/v1/workspaces/organizations?${parameters}`, signal)
  },
}
