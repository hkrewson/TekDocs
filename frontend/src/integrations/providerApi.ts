import type { WorkspaceContext } from '../workspaces/api'

export type IntegrationProvider = { key: string; label: string; version: string; direction: 'read_only'; credential_fields: { key: string; label: string; secret: boolean; minimum_length: number; input_type: string; help_text: string }[]; capabilities: string[]; object_types: string[]; pagination: string; minimum_sync_interval_minutes: number; maximum_sync_interval_minutes: number; health_states: string[]; observation_schema_version: number; default_base_url: string; base_url_editable: boolean; setup_help_url: string }
export type IntegrationConnection = { id: string; provider: string; name: string; base_url: string; provider_details: Record<string, string>; credential_configured: boolean; secret_generation: number; active: boolean; sync_interval_minutes: number; next_sync_at: string; health_status: string; last_successful_sync_at: string | null; last_error_code: string; rate_limit_reset_at: string | null; reconciliation_counts: Record<string, number>; created_at: string; updated_at: string }
export type IntegrationConnectionDraft = { provider: string; name: string; base_url: string; credentials: Record<string, string>; sync_interval_minutes: number }
export type IntegrationJob = { id: string; connection_id: string; connection_name: string; trigger: 'manual' | 'scheduled'; state: 'pending' | 'processing' | 'succeeded' | 'dead_letter' | 'cancelled'; attempts: number; cursor_present: boolean; last_error_code: string; result_counts: Record<string, number>; available_at: string; started_at: string | null; finished_at: string | null; created_at: string }
export type IntegrationLog = { id: string; connection_id: string; connection_name: string; job_id: string | null; level: 'info' | 'warning' | 'error'; code: string; metrics: Record<string, number>; occurred_at: string }
export type IntegrationObservation = { id: string; connection_id: string; connection_name: string; remote_type: string; remote_id: string; safe_projection: Record<string, string | number | boolean | null>; source_timestamp: string | null; state: 'observed' | 'retired'; observed_at: string }
export type IntegrationConflict = { id: string; connection_id: string; connection_name: string; local_entity_id: string | null; remote_type: string; remote_id: string; difference: string; status: 'open' | 'keep_local' | 'accept_remote' | 'ignored'; created_at: string; resolved_at: string | null }
export type IntegrationPage<T> = { results: T[]; page: number; page_size: number; count: number; has_more: boolean }
export type GitExportBundle = { id: string; selection_manifest: { documents: { entity_id: string; path: string }[]; publications: { entity_id: string }[] }; content_digest: string; byte_size: number; created_at: string }

export interface IntegrationsClient {
  listProviders(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationProvider[]>
  listConnections(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationConnection[]>
  createConnection(workspace: WorkspaceContext, draft: IntegrationConnectionDraft): Promise<IntegrationConnection>
  updateConnection(workspace: WorkspaceContext, connection: IntegrationConnection, active: boolean): Promise<IntegrationConnection>
  rotateConnection(workspace: WorkspaceContext, connection: IntegrationConnection, credentials: Record<string, string>): Promise<IntegrationConnection>
  startSync(workspace: WorkspaceContext, connection: IntegrationConnection): Promise<IntegrationJob>
  listJobs(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationPage<IntegrationJob>>
  cancelJob(workspace: WorkspaceContext, job: IntegrationJob): Promise<IntegrationJob>
  listLogs(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationPage<IntegrationLog>>
  listObservations(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationPage<IntegrationObservation>>
  listConflicts(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationPage<IntegrationConflict>>
  resolveConflict(workspace: WorkspaceContext, conflict: IntegrationConflict, resolution: 'keep_local' | 'accept_remote' | 'ignored'): Promise<IntegrationConflict>
  listGitExports(workspace: WorkspaceContext, signal?: AbortSignal): Promise<GitExportBundle[]>
  createGitExport(workspace: WorkspaceContext, documentIds: string[], publicationIds: string[]): Promise<GitExportBundle>
  gitExportDownloadUrl(workspace: WorkspaceContext, bundle: GitExportBundle): string
}

function base(workspace: WorkspaceContext) { return workspace.kind === 'msp' ? '/api/v1/workspaces/msp/integrations' : `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/integrations` }
function csrfToken() { return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? '' }
async function parse<T>(response: Response): Promise<T> { if (!response.ok) { const body = await response.json().catch(() => ({})) as { detail?: string; error?: { message?: string } }; throw new Error(body.error?.message ?? body.detail ?? 'The integration request failed.') } return response.json() as Promise<T> }
async function mutate<T>(path: string, method: 'POST' | 'PATCH', body: unknown, extra: Record<string, string> = {}): Promise<T> { await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } }); return parse(await fetch(path, { method, credentials: 'same-origin', headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), ...extra }, body: JSON.stringify(body) })) }

export const browserIntegrationsClient: IntegrationsClient = {
  listProviders: async (workspace, signal) => parse(await fetch(`${base(workspace)}/providers`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  listConnections: async (workspace, signal) => parse(await fetch(`${base(workspace)}/connections`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  createConnection: (workspace, draft) => mutate(`${base(workspace)}/connections`, 'POST', draft),
  updateConnection: (workspace, connection, active) => mutate(`${base(workspace)}/connections/${encodeURIComponent(connection.id)}`, 'PATCH', { active, sync_interval_minutes: connection.sync_interval_minutes }),
  rotateConnection: (workspace, connection, credentials) => mutate(`${base(workspace)}/connections/${encodeURIComponent(connection.id)}/rotate`, 'POST', { credentials }),
  startSync: (workspace, connection) => mutate(`${base(workspace)}/jobs`, 'POST', { connection_id: connection.id }, { 'Idempotency-Key': `browser:${crypto.randomUUID()}` }),
  listJobs: async (workspace, signal) => parse(await fetch(`${base(workspace)}/jobs?page=1&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  cancelJob: (workspace, job) => mutate(`${base(workspace)}/jobs/${encodeURIComponent(job.id)}/cancel`, 'POST', {}),
  listLogs: async (workspace, signal) => parse(await fetch(`${base(workspace)}/logs?page=1&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  listObservations: async (workspace, signal) => parse(await fetch(`${base(workspace)}/observations?page=1&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  listConflicts: async (workspace, signal) => parse(await fetch(`${base(workspace)}/conflicts?page=1&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  resolveConflict: (workspace, conflict, resolution) => mutate(`${base(workspace)}/conflicts/${encodeURIComponent(conflict.id)}/resolve`, 'POST', { resolution }),
  listGitExports: async (workspace, signal) => parse(await fetch(`${base(workspace)}/git-exports`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  createGitExport: (workspace, document_ids, publication_ids) => mutate(`${base(workspace)}/git-exports`, 'POST', { document_ids, publication_ids }),
  gitExportDownloadUrl: (workspace, bundle) => `${base(workspace)}/git-exports/${encodeURIComponent(bundle.id)}/download`,
}
