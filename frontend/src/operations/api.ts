import { AuthRequestError, browserCsrfToken, privilegedActionError } from '../auth/api'
import type { DocumentScope } from '../documentation/api'

export type ReminderRecord = {
  id: string
  source_entity_id: string
  source: string
  domain: 'compliance' | 'inventory' | 'domain' | 'documentation' | 'invoice'
  kind: string
  title: string
  due_on: string
  lead_days: number
  recurrence: 'none' | 'annual'
  owner_id: string | null
  owner: string | null
  active: boolean
  created_at: string
}

export type ReminderInput = Pick<ReminderRecord, 'source_entity_id' | 'domain' | 'kind' | 'title' | 'due_on' | 'lead_days' | 'recurrence'>

export type ActivityRecord = {
  id: string
  action: string
  actor_id: string | null
  actor_name: string | null
  entity_id: string | null
  entity_name: string | null
  entity_type: string | null
  request_id: string | null
  occurred_at: string
}

export type ActivityResult = {
  results: ActivityRecord[]
  count: number
  page: number
  page_size: number
  has_more: boolean
  actions: string[]
}

export interface OperationsClient {
  reminders(scope: DocumentScope, signal?: AbortSignal): Promise<ReminderRecord[]>
  createReminder(scope: DocumentScope, input: ReminderInput): Promise<ReminderRecord>
  reminderCalendarUrl(scope: DocumentScope): string
  activity(scope: DocumentScope, filters: { q?: string; occurred_after?: string; occurred_before?: string; page?: number }, signal?: AbortSignal): Promise<ActivityResult>
}

function workspacePath(scope: DocumentScope) {
  return scope.organizationId
    ? `/api/v1/workspaces/organizations/${encodeURIComponent(scope.organizationId)}`
    : '/api/v1/workspaces/msp'
}

async function parse<T>(response: Response | Promise<Response>, fallback: string): Promise<T> {
  const resolved = await response
  if (!resolved.ok) throw await privilegedActionError(resolved, fallback)
  return resolved.json() as Promise<T>
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

export const browserOperationsClient: OperationsClient = {
  reminders: (scope, signal) => parse<ReminderRecord[]>(fetch(`${workspacePath(scope)}/reminders`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }), 'Reminders could not be loaded.'),
  async createReminder(scope, input) {
    return parse<ReminderRecord>(fetch(`${workspacePath(scope)}/reminders`, {
      method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': await csrfToken() }, body: JSON.stringify(input),
    }), 'The reminder could not be created.')
  },
  reminderCalendarUrl: (scope) => `${workspacePath(scope)}/reminders/calendar.ics`,
  activity(scope, filters, signal) {
    const query = new URLSearchParams({ page: String(filters.page ?? 1), page_size: '50' })
    if (filters.q) query.set('q', filters.q)
    if (filters.occurred_after) query.set('occurred_after', filters.occurred_after)
    if (filters.occurred_before) query.set('occurred_before', filters.occurred_before)
    const base = scope.organizationId ? `${workspacePath(scope)}/activity` : '/api/v1/activity'
    return parse<ActivityResult>(fetch(`${base}?${query}`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal }), 'Activity could not be loaded.')
  },
}
