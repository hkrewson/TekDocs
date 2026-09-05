import { beforeEach, expect, it, vi } from 'vitest'
import { browserSystemStatusClient } from './api'

beforeEach(() => vi.restoreAllMocks())

it('loads the authorized value-free system diagnostics route', async () => {
  const payload = { status: 'ready', diagram_renderer: { recent_failures: [] } }
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }))

  await expect(browserSystemStatusClient.load()).resolves.toEqual(payload)
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/system/diagnostics', expect.objectContaining({ credentials: 'same-origin' }))
})

it('explains when system diagnostics are not authorized', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 403 }))
  await expect(browserSystemStatusClient.load()).rejects.toThrow('not authorized')
})
