export type StockMovement = {
  id: string
  movement_type: 'received' | 'used' | 'returned' | 'correction'
  quantity_change: string
  quantity_after: string
  client_id: string | null
  client_name: string | null
  note: string
  occurred_at: string
  recorded_at: string
  actor: string
}

export type StockItem = {
  id: string
  name: string
  description: string
  vendor_id: string | null
  vendor_name: string | null
  vendor_part_number: string
  unit: string
  quantity_on_hand: string
  reorder_level: string | null
  currency: string
  cost_per_unit: string
  client_price_per_unit: string
  purchase_quantity: string | null
  purchase_price: string | null
  order_total: string | null
  order_number: string
  order_url: string
  ordered_on: string | null
  tracking_number: string
  tracking_url: string
  movements: StockMovement[]
  created_at: string
  updated_at: string
}

export type StockChoice = { id: string; name: string }
export type StockResult = { results: StockItem[]; can_manage: boolean; vendors: StockChoice[]; clients: StockChoice[] }

export interface StockClient {
  list(signal?: AbortSignal): Promise<StockResult>
  create(values: object): Promise<StockItem>
  update(itemId: string, values: object): Promise<StockItem>
  archive(itemId: string): Promise<void>
  move(itemId: string, values: object): Promise<StockItem>
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
    throw new Error(errorText(body) || 'The stock request failed.')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const base = '/api/v1/workspaces/msp/stock'

async function mutate<T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: object): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse(await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    ...(body ? { body: JSON.stringify(body) } : {}),
  }))
}

export const browserStockClient: StockClient = {
  list: async (signal) => parse(await fetch(base, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  create: (values) => mutate(base, 'POST', values),
  update: (itemId, values) => mutate(`${base}/${encodeURIComponent(itemId)}`, 'PATCH', values),
  archive: (itemId) => mutate(`${base}/${encodeURIComponent(itemId)}`, 'DELETE'),
  move: (itemId, values) => mutate(`${base}/${encodeURIComponent(itemId)}/movements`, 'POST', values),
}
