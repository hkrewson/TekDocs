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

it('downloads live repository HTML only from the exact organization route with revision evidence', async () => {
  const commit = 'a'.repeat(40)
  const fetch = vi.fn().mockResolvedValue(new Response('<html>Saved</html>', {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Disposition': 'attachment; filename="repository-document.html"',
      'X-TekDocs-Export-Class': 'live_repository_revision',
      'X-TekDocs-Repository-Commit': commit,
    },
  }))
  vi.stubGlobal('fetch', fetch)
  const result = await browserRepositoryClient.exportHtml('content-1', 'org-1')
  expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/org-1/content-graph/documents/content-1/export/html', {
    credentials: 'same-origin',
  })
  expect(result).toMatchObject({ name: 'repository-document.html', commit })
  const reader = new FileReader()
  const loaded = new Promise<string>((resolve) => { reader.onload = () => resolve(reader.result as string) })
  reader.readAsText(result.content)
  expect(await loaded).toBe('<html>Saved</html>')
})

it('refuses denied or unlabeled HTML responses', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response('Denied', { status: 403 }))
    .mockResolvedValueOnce(new Response('<html>Unexpected</html>', { status: 200, headers: { 'Content-Type': 'text/html' } }))
  vi.stubGlobal('fetch', fetch)
  await expect(browserRepositoryClient.exportHtml('content-1')).rejects.toThrow('could not be downloaded')
  await expect(browserRepositoryClient.exportHtml('content-1')).rejects.toThrow('could not be downloaded')
})
