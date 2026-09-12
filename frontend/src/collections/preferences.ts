import type { components } from '../generated/api-v1'
import type { WorkspaceContext } from '../workspaces/api'

export type CollectionPreferences = components['schemas']['CollectionPreference']
export type CollectionPreferenceWrite = components['schemas']['CollectionPreferenceWrite']
export const assetColumns = ['name', 'model', 'status', 'assignment', 'site', 'warranty'] as const

// Callers provide only columns allowed by their current feature policy. Never
// cache preferences across users or workspaces: permission projections can differ.
export function defaultPreferences(allowed: readonly string[]): CollectionPreferences {
  return { columns: [...allowed], available_columns: [...allowed], default_columns: [...allowed], page_size: 25 }
}

function path(workspace: WorkspaceContext, feature: string) {
  const root = workspace.kind === 'msp' ? 'msp' : `organizations/${encodeURIComponent(workspace.id)}`
  return `/api/v1/workspaces/${root}/collection-preferences/${encodeURIComponent(feature)}`
}

function stringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every((item: unknown) => typeof item === 'string')
}

async function readResponse(response: Response): Promise<CollectionPreferences> {
  if (!response.ok) throw new Error(`Collection preferences request failed (${response.status})`)
  const value = await response.json() as CollectionPreferences
  if (![25, 50, 100].includes(value.page_size) || !stringArray(value.columns)
    || !stringArray(value.available_columns) || !stringArray(value.default_columns)) {
    throw new Error('Invalid collection preferences response')
  }
  return value
}

export const browserCollectionPreferences = {
  async load(workspace: WorkspaceContext, feature: string, allowed: readonly string[], signal?: AbortSignal): Promise<CollectionPreferences> {
    try {
      const value = await readResponse(await fetch(path(workspace, feature), {
        credentials: 'same-origin', headers: { Accept: 'application/json' }, signal,
      }))
      const available = allowed.filter((column) => value.available_columns.includes(column))
      return {
        columns: available.filter((column) => column === 'name' || value.columns.includes(column)),
        default_columns: available.filter((column) => value.default_columns.includes(column)),
        available_columns: available,
        page_size: value.page_size,
      }
    } catch (error) {
      if (signal?.aborted) throw error
      return defaultPreferences(allowed)
    }
  },
  save(workspace: WorkspaceContext, feature: string, value: CollectionPreferenceWrite): Promise<CollectionPreferences> {
    return mutate(workspace, feature, 'PUT', value)
  },
  reset(workspace: WorkspaceContext, feature: string): Promise<CollectionPreferences> {
    return mutate(workspace, feature, 'DELETE')
  },
}

async function mutate(workspace: WorkspaceContext, feature: string, method: 'PUT' | 'DELETE', value?: CollectionPreferenceWrite) {
  await fetch('/_allauth/browser/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  const csrf = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrftoken='))?.split('=')[1] ?? ''
  // No automatic mutation retry or fallback: the future editor retains its draft
  // and presents a failure instead of pretending that persistence succeeded.
  return readResponse(await fetch(path(workspace, feature), {
    method, credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
    ...(value ? { body: JSON.stringify(value) } : {}),
  }))
}
