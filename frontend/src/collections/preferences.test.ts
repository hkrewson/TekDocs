import { beforeEach, expect, it, vi } from 'vitest'
import type { WorkspaceContext } from '../workspaces/api'
import { assetColumns, browserCollectionPreferences as client, defaultPreferences } from './preferences'

const msp = { kind: 'msp', id: 'installation' } as WorkspaceContext
const org = { kind: 'organization', id: 'client/one' } as WorkspaceContext
beforeEach(() => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=preferences-csrf' })
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(defaultPreferences(assetColumns))))))
})

it('projects allowed identifiers in curated order and scopes each request', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ columns: ['site', 'secret'], available_columns: ['site', 'name', 'secret'], default_columns: ['name', 'secret'], page_size: 50 })))
  const result = await client.load(org, 'assets', assetColumns)
  expect(result).toEqual({ columns: ['name', 'site'], available_columns: ['name', 'site'], default_columns: ['name'], page_size: 50 })
  expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2Fone/collection-preferences/assets', expect.objectContaining({ credentials: 'same-origin' }))
  await client.load(msp, 'assets', assetColumns)
  expect(fetch).toHaveBeenLastCalledWith('/api/v1/workspaces/msp/collection-preferences/assets', expect.any(Object))
})

it.each(['denied', 'unavailable', 'malformed'])('falls back to current safe defaults when %s', async (failure) => {
  if (failure === 'unavailable') vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
  else vi.mocked(fetch).mockResolvedValueOnce(new Response('{}', { status: failure === 'denied' ? 403 : 200 }))
  expect(await client.load(msp, 'assets', ['name'])).toEqual(defaultPreferences(['name']))
})

it('does not turn cancellation into stale defaults', async () => {
  const controller = new AbortController()
  controller.abort()
  vi.mocked(fetch).mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'))
  await expect(client.load(msp, 'assets', assetColumns, controller.signal)).rejects.toThrow('Aborted')
})

it('saves and resets with CSRF and does not retry failed writes', async () => {
  const draft = { columns: ['name'], page_size: 100 } as const
  await client.save(org, 'assets', draft)
  expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/collection-preferences/assets'), expect.objectContaining({ method: 'PUT', body: JSON.stringify(draft) }))
  expect((vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('preferences-csrf')
  await client.reset(org, 'assets')
  expect(fetch).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ method: 'DELETE' }))
  vi.mocked(fetch).mockClear().mockResolvedValueOnce(new Response('{}')).mockResolvedValueOnce(new Response('{}', { status: 403 }))
  await expect(client.save(org, 'assets', draft)).rejects.toThrow('403')
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(draft).toEqual({ columns: ['name'], page_size: 100 })
})
