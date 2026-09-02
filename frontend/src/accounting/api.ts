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
  state: 'draft' | 'issued'
  number?: string
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
  issued_at?: string
  content_digest?: string
  signature_algorithm?: string
  key_fingerprint?: string
  delivered_at?: string | null
  delivery_count?: number
  lifecycle_state?: 'issued' | 'delivered' | 'externally_synchronized' | 'partially_paid' | 'paid' | 'overdue' | 'voided' | 'credited'
  reconciliation_state?: 'unsynchronized' | 'synchronized' | 'rejected' | 'duplicate' | 'externally_changed'
  paid_amount?: string
  balance_amount?: string
  last_event_at?: string | null
  lifecycle_events?: InvoiceLifecycleEvent[]
}

export type InvoiceLifecycleEvent = {
  id: string
  event_type: string
  occurred_at: string
  recorded_at: string
  actor: string | null
  provider: string
  external_id: string
  amount: string | null
  currency: string
  related_invoice_id: string | null
  note: string
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

export type InvoiceDateComponent = 'none' | 'year' | 'short_year' | 'year_month' | 'short_year_month' | 'month_year' | 'month_short_year' | 'year_month_code' | 'short_year_month_code'

export type InvoiceIssueSettings = {
  configured: boolean
  issue_ready: boolean
  readiness_issues: string[]
  legal_name: string
  address_line_1: string
  address_line_2: string
  city: string
  region: string
  postal_code: string
  country_code: string
  billing_email: string
  phone: string
  tax_registration: string
  default_currency: string
  payment_terms_days: number
  invoice_prefix: string
  invoice_date_component: InvoiceDateComponent
  invoice_separator: '-' | '/' | '.' | ''
  invoice_sequence_digits: number
  invoice_reset_period: 'never' | 'yearly' | 'monthly'
  country_choices: Array<{ value: string; label: string }>
}

export interface InvoiceClient {
  list(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ results: InvoiceDraft[]; can_manage: boolean; can_issue: boolean }>
  choices(workspace: WorkspaceContext, signal?: AbortSignal): Promise<{ origins: InvoiceOrigin[]; tax_rates: TaxRateChoice[] }>
  create(workspace: WorkspaceContext, values: object): Promise<InvoiceDraft>
  update(workspace: WorkspaceContext, invoiceId: string, values: object): Promise<InvoiceDraft>
  remove(workspace: WorkspaceContext, invoiceId: string): Promise<void>
  addLine(workspace: WorkspaceContext, invoiceId: string, values: object): Promise<InvoiceDraft>
  updateLine(workspace: WorkspaceContext, invoiceId: string, lineId: string, values: object): Promise<InvoiceDraft>
  removeLine(workspace: WorkspaceContext, invoiceId: string, lineId: string): Promise<InvoiceDraft>
  issueSettings(signal?: AbortSignal): Promise<InvoiceIssueSettings>
  saveIssueSettings(values: object): Promise<InvoiceIssueSettings>
  issue(workspace: WorkspaceContext, invoiceId: string): Promise<InvoiceDraft>
  deliver(workspace: WorkspaceContext, invoiceId: string, recipient: string): Promise<InvoiceDraft>
  recordEvent(workspace: WorkspaceContext, invoiceId: string, values: object): Promise<InvoiceDraft>
  pdfUrl(workspace: WorkspaceContext, invoiceId: string): string
  csvUrl(workspace: WorkspaceContext, invoiceId: string): string
  accountingExportUrl(workspace: WorkspaceContext, invoiceId: string): string
}

export class InvoiceRequestError extends Error {
  constructor(message: string, readonly status?: number, readonly code?: string) {
    super(message)
    this.name = 'InvoiceRequestError'
  }
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
    const envelope = body.error && typeof body.error === 'object' ? body.error as Record<string, unknown> : undefined
    throw new InvoiceRequestError(
      errorText(envelope?.detail) || errorText(body) || 'The invoice request failed.',
      response.status,
      typeof envelope?.code === 'string' ? envelope.code : undefined,
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  return parse(await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
}

async function mutate<T>(path: string, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', body?: object): Promise<T> {
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
  issueSettings: (signal) => read('/api/v1/workspaces/msp/invoice-settings', signal),
  saveIssueSettings: (values) => mutate('/api/v1/workspaces/msp/invoice-settings', 'PUT', values),
  issue: (workspace, invoiceId) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}/issue`, 'POST'),
  deliver: (workspace, invoiceId, recipient) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}/deliver`, 'POST', { recipient }),
  recordEvent: (workspace, invoiceId, values) => mutate(`${basePath(workspace)}/${encodeURIComponent(invoiceId)}/events`, 'POST', values),
  pdfUrl: (workspace, invoiceId) => `${basePath(workspace)}/${encodeURIComponent(invoiceId)}/pdf`,
  csvUrl: (workspace, invoiceId) => `${basePath(workspace)}/${encodeURIComponent(invoiceId)}/csv`,
  accountingExportUrl: (workspace, invoiceId) => `${basePath(workspace)}/${encodeURIComponent(invoiceId)}/accounting-export`,
}
