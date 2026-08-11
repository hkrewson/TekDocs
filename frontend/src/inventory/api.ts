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
  software_installation: SoftwareInstallation | null
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
export type SoftwareInstallation = { id: string; asset_id?: string; asset_name?: string; product_id?: string; product_name?: string; model_name?: string; status: 'planned' | 'installed' | 'suspended' | 'uninstalled'; installed_version: string; installed_on: string | null; last_verified_on: string | null; site_id: string | null; site_name: string | null }
export type SoftwareLicenseSeat = { id: string; seat_number: number; person_id: string | null; person_name: string | null; installation_id: string | null; installation_name: string | null; assigned_at: string; revoked_at: string | null }
export type SoftwareLicenseEvent = { id: string; event_type: string; installation_name: string | null; person_name: string | null; seat_number: number | null; occurred_at: string }
export type SoftwareLicense = { id: string; name: string; supplier_name: string; product_id: string; product_name: string; model_name: string | null; kind: 'subscription' | 'perpetual' | 'trial'; status: 'active' | 'suspended' | 'expired' | 'terminated'; seat_limit: number; active_seats: number; starts_on: string | null; renews_on: string | null; ends_on: string | null; renewal_interval: 'none' | 'monthly' | 'annual' | 'multi_year'; auto_renew: boolean; reference: string; installations: Array<{ id: string; name: string }>; seats: SoftwareLicenseSeat[]; events: SoftwareLicenseEvent[] }
export type SoftwareChoices = { installations: SoftwareInstallation[]; people: Array<{ id: string; name: string }> }
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
export type AssetCsvPreview = {
  schema_version: string
  rows: Array<{ row: number; asset_id: string; name: string; kind: 'hardware' | 'software'; action: 'create' | 'update' | 'skip'; changes: string[] }>
  errors: Array<{ row: number; message: string }>
  summary: { total: number; create: number; update: number; skip: number; errors: number }
  preview_token: string | null
}

export interface InventoryClient {
  listAssets(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: ClientAsset[]; count: number; can_manage: boolean; can_view_relationships: boolean; can_create_relationships: boolean; can_archive_relationships: boolean }>
  listModelChoices(workspace: WorkspaceContext, query: string, signal?: AbortSignal): Promise<{ results: ModelChoice[] }>
  createAsset(workspace: WorkspaceContext, modelId: string, name: string): Promise<ClientAsset>
  bulkAssets(workspace: WorkspaceContext, assetIds: string[], action: 'set_hardware_state' | 'archive', lifecycleState?: HardwareProfile['lifecycle_state']): Promise<{ action: string; processed: number }>
  updateHardware(workspace: WorkspaceContext, assetId: string, values: Partial<HardwareProfile>): Promise<HardwareProfile>
  listHardwareLifecycle(workspace: WorkspaceContext, assetId: string): Promise<HardwareLifecycleEvent[]>
  assignmentChoices(workspace: WorkspaceContext, assetId: string): Promise<HardwareAssignmentChoices>
  assignHardware(workspace: WorkspaceContext, assetId: string, values: { person_id?: string | null; site_id?: string | null; location_id?: string | null }): Promise<HardwareProfile>
  unassignHardware(workspace: WorkspaceContext, assetId: string): Promise<HardwareProfile>
  disposeHardware(workspace: WorkspaceContext, assetId: string, values: { disposed_on: string; method: string; reason: string }): Promise<HardwareProfile>
  updateSoftwareInstallation(workspace: WorkspaceContext, assetId: string, values: Partial<SoftwareInstallation>): Promise<SoftwareInstallation>
  listLicenses(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: SoftwareLicense[]; count: number; can_manage: boolean }>
  createLicense(workspace: WorkspaceContext, values: object): Promise<SoftwareLicense>
  updateLicense(workspace: WorkspaceContext, licenseId: string, values: object): Promise<SoftwareLicense>
  softwareChoices(workspace: WorkspaceContext): Promise<SoftwareChoices>
  linkLicenseInstallation(workspace: WorkspaceContext, licenseId: string, installationId: string): Promise<SoftwareLicense>
  assignLicenseSeat(workspace: WorkspaceContext, licenseId: string, values: { person_id?: string | null; installation_id?: string | null }): Promise<SoftwareLicense>
  revokeLicenseSeat(workspace: WorkspaceContext, licenseId: string, seatId: string): Promise<SoftwareLicense>
  loadDocument(workspace: WorkspaceContext, assetId: string, publicationId: string): Promise<AssetDocument & { sanitized_html: string }>
  listVendors(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: DerivedVendor[]; count: number }>
  artifactUrl(workspace: WorkspaceContext, assetId: string, publicationId: string, artifactId: string): string
  assetCsvTemplateUrl(workspace: WorkspaceContext): string
  assetCsvExportUrl(workspace: WorkspaceContext): string
  previewAssetCsv(workspace: WorkspaceContext, file: File): Promise<AssetCsvPreview>
  applyAssetCsv(workspace: WorkspaceContext, file: File, previewToken: string): Promise<{ created: number; updated: number; skipped: number }>
}

