import type { WorkspaceContext } from '../workspaces/api'

export type WebhookDirection = 'outbound' | 'inbound'
export type WebhookEndpoint = {
  id: string; direction: WebhookDirection; name: string; url: string; inbound_path: string | null
  topics: string[]; secret_prefix: string; secret_generation: number; active: boolean
  created_at: string; updated_at: string
}
export type IssuedWebhookEndpoint = WebhookEndpoint & { signing_secret: string }
export type WebhookDelivery = {
  id: string; endpoint_id: string; endpoint_name: string; topic: string
  state: 'pending' | 'processing' | 'delivered' | 'dead_letter'; attempts: number
  available_at: string; last_attempt_at: string | null; delivered_at: string | null
  response_status: number | null; last_error_code: string; created_at: string
}
export type WebhookDeliveryResult = { results: WebhookDelivery[]; page: number; page_size: number; count: number; has_more: boolean }
export type WebhookDraft = { name: string; direction: WebhookDirection; url: string; topics: string[] }

export interface WebhooksClient {
  listEndpoints(workspace: WorkspaceContext, signal?: AbortSignal): Promise<WebhookEndpoint[]>
  createEndpoint(workspace: WorkspaceContext, draft: WebhookDraft): Promise<IssuedWebhookEndpoint>
  setActive(workspace: WorkspaceContext, endpoint: WebhookEndpoint, active: boolean): Promise<WebhookEndpoint>
  rotate(workspace: WorkspaceContext, endpoint: WebhookEndpoint): Promise<IssuedWebhookEndpoint>
  listDeliveries(workspace: WorkspaceContext, page: number, state?: string, signal?: AbortSignal): Promise<WebhookDeliveryResult>
  retry(workspace: WorkspaceContext, delivery: WebhookDelivery, reason: string): Promise<WebhookDelivery>
}

function base(workspace: WorkspaceContext) {
  return `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/integrations/webhooks`
}


function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string; error?: { message?: string } }
    throw new Error(body.error?.message ?? body.detail ?? 'The webhook request failed.')
  }
  return response.json() as Promise<T>
}

async function mutate<T>(path: string, method: 'POST' | 'PATCH', body?: unknown): Promise<T> {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  return parse<T>(await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  }))
}

export const browserWebhooksClient: WebhooksClient = {
  listEndpoints: async (workspace, signal) => parse(await fetch(`${base(workspace)}/endpoints`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  createEndpoint: (workspace, draft) => mutate(`${base(workspace)}/endpoints`, 'POST', draft),
  setActive: (workspace, endpoint, active) => mutate(`${base(workspace)}/endpoints/${encodeURIComponent(endpoint.id)}`, 'PATCH', { active }),
  rotate: (workspace, endpoint) => mutate(`${base(workspace)}/endpoints/${encodeURIComponent(endpoint.id)}/rotate`, 'POST'),
  listDeliveries: async (workspace, page, state, signal) => {
    const query = new URLSearchParams({ page: String(page), page_size: '25' })
    if (state) query.set('state', state)
    return parse(await fetch(`${base(workspace)}/deliveries?${query}`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }))
  },
  retry: (workspace, delivery, reason) => mutate(`${base(workspace)}/deliveries/${encodeURIComponent(delivery.id)}/retry`, 'POST', { reason }),
}
