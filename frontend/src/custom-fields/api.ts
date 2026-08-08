import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type CustomFieldType = 'text' | 'integer' | 'number' | 'boolean' | 'date' | 'url' | 'email' | 'choice' | 'multi_choice'
export type CustomFieldEntityType = 'organization' | 'person' | 'site' | 'location'
export type CustomFieldScope = { organizationId?: string }

export type CustomFieldVersion = {
  id: string
  version: number
  label: string
  description: string
  required: boolean
  field_type: CustomFieldType
  schema: Record<string, unknown>
  display_order: number
  created_at: string
}

export type CustomFieldDefinition = {
  id: string
  key: string
  entity_type: CustomFieldEntityType
  owner: 'msp' | 'organization'
  organization_id: string | null
  inherited: boolean
  archived: boolean
  current_version: CustomFieldVersion
  versions: CustomFieldVersion[]
}

export type CustomFieldDefinitionInput = {
  key: string
  entity_type: CustomFieldEntityType
  label: string
  description: string
  required: boolean
  field_type: CustomFieldType
  display_order: number
  options: string[]
}

export type CustomFieldVersionInput = Omit<CustomFieldDefinitionInput, 'key' | 'entity_type'>
export type CustomFieldDefinitionResult = { results: CustomFieldDefinition[]; count: number }
export type MigrationImpact = { total: number; compatible: number; incompatible: number }
export type CustomFieldVersionResult = { definition: CustomFieldDefinition; migration_impact: MigrationImpact }

export type EntityCustomField = {
  definition: CustomFieldDefinition
  has_value: boolean
  value: unknown
  value_version_id: string | null
  value_version: number | null
  is_current: boolean
  valid_for_current: boolean
}
export type EntityCustomFieldResult = { entity_id: string; entity_type: string; fields: EntityCustomField[] }

export interface CustomFieldsClient {
  listDefinitions(scope: CustomFieldScope, signal?: AbortSignal): Promise<CustomFieldDefinitionResult>
  createDefinition(scope: CustomFieldScope, input: CustomFieldDefinitionInput): Promise<CustomFieldDefinition>
  createVersion(scope: CustomFieldScope, id: string, input: CustomFieldVersionInput): Promise<CustomFieldVersionResult>
  archiveDefinition(scope: CustomFieldScope, id: string): Promise<void>
  listEntityFields(scope: CustomFieldScope, entityId: string, signal?: AbortSignal): Promise<EntityCustomFieldResult>
  setEntityValue(scope: CustomFieldScope, entityId: string, definitionId: string, value: unknown): Promise<EntityCustomFieldResult>
  clearEntityValue(scope: CustomFieldScope, entityId: string, definitionId: string): Promise<void>
}

function definitionCollectionPath(scope: CustomFieldScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/custom-field-definitions`
    : '/api/v1/custom-field-definitions'
}

function entityCollectionPath(scope: CustomFieldScope, entityId: string) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/entities/${encodeURIComponent(entityId)}/custom-fields`
    : `/api/v1/entities/${encodeURIComponent(entityId)}/custom-fields`
}

async function decode<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T
  } catch {
    throw new AuthRequestError('The server returned an unreadable custom-field response.', response.status)
  }
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

function requestError(response: Response) {
  const message = response.status === 400
    ? 'Review the custom-field configuration or value.'
    : response.status === 403
      ? 'Your account is not authorized to manage custom fields in this workspace.'
      : response.status === 404
        ? 'That field, record, or workspace is no longer available.'
        : 'The custom-field change was not completed.'
  return new AuthRequestError(message, response.status)
}

async function mutation(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown) {
  return fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export const browserCustomFieldsClient: CustomFieldsClient = {
  async listDefinitions(scope, signal) {
    const response = await fetch(definitionCollectionPath(scope), { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    if (!response.ok) throw requestError(response)
    return decode<CustomFieldDefinitionResult>(response)
  },
  async createDefinition(scope, input) {
    const response = await mutation(definitionCollectionPath(scope), 'POST', input)
    if (!response.ok) throw requestError(response)
    return decode<CustomFieldDefinition>(response)
  },
  async createVersion(scope, id, input) {
    const response = await mutation(`${definitionCollectionPath(scope)}/${encodeURIComponent(id)}`, 'PATCH', input)
    if (!response.ok) throw requestError(response)
    return decode<CustomFieldVersionResult>(response)
  },
  async archiveDefinition(scope, id) {
    const response = await mutation(`${definitionCollectionPath(scope)}/${encodeURIComponent(id)}`, 'DELETE')
    if (!response.ok) throw requestError(response)
  },
  async listEntityFields(scope, entityId, signal) {
    const response = await fetch(entityCollectionPath(scope, entityId), { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    if (!response.ok) throw requestError(response)
    return decode<EntityCustomFieldResult>(response)
  },
  async setEntityValue(scope, entityId, definitionId, value) {
    const response = await mutation(`${entityCollectionPath(scope, entityId)}/${encodeURIComponent(definitionId)}`, 'PATCH', { value })
    if (!response.ok) throw requestError(response)
    return decode<EntityCustomFieldResult>(response)
  },
  async clearEntityValue(scope, entityId, definitionId) {
    const response = await mutation(`${entityCollectionPath(scope, entityId)}/${encodeURIComponent(definitionId)}`, 'DELETE')
    if (!response.ok) throw requestError(response)
  },
}
