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

export type AccessCatalog = { permissions: PermissionDefinition[]; roles: RoleDefinition[]; custom_assignable_permissions: PermissionDefinition[] }
export type Member = { id: string; display_name: string; email: string; role: BuiltInRole; is_owner: boolean; joined_at: string | null }
export type AssignedStaff = { id: string; display_name: string; email: string; role: TenantRole }
export type OrganizationAccess = { id: string; name: string; access_mode: OrganizationAccessMode; assigned_staff: AssignedStaff[] }
export type CustomRoleScope = 'tenant' | 'organization'
export type CustomRole = { id: string; name: string; description: string; scope: CustomRoleScope; permissions: string[]; assignment_count: number; archived_at: string | null; created_at: string; updated_at: string }
export type CustomRoleInput = { name: string; description: string; scope: CustomRoleScope; permissions: string[] }
export type ScopedRoleAssignment = { id: string; member_id: string; member_name: string; member_email: string; role_id: string; role_name: string; role_scope: CustomRoleScope; organization_id: string | null; organization_name: string | null; created_at: string }

export interface AccessControlClient {
  catalog(signal?: AbortSignal): Promise<AccessCatalog>
  members(signal?: AbortSignal): Promise<Member[]>
  organizations(signal?: AbortSignal): Promise<OrganizationAccess[]>
  customRoles(signal?: AbortSignal): Promise<CustomRole[]>
  scopedAssignments(signal?: AbortSignal): Promise<ScopedRoleAssignment[]>
  assignRole(userId: string, role: TenantRole): Promise<Member>
  changeAccessMode(organizationId: string, accessMode: OrganizationAccessMode): Promise<OrganizationAccess>
  assignStaff(organizationId: string, userId: string): Promise<OrganizationAccess>
  removeStaff(organizationId: string, userId: string): Promise<OrganizationAccess>
  createCustomRole(input: CustomRoleInput): Promise<CustomRole>
  updateCustomRole(roleId: string, input: Omit<CustomRoleInput, 'scope'>): Promise<CustomRole>
  archiveCustomRole(roleId: string): Promise<CustomRole>
  createScopedAssignment(input: { user_id: string; role_id: string; organization_id?: string | null }): Promise<ScopedRoleAssignment>
  removeScopedAssignment(assignmentId: string): Promise<void>
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
  return mutate<T>('PATCH', path, body)
}

async function mutate<T>(method: 'PATCH' | 'POST' | 'DELETE', path: string, body?: object): Promise<T> {
  let token = browserCsrfToken()
  if (!token) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    token = browserCsrfToken()
  }
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw requestError(response)
  if (response.status === 204) return undefined as T
  return payload<T>(response)
}

export const browserAccessControlClient: AccessControlClient = {
  catalog: (signal) => load<AccessCatalog>('/api/v1/access-control/catalog', signal),
  members: (signal) => load<Member[]>('/api/v1/access-control/members', signal),
  organizations: (signal) => load<OrganizationAccess[]>('/api/v1/access-control/organizations', signal),
  customRoles: (signal) => load<CustomRole[]>('/api/v1/access-control/custom-roles', signal),
  scopedAssignments: (signal) => load<ScopedRoleAssignment[]>('/api/v1/access-control/role-assignments', signal),
  assignRole: (userId, role) => patch<Member>(`/api/v1/access-control/members/${encodeURIComponent(userId)}`, { role }),
  changeAccessMode: (organizationId, accessMode) => patch<OrganizationAccess>(
    `/api/v1/access-control/organizations/${encodeURIComponent(organizationId)}`,
    { access_mode: accessMode },
  ),
  assignStaff: (organizationId, userId) => mutate<OrganizationAccess>(
    'POST',
    `/api/v1/access-control/organizations/${encodeURIComponent(organizationId)}/staff`,
    { user_id: userId },
  ),
  removeStaff: (organizationId, userId) => mutate<OrganizationAccess>(
    'DELETE',
    `/api/v1/access-control/organizations/${encodeURIComponent(organizationId)}/staff/${encodeURIComponent(userId)}`,
  ),
  createCustomRole: (input) => mutate<CustomRole>('POST', '/api/v1/access-control/custom-roles', input),
  updateCustomRole: (roleId, input) => patch<CustomRole>(`/api/v1/access-control/custom-roles/${encodeURIComponent(roleId)}`, input),
  archiveCustomRole: (roleId) => mutate<CustomRole>('DELETE', `/api/v1/access-control/custom-roles/${encodeURIComponent(roleId)}`),
  createScopedAssignment: (input) => mutate<ScopedRoleAssignment>('POST', '/api/v1/access-control/role-assignments', input),
  removeScopedAssignment: (assignmentId) => mutate<void>('DELETE', `/api/v1/access-control/role-assignments/${encodeURIComponent(assignmentId)}`),
}
