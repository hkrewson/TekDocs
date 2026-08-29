import type { WorkspaceContext } from '../workspaces/api'

export type InvoiceLine = {
  id: string
  position: number
  description: string
  quantity: string
  unit_amount: string
  currency: string
  tax_rate_name: string
  tax_rate_value: string
  tax_inclusive: boolean
  net: string
  tax: string
  total: string
  origin_type: '' | 'catalog_product' | 'service_rate' | 'contract_cost'
  origin_id: string | null
}

export type InvoiceDraft = {
  id: string
  state: 'draft'
  currency: string
  invoice_date: string
  due_date: string
  reference: string
  notes: string
  subtotal: string
  tax_total: string
  total: string
  lines: InvoiceLine[]
  created_at: string
  updated_at: string
}

export type InvoiceOrigin = {
  id: string
  origin_type: 'catalog_product' | 'service_rate' | 'contract_cost'
  name: string
  description: string
  unit_amount: string
  currency: string
  quantity: string
}

export type TaxRateChoice = { id: string; name: string; rate: string; inclusive: boolean }

export interface InvoiceClient {
  list(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: InvoiceDraft[]; can_manage: boolean }>
  choices(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ origins: InvoiceOrigin[]; tax_rates: TaxRateChoice[] }>
  create(workspace: WorkspaceContext, values: object): Promise<InvoiceDraft>
  update(workspace: WorkspaceContext, invoiceId: string, values: object): Promise<InvoiceDraft>
  remove(workspace: WorkspaceContext, invoiceId: string): Promise<void>
  addLine(workspace: WorkspaceContext, invoiceId: string, values: object): Promise<InvoiceDraft>
  updateLine(workspace: WorkspaceContext, invoiceId: string, lineId: string, values: object): Promise<InvoiceDraft>
  removeLine(workspace: WorkspaceContext, invoiceId: string, lineId: string): Promise<InvoiceDraft>
}

function basePath(workspace: WorkspaceContext) {
  return `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/invoices`
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
    throw new Error(errorText(body) ?? 'The invoice request failed.')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function mutate<T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: object): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse(await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    ...(body ? { body: JSON.stringify(body) } : {}),
  }))
}

export const browserInvoiceClient: InvoiceClient = {
  list: async (workspace, signal) => parse(await fetch(basePath(workspace), { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  choices: async (workspace, signal) => parse(await fetch(`${basePath(workspace)}/origin-choices`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  create: (workspace, values) => mutate(basePath(workspace), 'POST', values),
  update: (workspace, invoiceId, values) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}`, 'PATCH', values),
  remove: (workspace, invoiceId) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}`, 'DELETE'),
  addLine: (workspace, invoiceId, values) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}/lines`, 'POST', values),
  updateLine: (workspace, invoiceId, lineId, values) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}/lines/${encodeURIComponent(lineId)}`, 'PATCH', values),
  removeLine: (workspace, invoiceId, lineId) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}/lines/${encodeURIComponent(lineId)}`, 'DELETE'),
}
