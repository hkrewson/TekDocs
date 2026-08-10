import type { WorkspaceContext } from '../workspaces/api'

export type AssetDocument = {
  publication_id: string
  source_document_id: string
  title: string
  category: string
  reason: string
  content_digest: string
  published_at: string
  verification: { valid: boolean; digest_valid: boolean; signature_valid: boolean; key_fingerprint_valid: boolean }
  artifacts: Array<{ id: string; kind: string; filename: string; media_type: string; size: number; checksum: string }>
}
export type ClientAsset = {
  id: string
  name: string
  kind: 'hardware' | 'software'
  supplier_id: string
  supplier_name: string
  product_id: string
  product_name: string
  model_id: string
  model_name: string
  model_number: string
  model_revision_id: string
  model_revision: number
  specification_version_id: string
  specification_definition_id: string
  specification_version: number
  specifications: Record<string, unknown>
  provenance_checksum: string
  documents: AssetDocument[]
  hardware: HardwareProfile | null
  created_at: string
}
export type HardwareProfile = {
  serial_number: string
  asset_tag: string
  lifecycle_state: 'in_stock' | 'in_service' | 'repair' | 'retired' | 'disposed'
  acquired_on: string | null
  acquisition_method: string
  acquisition_reference: string
  warranty_provider: string
  warranty_starts_on: string | null
  warranty_ends_on: string | null
  warranty_reference: string
  assignment: { person_id: string | null; person_name: string | null; site_id: string | null; site_name: string | null; location_id: string | null; location_name: string | null; assigned_at: string | null }
  disposed_on: string | null
  disposal_method: string
  disposal_reason: string
}
export type HardwareLifecycleEvent = { id: string; event_type: string; from_state: string; to_state: string; person_name: string | null; site_name: string | null; location_name: string | null; occurred_at: string }
export type HardwareAssignmentChoices = { people: Array<{ id: string; name: string }>; sites: Array<{ id: string; name: string }>; locations: Array<{ id: string; name: string; site_id: string }> }
export type ModelChoice = {
  id: string
  name: string
  model_number: string
  product_id: string
  product_name: string
  kind: 'hardware' | 'software'
  supplier_id: string
  supplier_name: string
  revision: number
  specification_version_id: string
  specifications: Record<string, unknown>
}
export type DerivedVendor = {
  id: string
  name: string
  legal_name: string
  website: string
  classifications: string[]
  asset_count: number
}

export interface InventoryClient {
  listAssets(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: ClientAsset[]; count: number; can_manage: boolean }>
  listModelChoices(workspace: WorkspaceContext, query: string, signal?: AbortSignal): Promise<{ results: ModelChoice[] }>
  createAsset(workspace: WorkspaceContext, modelId: string, name: string): Promise<ClientAsset>
  updateHardware(workspace: WorkspaceContext, assetId: string, values: Partial<HardwareProfile>): Promise<HardwareProfile>
  listHardwareLifecycle(workspace: WorkspaceContext, assetId: string): Promise<HardwareLifecycleEvent[]>
  assignmentChoices(workspace: WorkspaceContext, assetId: string): Promise<HardwareAssignmentChoices>
  assignHardware(workspace: WorkspaceContext, assetId: string, values: { person_id?: string | null; site_id?: string | null; location_id?: string | null }): Promise<HardwareProfile>
  unassignHardware(workspace: WorkspaceContext, assetId: string): Promise<HardwareProfile>
  disposeHardware(workspace: WorkspaceContext, assetId: string, values: { disposed_on: string; method: string; reason: string }): Promise<HardwareProfile>
  loadDocument(workspace: WorkspaceContext, assetId: string, publicationId: string): Promise<AssetDocument & { sanitized_html: string }>
  listVendors(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: DerivedVendor[]; count: number }>
  artifactUrl(workspace: WorkspaceContext, assetId: string, publicationId: string, artifactId: string): string
}

function basePath(workspace: WorkspaceContext) {
  return `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}`
}

function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

function errorText(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(errorText).filter(Boolean).join(' ')
  if (value && typeof value === 'object') return Object.values(value).map(errorText).filter(Boolean).join(' ')
  return undefined
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as Record<string, unknown>
    throw new Error(errorText(body) ?? 'The inventory request failed.')
  }
  return response.json() as Promise<T>
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return parse(await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
}

async function mutate<T>(path: string, method: string, body?: object): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse(await fetch(path, {
    method, credentials: 'same-origin', headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    ...(body ? { body: JSON.stringify(body) } : {}),
  }))
}

export const browserInventoryClient: InventoryClient = {
  listAssets: (workspace, signal) => get(`${basePath(workspace)}/assets`, signal),
  listModelChoices: (workspace, query, signal) => get(`${basePath(workspace)}/assets/model-choices?q=${encodeURIComponent(query)}`, signal),
  async createAsset(workspace, modelId, name) {
    return mutate(`${basePath(workspace)}/assets`, 'POST', { model_id: modelId, name })
  },
  updateHardware: (workspace, assetId, values) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware`, 'PATCH', values),
  listHardwareLifecycle: (workspace, assetId) => get(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/lifecycle`),
  assignmentChoices: (workspace, assetId) => get(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/assignment-choices`),
  assignHardware: (workspace, assetId, values) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/assignment`, 'POST', values),
  unassignHardware: (workspace, assetId) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/assignment`, 'DELETE'),
  disposeHardware: (workspace, assetId, values) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/dispose`, 'POST', values),
  loadDocument: (workspace, assetId, publicationId) => get(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/documents/${encodeURIComponent(publicationId)}`),
  listVendors: (workspace, signal) => get(`${basePath(workspace)}/vendors`, signal),
  artifactUrl: (workspace, assetId, publicationId, artifactId) => `${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/documents/${encodeURIComponent(publicationId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
}
