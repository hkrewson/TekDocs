import { AuthRequestError } from '../auth/api'

export type RendererFailure = { code: string; occurred_at: number }
export type SystemDiagnostics = {
  status: 'ready' | 'degraded'
  checked_at: string
  application_version: string
  database: 'ready'
  diagram_renderer: {
    status: 'ready' | 'stale' | 'unavailable' | 'not_configured'
    version: string | null
    capacity: number
    queue: { waiting: number; processing: number; total: number }
    recent_failures: RendererFailure[]
    last_checked_at: number | null
  }
}

export interface SystemStatusClient {
  load(signal?: AbortSignal): Promise<SystemDiagnostics>
}

async function load(signal?: AbortSignal): Promise<SystemDiagnostics> {
  const response = await fetch('/api/v1/system/diagnostics', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) {
    throw new AuthRequestError(
      response.status === 403
        ? 'Your account is not authorized to view system status.'
        : 'System status could not be loaded.',
      response.status,
    )
  }
  try {
    return await response.json() as SystemDiagnostics
  } catch {
    throw new AuthRequestError('The server returned an unreadable system-status response.', response.status)
  }
}

export const browserSystemStatusClient: SystemStatusClient = { load }
