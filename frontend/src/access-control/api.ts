import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type BuiltInRole = 'owner' | 'administrator' | 'technician' | 'contributor' | 'read_only' | 'client_administrator' | 'client_user'
export type TenantRole = 'administrator' | 'technician' | 'contributor' | 'read_only'
export type OrganizationAccessMode = 'all_authorized' | 'assigned_only'

export type PermissionDefinition = {
  key: string
  label: string
  category: string
  requires_mfa: boolean
}

export type RoleDefinition = {
  value: BuiltInRole
  label: string
  description: string
  assignable_scope: 'installation' | 'tenant' | 'organization'
  permissions: string[]
}

export type AccessCatalog = { permissions: PermissionDefinition[]; roles: RoleDefinition[] }
export type Member = { id: string; display_name: string; email: string; role: BuiltInRole; is_owner: boolean; joined_at: string | null }
export type OrganizationAccess = { id: string; name: string; access_mode: OrganizationAccessMode }

export interface AccessControlClient {
  catalog(signal?: AbortSignal): Promise<AccessCatalog>
  members(signal?: AbortSignal): Promise<Member[]>
  organizations(signal?: AbortSignal): Promise<OrganizationAccess[]>
  assignRole(userId: string, role: TenantRole): Promise<Member>
  changeAccessMode(organizationId: string, accessMode: OrganizationAccessMode): Promise<OrganizationAccess>
}

async function payload<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T
  } catch {
    throw new AuthRequestError('The server returned an unreadable access-control response.', response.status)
  }
}

function requestError(response: Response) {
  return new AuthRequestError(
    response.status === 403
      ? 'Your account is not authorized to manage access control.'
      : response.status === 404
        ? 'The selected member or organization is no longer available.'
        : response.status === 400
          ? 'The selected access-control change is not valid.'
          : 'Access control is unavailable.',
    response.status,
  )
}

async function load<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
  if (!response.ok) throw requestError(response)
  return payload<T>(response)
}

async function patch<T>(path: string, body: object): Promise<T> {
  let token = browserCsrfToken()
  if (!token) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    token = browserCsrfToken()
  }
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  const response = await fetch(path, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw requestError(response)
  return payload<T>(response)
}

export const browserAccessControlClient: AccessControlClient = {
  catalog: (signal) => load<AccessCatalog>('/api/v1/access-control/catalog', signal),
  members: (signal) => load<Member[]>('/api/v1/access-control/members', signal),
  organizations: (signal) => load<OrganizationAccess[]>('/api/v1/access-control/organizations', signal),
  assignRole: (userId, role) => patch<Member>(`/api/v1/access-control/members/${encodeURIComponent(userId)}`, { role }),
  changeAccessMode: (organizationId, accessMode) => patch<OrganizationAccess>(
    `/api/v1/access-control/organizations/${encodeURIComponent(organizationId)}`,
    { access_mode: accessMode },
  ),
}
