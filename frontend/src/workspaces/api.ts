import { AuthRequestError } from '../auth/api'
import type { Organization, OrganizationClassification } from '../organizations/api'

export type WorkspaceCapability =
  | 'overview'
  | 'documentation'
  | 'organizations'
  | 'people'
  | 'assets'
  | 'networks'
  | 'credentials'
  | 'products'
  | 'compliance'
  | 'activity'

export type WorkspaceContext = {
  kind: 'msp' | 'organization'
  id: string
  name: string
  classifications: OrganizationClassification[]
  capabilities: WorkspaceCapability[]
  organization: Organization | null
}

export interface WorkspaceClient {
  loadMsp(): Promise<WorkspaceContext>
  loadOrganization(id: string): Promise<WorkspaceContext>
}

async function load(path: string): Promise<WorkspaceContext> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
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
    return await response.json() as WorkspaceContext
  } catch {
    throw new AuthRequestError('The server returned an unreadable workspace response.', response.status)
  }
}

export const browserWorkspaceClient: WorkspaceClient = {
  loadMsp: () => load('/api/v1/workspaces/msp'),
  loadOrganization: (id) => load(`/api/v1/workspaces/organizations/${encodeURIComponent(id)}`),
}
