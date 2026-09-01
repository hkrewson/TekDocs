import type { WorkspaceContext } from '../workspaces/api'

export const IMPORT_SOURCE_FORMATS = ['tekdocs_bundle', 'tekdocs_csv', 'itflow_csv', 'itglue_csv', 'hudu_csv'] as const
export const IMPORT_RECORD_TYPES = [
  'organizations', 'people', 'sites', 'locations', 'vendors', 'products', 'models', 'assets',
  'software_licenses', 'networks', 'documents', 'document_metadata', 'credential_references',
] as const

export type ImportSourceFormat = (typeof IMPORT_SOURCE_FORMATS)[number]
export type ImportRecordType = (typeof IMPORT_RECORD_TYPES)[number]
export type ImportAction = 'create' | 'update' | 'unchanged' | 'conflict' | 'rejected'

export type ImportBatch = {
  id: string
  source_format: ImportSourceFormat
  schema_version: number
  source_filename: string
  source_digest: string
  state: 'preview_ready' | 'applying' | 'applied' | 'cancelled' | 'failed'
  result_counts: Partial<Record<ImportAction, number>>
  last_error_code: string
  created_at: string
  expires_at: string
  applied_at: string | null
}

export type ImportRow = {
  id: string
  row_number: number
  record_type: ImportRecordType
  external_key: string
  action: ImportAction
  reason_code: string
  local_entity_id: string | null
}

export type ImportPage<T> = { results: T[]; page: number; page_size: number; count: number; has_more: boolean }

export interface ImportsClient {
  list(workspace: WorkspaceContext, signal?: AbortSignal): Promise<ImportPage<ImportBatch>>
  preview(workspace: WorkspaceContext, file: File, format: ImportSourceFormat, recordType?: ImportRecordType): Promise<ImportBatch>
  rows(workspace: WorkspaceContext, batch: ImportBatch, signal?: AbortSignal): Promise<ImportPage<ImportRow>>
  apply(workspace: WorkspaceContext, batch: ImportBatch, matches: Record<string, string>): Promise<ImportBatch>
  cancel(workspace: WorkspaceContext, batch: ImportBatch): Promise<ImportBatch>
  reportUrl(workspace: WorkspaceContext, batch: ImportBatch): string
  templateUrl(workspace: WorkspaceContext, recordType: ImportRecordType): string
}

function base(workspace: WorkspaceContext) {
  return workspace.kind === 'msp'
    ? '/api/v1/workspaces/msp/integrations/imports'
    : `/api/v1/workspaces/organizations/${encodeURIComponent(workspace.id)}/integrations/imports`
}

function csrfToken() {
  return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=')[1] ?? ''
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string; error?: { message?: string; fields?: Record<string, string[]> } }
    const fieldError = body.error?.fields && Object.values(body.error.fields).flat()[0]
    throw new Error(fieldError ?? body.error?.message ?? body.detail ?? 'The import request failed.')
  }
  return response.json() as Promise<T>
}

async function prepareMutation() {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
}

export const browserImportsClient: ImportsClient = {
  list: async (workspace, signal) => parse(await fetch(`${base(workspace)}?page=1&page_size=25`, {
    credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
  })),
  preview: async (workspace, file, sourceFormat, recordType) => {
    await prepareMutation()
    const body = new FormData()
    body.set('file', file)
    body.set('source_format', sourceFormat)
    if (sourceFormat !== 'tekdocs_bundle' && recordType) body.set('record_type', recordType)
    return parse(await fetch(base(workspace), {
      method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'X-CSRFToken': csrfToken() }, body,
    }))
  },
  rows: async (workspace, batch, signal) => parse(await fetch(`${base(workspace)}/${encodeURIComponent(batch.id)}/rows?page=1&page_size=100`, {
    credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
  })),
  apply: async (workspace, batch, matches) => {
    await prepareMutation()
    return parse(await fetch(`${base(workspace)}/${encodeURIComponent(batch.id)}/apply`, {
      method: 'POST', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ matches }),
    }))
  },
  cancel: async (workspace, batch) => {
    await prepareMutation()
    return parse(await fetch(`${base(workspace)}/${encodeURIComponent(batch.id)}/cancel`, {
      method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'X-CSRFToken': csrfToken() },
    }))
  },
  reportUrl: (workspace, batch) => `${base(workspace)}/${encodeURIComponent(batch.id)}/report`,
  templateUrl: (workspace, recordType) => `${base(workspace)}/templates/${encodeURIComponent(recordType)}`,
}
