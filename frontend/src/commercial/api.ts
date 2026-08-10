import type { WorkspaceContext } from '../workspaces/api'

export type ContractCost = {
  id: string
  label: string
  amount: string
  currency: string
  billing_interval: 'one_time' | 'monthly' | 'quarterly' | 'annual'
  quantity: string
  starts_on: string | null
  ends_on: string | null
  reference: string
}

export type CommercialContract = {
  id: string
  name: string
  provider_id: string
  provider_name: string
  kind: 'service' | 'support' | 'lease' | 'subscription' | 'other'
  status: 'draft' | 'active' | 'expired' | 'terminated'
  description: string
  reference: string
  starts_on: string | null
  ends_on: string | null
  renews_on: string | null
  auto_renew: boolean
  renewal_notice_days: number
  costs?: ContractCost[]
}

export type CommercialResult = {
  results: CommercialContract[]
  count: number
  can_manage: boolean
  can_view_costs: boolean
}

export interface CommercialClient {
  listContracts(workspace: WorkspaceContext, query: string, signal?: AbortSignal): Promise<CommercialResult>
  providerChoices(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: Array<{ id: string; name: string }> }>
  createContract(workspace: WorkspaceContext, values: object): Promise<CommercialContract>
  updateContract(workspace: WorkspaceContext, contractId: string, values: object): Promise<CommercialContract>
  archiveContract(workspace: WorkspaceContext, contractId: string): Promise<void>
  createCost(workspace: WorkspaceContext, contractId: string, values: object): Promise<CommercialContract>
  updateCost(workspace: WorkspaceContext, contractId: string, costId: string, values: object): Promise<CommercialContract>
  archiveCost(workspace: WorkspaceContext, contractId: string, costId: string): Promise<CommercialContract>
}

function basePath(workspace: WorkspaceContext) {
  return workspace.kind === 'msp'
    ? '/api/v1/workspaces/msp/contracts'
    : `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/contracts`
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
    throw new Error(errorText(body) ?? 'The commercial record request failed.')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return parse(await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
}

async function mutate<T>(path: string, method: string, body?: object): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse(await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    ...(body ? { body: JSON.stringify(body) } : {}),
  }))
}

export const browserCommercialClient: CommercialClient = {
  listContracts: (workspace, query, signal) => get(`${basePath(workspace)}?q=${encodeURIComponent(query)}`, signal),
  providerChoices: (workspace, signal) => get(`${basePath(workspace)}/providers`, signal),
  createContract: (workspace, values) => mutate(basePath(workspace), 'POST', values),
  updateContract: (workspace, contractId, values) => mutate(`${basePath(workspace)}/${encodeURIComponent(contractId)}`, 'PATCH', values),
  archiveContract: (workspace, contractId) => mutate(`${basePath(workspace)}/${encodeURIComponent(contractId)}`, 'DELETE'),
  createCost: (workspace, contractId, values) => mutate(`${basePath(workspace)}/${encodeURIComponent(contractId)}/costs`, 'POST', values),
  updateCost: (workspace, contractId, costId, values) => mutate(`${basePath(workspace)}/${encodeURIComponent(contractId)}/costs/${encodeURIComponent(costId)}`, 'PATCH', values),
  archiveCost: (workspace, contractId, costId) => mutate(`${basePath(workspace)}/${encodeURIComponent(contractId)}/costs/${encodeURIComponent(costId)}`, 'DELETE'),
}
