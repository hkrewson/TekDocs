import type { components } from '../generated/api-v1'
import type { WorkspaceContext } from '../workspaces/api'
import { browserInvoiceClient, mutate, read } from './api'
import type { TaxRateChoice } from './api'
import type { RecurringSchedule } from './recurringApi'
export type EnrollmentReview = components['schemas']['RecurringSource']
export type EnrollmentValues = components['schemas']['RecurringEnrollment']
export type EnrollmentSources = components['schemas']['RecurringSourcePage']
export interface EnrollmentClient {
  sources(this: void, workspace: WorkspaceContext, q: string, page: number, signal?: AbortSignal): Promise<EnrollmentSources>
  review(this: void, workspace: WorkspaceContext, id: string): Promise<EnrollmentReview>
  taxes(this: void, workspace: WorkspaceContext): Promise<TaxRateChoice[]>
  enroll(this: void, workspace: WorkspaceContext, values: EnrollmentValues): Promise<RecurringSchedule>
}
const base = (workspace: WorkspaceContext) => `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/recurring-invoices`
export const browserEnrollmentClient: EnrollmentClient = {
  sources: (workspace, q, page, signal) => read(`${base(workspace)}/sources?${new URLSearchParams({ q, page: String(page), page_size: '20' })}`, signal),
  review: (workspace, id) => read(`${base(workspace)}/sources/${encodeURIComponent(id)}`),
  taxes: async (workspace) => (await browserInvoiceClient.choices(workspace)).tax_rates,
  enroll: (workspace, values) => mutate(base(workspace), 'POST', values),
}
