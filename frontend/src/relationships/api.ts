import { AuthRequestError, browserCsrfToken } from '../auth/api'

export type EntityLinkType =
  | 'related_to'
  | 'connected_to'
  | 'depends_on'
  | 'managed_by'
  | 'supplied_by'
  | 'manufactured_by'
  | 'partnered_with'
  | 'located_at'
  | 'assigned_to'
  | 'references'

export type EntityReference = {
  id: string
  display_name: string
  entity_type: string
  visibility: 'msp_private' | 'client_visible'
  workspace_label: string
  eligible_link_types: EntityLinkType[]
}

export type LinkTypeDefinition = {
  value: EntityLinkType
  forward_label: string
  inverse_label: string
  symmetric: boolean
  target_types: string[]
}

export type EntityRelationship = {
  id: string
  link_type: EntityLinkType
  label: string
  direction: 'outgoing' | 'incoming'
  source_id: string
  target_id: string
  related_entity: EntityReference
  created_at: string
}

export type RelationshipScope = { organizationId?: string }
export type EntitySearchResult = { results: EntityReference[]; page: number; page_size: number; count: number; has_more: boolean }
export type RelationshipGraphFamily = 'network' | 'asset' | 'document'
export type RelationshipGraphNode = { id: string; label: string; entity_type: string; visibility: 'msp_private' | 'client_visible'; root: boolean }
export type RelationshipGraphEdge = { id: string; source: string; target: string; link_type: EntityLinkType; label: string; symmetric: boolean }
export type RelationshipGraph = { family: RelationshipGraphFamily; workspace: { kind: 'msp' | 'organization'; id: string }; root_entity_id: string | null; depth: number; edge_limit: number; truncated: boolean; digest: string; nodes: RelationshipGraphNode[]; edges: RelationshipGraphEdge[] }
export type RelationshipGraphView = { id: string; name: string; family: RelationshipGraphFamily; root_entity_id: string | null; depth: number; edge_limit: number; positions: Record<string, { x: number; y: number }>; graph: RelationshipGraph; created_at: string; updated_at: string }
export type RelationshipGraphSnapshot = { id: string; view_id: string; content_digest: string; graph: RelationshipGraph & { positions?: Record<string, { x: number; y: number }>; view_name?: string }; created_at: string }

export interface RelationshipsClient {
  linkTypes(signal?: AbortSignal): Promise<LinkTypeDefinition[]>
  search(scope: RelationshipScope, query: string, entityType?: string, signal?: AbortSignal): Promise<EntitySearchResult>
  list(scope: RelationshipScope, entityId: string, signal?: AbortSignal): Promise<EntityRelationship[]>
  create(scope: RelationshipScope, entityId: string, targetId: string, linkType: EntityLinkType): Promise<EntityRelationship>
  archive(scope: RelationshipScope, entityId: string, linkId: string): Promise<void>
  graph?(scope: RelationshipScope, family: RelationshipGraphFamily, options?: { rootId?: string; depth?: number; edgeLimit?: number }, signal?: AbortSignal): Promise<RelationshipGraph>
  graphViews?(scope: RelationshipScope, signal?: AbortSignal): Promise<RelationshipGraphView[]>
  saveGraphView?(scope: RelationshipScope, values: { name: string; family: RelationshipGraphFamily; root_entity_id: string | null; depth: number; edge_limit: number; positions: Record<string, { x: number; y: number }> }): Promise<RelationshipGraphView>
  updateGraphView?(scope: RelationshipScope, viewId: string, values: { name: string; family: RelationshipGraphFamily; root_entity_id: string | null; depth: number; edge_limit: number; positions: Record<string, { x: number; y: number }> }): Promise<RelationshipGraphView>
  snapshotGraphView?(scope: RelationshipScope, viewId: string): Promise<RelationshipGraphSnapshot>
  graphSnapshotExportUrl?(scope: RelationshipScope, snapshotId: string, format: 'json' | 'csv' | 'svg'): string
}

function entitiesPath(scope: RelationshipScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/entities`
    : '/api/v1/entities'
}

function relationshipsPath(scope: RelationshipScope, entityId: string, linkId?: string) {
  const base = `${entitiesPath(scope)}/${encodeURIComponent(entityId)}/links`
  return linkId ? `${base}/${encodeURIComponent(linkId)}` : base
}

function graphPath(scope: RelationshipScope) {
  return scope.organizationId ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}/relationship-graph` : '/api/v1/relationship-graph'
}

