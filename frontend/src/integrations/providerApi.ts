import type { WorkspaceContext } from '../workspaces/api'

export type IntegrationConnection = { id: string; provider: 'netbox'; name: string; base_url: string; credential_configured: boolean; secret_generation: number; active: boolean; sync_interval_minutes: number; next_sync_at: string; created_at: string; updated_at: string }
export type IntegrationConnectionDraft = { provider: 'netbox'; name: string; base_url: string; api_token: string; sync_interval_minutes: number }
export type IntegrationJob = { id: string; connection_id: string; connection_name: string; trigger: 'manual' | 'scheduled'; state: 'pending' | 'processing' | 'succeeded' | 'dead_letter'; attempts: number; cursor_present: boolean; last_error_code: string; result_counts: Record<string, number>; available_at: string; started_at: string | null; finished_at: string | null; created_at: string }
export type IntegrationLog = { id: string; connection_id: string; connection_name: string; job_id: string | null; level: 'info' | 'warning' | 'error'; code: string; metrics: Record<string, number>; occurred_at: string }
export type IntegrationConflict = { id: string; connection_id: string; connection_name: string; local_entity_id: string | null; remote_type: string; remote_id: string; difference: string; status: 'open' | 'keep_local' | 'accept_remote' | 'ignored'; created_at: string; resolved_at: string | null }
export type IntegrationPage<T> = { results: T[]; page: number; page_size: number; count: number; has_more: boolean }
export type GitExportBundle = { id: string; selection_manifest: { documents: { entity_id: string; path: string }[]; publications: { entity_id: string }[] }; content_digest: string; byte_size: number; created_at: string }

export interface IntegrationsClient {
  listConnections(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationConnection[]>
  createConnection(workspace: WorkspaceContext, draft: IntegrationConnectionDraft): Promise<IntegrationConnection>
  updateConnection(workspace: WorkspaceContext, connection: IntegrationConnection, active: boolean): Promise<IntegrationConnection>
  rotateConnection(workspace: WorkspaceContext, connection: IntegrationConnection, apiToken: string): Promise<IntegrationConnection>
  startSync(workspace: WorkspaceContext, connection: IntegrationConnection): Promise<IntegrationJob>
  listJobs(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationPage<IntegrationJob>>
  listLogs(workspace: WorkspaceContext, signal?: AbortSignal): Promise<IntegrationPage<IntegrationLog>>
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
  listConnections: async (workspace, signal) => parse(await fetch(`${base(workspace)}/connections`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  createConnection: (workspace, draft) => mutate(`${base(workspace)}/connections`, 'POST', draft),
  updateConnection: (workspace, connection, active) => mutate(`${base(workspace)}/connections/${encodeURIComponent(connection.id)}`, 'PATCH', { active, sync_interval_minutes: connection.sync_interval_minutes }),
  rotateConnection: (workspace, connection, api_token) => mutate(`${base(workspace)}/connections/${encodeURIComponent(connection.id)}/rotate`, 'POST', { api_token }),
  startSync: (workspace, connection) => mutate(`${base(workspace)}/jobs`, 'POST', { connection_id: connection.id }, { 'Idempotency-Key': `browser:${crypto.randomUUID()}` }),
  listJobs: async (workspace, signal) => parse(await fetch(`${base(workspace)}/jobs?page=1&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  listLogs: async (workspace, signal) => parse(await fetch(`${base(workspace)}/logs?page=1&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  listConflicts: async (workspace, signal) => parse(await fetch(`${base(workspace)}/conflicts?page=1&page_size=50`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  resolveConflict: (workspace, conflict, resolution) => mutate(`${base(workspace)}/conflicts/${encodeURIComponent(conflict.id)}/resolve`, 'POST', { resolution }),
  listGitExports: async (workspace, signal) => parse(await fetch(`${base(workspace)}/git-exports`, { credentials: 'same-origin', headers: { Accept: 'application/json' }, signal })),
  createGitExport: (workspace, document_ids, publication_ids) => mutate(`${base(workspace)}/git-exports`, 'POST', { document_ids, publication_ids }),
  gitExportDownloadUrl: (workspace, bundle) => `${base(workspace)}/git-exports/${encodeURIComponent(bundle.id)}/download`,
}
