import type { WorkspaceContext } from '../workspaces/api'

export type ProductKind = 'hardware' | 'software'
export type ModelLifecycle = 'active' | 'discontinued' | 'pre_release'
export type SpecificationProperty = {
  type: 'string' | 'integer' | 'number' | 'boolean' | 'array'
  title?: string
  description?: string
  enum?: string[]
  items?: { type: 'string'; enum?: string[] }
}
export type SpecificationSchema = {
  $schema?: string
  type: 'object'
  additionalProperties: false
  properties: Record<string, SpecificationProperty>
  required?: string[]
}
export type SpecificationVersion = {
  id: string
  version: number
  schema: SpecificationSchema
  checksum: string
  created_by: string
  created_at: string
}
export type SpecificationDefinition = {
  id: string
  name: string
  product_kind: ProductKind
  versions: SpecificationVersion[]
}
export type ModelRevision = {
  id: string
  revision: number
  parent_id: string | null
  specification_version_id: string
  specification_definition_id: string
  specification_definition_name: string
  specification_version: number
  lifecycle: ModelLifecycle
  specifications: Record<string, unknown>
  notes: string
  checksum: string
  created_by: string
  created_at: string
}
export type CatalogModel = {
  id: string
  name: string
  model_number: string
  current_revision: ModelRevision
  revisions: ModelRevision[]
}
export type CatalogProduct = {
  id: string
  name: string
  kind: ProductKind
  description: string
  updated_at: string
  models: CatalogModel[]
}
export type ProductDraft = { name: string; kind: ProductKind; description: string }
export type DefinitionDraft = { name: string; product_kind: ProductKind; schema: SpecificationSchema }
export type ModelDraft = {
  name: string
  model_number: string
  specification_version_id: string
  lifecycle: ModelLifecycle
  specifications: Record<string, unknown>
  notes: string
}

export interface CatalogClient {
  listProducts(workspace: WorkspaceContext, query: string, kind: ProductKind | '', signal?: AbortSignal): Promise<{ results: CatalogProduct[]; can_manage: boolean }>
  createProduct(workspace: WorkspaceContext, draft: ProductDraft): Promise<CatalogProduct>
  updateProduct(workspace: WorkspaceContext, productId: string, draft: Omit<ProductDraft, 'kind'>): Promise<CatalogProduct>
  archiveProduct(workspace: WorkspaceContext, productId: string): Promise<void>
  listDefinitions(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: SpecificationDefinition[]; can_manage: boolean }>
  createDefinition(workspace: WorkspaceContext, draft: DefinitionDraft): Promise<SpecificationDefinition>
  versionDefinition(workspace: WorkspaceContext, definitionId: string, schema: SpecificationSchema): Promise<SpecificationVersion>
  createModel(workspace: WorkspaceContext, productId: string, draft: ModelDraft): Promise<CatalogModel>
  reviseModel(workspace: WorkspaceContext, productId: string, modelId: string, draft: ModelDraft & { base_revision_id: string }): Promise<CatalogModel>
  archiveModel(workspace: WorkspaceContext, productId: string, modelId: string): Promise<void>
}

function basePath(workspace: WorkspaceContext) {
  return `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/catalog`
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
    const error = new Error(errorText(body) ?? 'The catalog request failed.')
    if (response.status === 409) Object.assign(error, { currentRevision: body.current_revision })
    throw error
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function mutate<T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse<T>(await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  }))
}

export const browserCatalogClient: CatalogClient = {
  async listProducts(workspace, query, kind, signal) {
    const parameters = new URLSearchParams()
    if (query) parameters.set('q', query)
    if (kind) parameters.set('kind', kind)
    const suffix = parameters.size ? `?${parameters}` : ''
    return parse(await fetch(`${basePath(workspace)}/products${suffix}`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
  },
  createProduct: (workspace, draft) => mutate(`${basePath(workspace)}/products`, 'POST', draft),
  updateProduct: (workspace, productId, draft) => mutate(`${basePath(workspace)}/products/${encodeURIComponent(productId)}`, 'PATCH', draft),
  archiveProduct: (workspace, productId) => mutate(`${basePath(workspace)}/products/${encodeURIComponent(productId)}`, 'DELETE'),
  async listDefinitions(workspace, signal) {
    return parse(await fetch(`${basePath(workspace)}/specification-definitions`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
  },
  createDefinition: (workspace, draft) => mutate(`${basePath(workspace)}/specification-definitions`, 'POST', draft),
  versionDefinition: (workspace, definitionId, schema) => mutate(`${basePath(workspace)}/specification-definitions/${encodeURIComponent(definitionId)}/versions`, 'POST', { schema }),
  createModel: (workspace, productId, draft) => mutate(`${basePath(workspace)}/products/${encodeURIComponent(productId)}/models`, 'POST', draft),
  reviseModel: (workspace, productId, modelId, draft) => mutate(`${basePath(workspace)}/products/${encodeURIComponent(productId)}/models/${encodeURIComponent(modelId)}`, 'PATCH', draft),
  archiveModel: (workspace, productId, modelId) => mutate(`${basePath(workspace)}/products/${encodeURIComponent(productId)}/models/${encodeURIComponent(modelId)}`, 'DELETE'),
}