function graphViewsPath(scope: RelationshipScope, viewId?: string) {
  const base = `${graphPath(scope)}/views`
  return viewId ? `${base}/${encodeURIComponent(viewId)}` : base
}

async function json<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T
  } catch {
    throw new AuthRequestError('The server returned an unreadable response.', response.status)
  }
}

async function csrfToken(): Promise<string> {
  let token = browserCsrfToken()
  if (!token) {
    await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    token = browserCsrfToken()
  }
  if (!token) throw new AuthRequestError('The browser security token is unavailable. Refresh and try again.')
  return token
}

function requestError(response: Response, action: 'load' | 'change') {
  const message = response.status === 400
    ? 'The selected relationship is not valid for these records.'
    : response.status === 403
      ? `Your account is not authorized to ${action === 'load' ? 'view' : 'manage'} relationships in this workspace.`
      : response.status === 404
        ? 'The record or relationship is no longer available in this workspace.'
        : `Relationships could not be ${action === 'load' ? 'loaded' : 'changed'}.`
  return new AuthRequestError(message, response.status)
}

async function mutation(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: object) {
  return fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() },
    body: body ? JSON.stringify(body) : undefined,
  })
}

export const browserRelationshipsClient: RelationshipsClient = {
  async linkTypes(signal) {
    const response = await fetch('/api/v1/entity-link-types', { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    if (!response.ok) throw requestError(response, 'load')
    return json<LinkTypeDefinition[]>(response)
  },
  async search(scope, query, entityType, signal) {
    const parameters = new URLSearchParams({ q: query, page: '1', page_size: '15' })
    if (entityType) parameters.set('entity_type', entityType)
    const response = await fetch(`${entitiesPath(scope)}/search?${parameters}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (!response.ok) throw requestError(response, 'load')
    return json<EntitySearchResult>(response)
  },
  async list(scope, entityId, signal) {
    const response = await fetch(relationshipsPath(scope, entityId), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (!response.ok) throw requestError(response, 'load')
    return (await json<{ relationships: EntityRelationship[] }>(response)).relationships
  },
  async create(scope, entityId, targetId, linkType) {
    const response = await mutation(relationshipsPath(scope, entityId), 'POST', { target_id: targetId, link_type: linkType })
    if (!response.ok) throw requestError(response, 'change')
    return json<EntityRelationship>(response)
  },
  async archive(scope, entityId, linkId) {
    const response = await mutation(relationshipsPath(scope, entityId, linkId), 'DELETE')
    if (!response.ok) throw requestError(response, 'change')
  },
  async graph(scope, family, options = {}, signal) {
    const parameters = new URLSearchParams({ family, depth: String(options.depth ?? 2), edge_limit: String(options.edgeLimit ?? 100) })
    if (options.rootId) parameters.set('root', options.rootId)
    const response = await fetch(`${graphPath(scope)}?${parameters}`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    if (!response.ok) throw requestError(response, 'load')
    return json<RelationshipGraph>(response)
  },
  async graphViews(scope, signal) {
    const response = await fetch(graphViewsPath(scope), { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })
    if (!response.ok) throw requestError(response, 'load')
    return json<RelationshipGraphView[]>(response)
  },
  async saveGraphView(scope, values) {
    const response = await mutation(graphViewsPath(scope), 'POST', values)
    if (!response.ok) throw requestError(response, 'change')
    return json<RelationshipGraphView>(response)
  },
  async updateGraphView(scope, viewId, values) {
    const response = await mutation(graphViewsPath(scope, viewId), 'PATCH', values)
    if (!response.ok) throw requestError(response, 'change')
    return json<RelationshipGraphView>(response)
  },
  async snapshotGraphView(scope, viewId) {
    const response = await mutation(`${graphViewsPath(scope, viewId)}/snapshots`, 'POST')
    if (!response.ok) throw requestError(response, 'change')
    return json<RelationshipGraphSnapshot>(response)
  },
  graphSnapshotExportUrl(scope, snapshotId, format) {
    return `${graphPath(scope)}/snapshots/${encodeURIComponent(snapshotId)}/export/${format}`
  },
}