function basePath(workspace: WorkspaceContext) {
  return workspace.kind === 'msp'
    ? '/api/v1/workspaces/msp'
    : `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}`
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

async function mutateForm<T>(path: string, body: FormData): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse(await fetch(path, {
    method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'X-CSRFToken': csrfToken() }, body,
  }))
}

export const browserInventoryClient: InventoryClient = {
  listAssets: (workspace, signal) => get(`${basePath(workspace)}/assets`, signal),
  listModelChoices: (workspace, query, signal) => get(`${basePath(workspace)}/assets/model-choices?q=${encodeURIComponent(query)}`, signal),
  async createAsset(workspace, modelId, name) {
    return mutate(`${basePath(workspace)}/assets`, 'POST', { model_id: modelId, name })
  },
  bulkAssets: (workspace, assetIds, action, lifecycleState) => mutate(
    `${basePath(workspace)}/assets/bulk`,
    'POST',
    { asset_ids: assetIds, action, ...(lifecycleState ? { lifecycle_state: lifecycleState } : {}) },
  ),
  updateHardware: (workspace, assetId, values) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware`, 'PATCH', values),
  listHardwareLifecycle: (workspace, assetId) => get(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/lifecycle`),
  assignmentChoices: (workspace, assetId) => get(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/assignment-choices`),
  assignHardware: (workspace, assetId, values) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/assignment`, 'POST', values),
  unassignHardware: (workspace, assetId) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/assignment`, 'DELETE'),
  disposeHardware: (workspace, assetId, values) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/hardware/dispose`, 'POST', values),
  updateSoftwareInstallation: (workspace, assetId, values) => mutate(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/software`, 'PATCH', values),
  listLicenses: (workspace, signal) => get(`${basePath(workspace)}/licenses`, signal),
  createLicense: (workspace, values) => mutate(`${basePath(workspace)}/licenses`, 'POST', values),
  updateLicense: (workspace, licenseId, values) => mutate(`${basePath(workspace)}/licenses/${encodeURIComponent(licenseId)}`, 'PATCH', values),
  softwareChoices: (workspace) => get(`${basePath(workspace)}/licenses/choices`),
  linkLicenseInstallation: (workspace, licenseId, installationId) => mutate(`${basePath(workspace)}/licenses/${encodeURIComponent(licenseId)}/installations`, 'POST', { installation_id: installationId }),
  assignLicenseSeat: (workspace, licenseId, values) => mutate(`${basePath(workspace)}/licenses/${encodeURIComponent(licenseId)}/seats`, 'POST', values),
  revokeLicenseSeat: (workspace, licenseId, seatId) => mutate(`${basePath(workspace)}/licenses/${encodeURIComponent(licenseId)}/seats/${encodeURIComponent(seatId)}`, 'DELETE'),
  loadDocument: (workspace, assetId, publicationId) => get(`${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/documents/${encodeURIComponent(publicationId)}`),
  listVendors: (workspace, signal) => get(`${basePath(workspace)}/vendors`, signal),
  artifactUrl: (workspace, assetId, publicationId, artifactId) => `${basePath(workspace)}/assets/${encodeURIComponent(assetId)}/documents/${encodeURIComponent(publicationId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
  assetCsvTemplateUrl: (workspace) => `${basePath(workspace)}/assets/csv/template`,
  assetCsvExportUrl: (workspace) => `${basePath(workspace)}/assets/csv/export`,
  previewAssetCsv: (workspace, file) => {
    const body = new FormData(); body.append('file', file)
    return mutateForm(`${basePath(workspace)}/assets/csv/preview`, body)
  },
  applyAssetCsv: (workspace, file, previewToken) => {
    const body = new FormData(); body.append('file', file); body.append('preview_token', previewToken)
    return mutateForm(`${basePath(workspace)}/assets/csv/apply`, body)
  },
}
