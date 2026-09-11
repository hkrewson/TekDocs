import type { components } from '../generated/api-v1'
import type { WorkspaceContext } from '../workspaces/api'
import { read, mutate } from './api'

export type RecurringSchedule = components['schemas']['RecurringSchedule']
export type RecurringPreview = components['schemas']['RecurringPreview']
export type RecurringDue = components['schemas']['RecurringDue']
export type RecurringClaim = components['schemas']['RecurringClaim']
export type RecurringPage = components['schemas']['RecurringSchedulePage']
export interface RecurringClient {
  list(this: void, workspace: WorkspaceContext, page: number, signal?: AbortSignal): Promise<RecurringPage>
  due(this: void, workspace: WorkspaceContext, id: string, from: string, asOf: string, signal?: AbortSignal): Promise<RecurringDue>
  preview(this: void, workspace: WorkspaceContext, id: string, starts: string[], asOf: string): Promise<RecurringPreview>
  apply(this: void, workspace: WorkspaceContext, id: string, token: string): Promise<readonly RecurringClaim[]>
}
const base = (workspace: WorkspaceContext) => `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/recurring-invoices`
export const browserRecurringClient: RecurringClient = {
  list: (workspace, page, signal) => read(`${base(workspace)}?${new URLSearchParams({ page: String(page), page_size: '20' })}`, signal),
  due: (workspace, id, from, asOf, signal) => read(`${base(workspace)}/${encodeURIComponent(id)}/due?${new URLSearchParams({ due_from: from, as_of: asOf })}`, signal),
  preview: (workspace, id, starts, asOf) => mutate(`${base(workspace)}/${encodeURIComponent(id)}/preview`, 'POST', { starts_on: starts, as_of: asOf }),
  apply: (workspace, id, token) => mutate(`${base(workspace)}/${encodeURIComponent(id)}/apply`, 'POST', { preview_token: token }),
}
