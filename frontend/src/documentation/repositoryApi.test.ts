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

it('pages exact-document evidence and checks finalized state in the selected organization', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ results: [], page: 2, page_size: 25, count: 0, has_more: false }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'static-1', verified: true }), { status: 200 }))
  vi.stubGlobal('fetch', fetch)
  expect((await browserRepositoryClient.listEvidence('content-1', 'org-1', 2)).page).toBe(2)
  expect(fetch).toHaveBeenNthCalledWith(1, '/api/v1/workspaces/organizations/org-1/repository-publication-evidence?content_id=content-1&page=2&page_size=25', {
    credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: undefined,
  })
  expect(await browserRepositoryClient.staticPublication('evidence-1', 'org-1')).toMatchObject({ id: 'static-1', verified: true })
  expect(fetch).toHaveBeenNthCalledWith(2, '/api/v1/workspaces/organizations/org-1/repository-publication-evidence/evidence-1/package/static-publication', {
    credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: undefined,
  })
})

it('treats unfinished STATIC records as unavailable while preserving authorization denial', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response('Pending', { status: 409 }))
    .mockResolvedValueOnce(new Response('Not found', { status: 404 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Denied' }), { status: 403 }))
  vi.stubGlobal('fetch', fetch)
  expect(await browserRepositoryClient.staticPublication('evidence-1')).toBeNull()
  expect(await browserRepositoryClient.staticPublication('evidence-1')).toBeNull()
  await expect(browserRepositoryClient.staticPublication('evidence-1')).rejects.toThrow('Denied')
})

it.each([
  ['md', 'markdown', 'text/markdown; charset=utf-8'],
  ['html', 'html', 'text/html; charset=utf-8'],
  ['pdf', 'pdf', 'application/pdf'],
] as const)('downloads a verified retained %s file from the organization approval route', async (format, endpoint, mediaType) => {
  const digest = 'd'.repeat(64)
  const fetch = vi.fn().mockResolvedValue(new Response('retained', {
    status: 200,
    headers: {
      'Content-Type': mediaType,
      'Content-Disposition': `attachment; filename="repository-static-publication.${format}"`,
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'private, no-store',
      'X-TekDocs-Export-Class': 'immutable_static_publication',
      'X-TekDocs-Publication-Digest': digest,
      ...(format === 'html' ? { 'Content-Security-Policy': "sandbox; default-src 'none'" } : {}),
    },
  }))
  vi.stubGlobal('fetch', fetch)
  const result = await browserRepositoryClient.exportStatic('evidence-1', format, digest, 'org-1')
  expect(result.name).toBe(`repository-static-publication.${format}`)
  expect(result.content.size).toBe(8)
  expect(fetch).toHaveBeenCalledWith(`/api/v1/workspaces/organizations/org-1/repository-publication-evidence/evidence-1/package/static-publication/export/${endpoint}`, {
    credentials: 'same-origin', signal: undefined,
  })
})

it('refuses denied, mislabeled, or wrong-publication retained responses', async () => {
  const digest = 'd'.repeat(64)
  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'Content-Disposition': 'attachment; filename="repository-static-publication.html"',
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'private, no-store',
    'X-TekDocs-Export-Class': 'immutable_static_publication',
    'X-TekDocs-Publication-Digest': 'a'.repeat(64),
    'Content-Security-Policy': "sandbox; default-src 'none'",
  }
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('Denied', { status: 403 }))
    .mockResolvedValueOnce(new Response('<html>Other record</html>', { status: 200, headers }))
    .mockResolvedValueOnce(new Response('<html>Wrong class</html>', { status: 200, headers: { ...headers, 'X-TekDocs-Publication-Digest': digest, 'X-TekDocs-Export-Class': 'live_repository_revision' } })))
  await expect(browserRepositoryClient.exportStatic('evidence-1', 'html', digest, 'org-1')).rejects.toThrow('could not be downloaded')
  await expect(browserRepositoryClient.exportStatic('evidence-1', 'html', digest, 'org-1')).rejects.toThrow('could not be downloaded')
  await expect(browserRepositoryClient.exportStatic('evidence-1', 'html', digest, 'org-1')).rejects.toThrow('could not be downloaded')
  await expect(browserRepositoryClient.exportStatic('evidence-1', 'html', digest)).rejects.toThrow('could not be downloaded')
})
