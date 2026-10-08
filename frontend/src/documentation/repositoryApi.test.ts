import { afterEach, it, expect, vi } from 'vitest'
import { browserRepositoryClient } from './repositoryApi'

afterEach(() => vi.unstubAllGlobals())

it('downloads an organization source ZIP without requesting an unsupported JSON renderer', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('zip', {
    status: 200,
    headers: { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="tekdocs-repository-aaaaaaaaaaaa.zip"' },
  }))
  vi.stubGlobal('fetch', fetch)
  const result = await browserRepositoryClient.exportSources('org-1')
  expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/org-1/content-graph/authoring/export', {
    credentials: 'same-origin',
  })
  expect(result.name).toBe('tekdocs-repository-aaaaaaaaaaaa.zip')
  expect(result.content.size).toBe(3)
})

it('reports a denied source snapshot instead of treating the error as a download', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Repository is not indexed' }), {
    status: 409, headers: { 'Content-Type': 'application/json' },
  })))
  await expect(browserRepositoryClient.exportSources()).rejects.toThrow('Repository is not indexed')
})

it('refuses a successful upstream response that is not a ZIP', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>sign in</html>', {
    status: 200, headers: { 'Content-Type': 'text/html' },
  })))
  await expect(browserRepositoryClient.exportSources()).rejects.toThrow('could not be downloaded')
})
