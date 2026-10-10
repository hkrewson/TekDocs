import { afterEach, it, expect, vi } from 'vitest'
import { browserRepositoryClient } from './repositoryApi'

afterEach(() => vi.unstubAllGlobals())

it.each([undefined, 'org/1'])('uploads a scanned file to the exact saved document in workspace %s', async (organizationId) => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  const attachment = { id: '11111111-1111-4111-8111-111111111111', filename: 'steps.txt', size: 5, scan_status: 'clean' }
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(attachment), { status: 201 }))
  vi.stubGlobal('fetch', fetch)
  const file = new File(['steps'], 'steps.txt', { type: 'text/plain' })
  expect(await browserRepositoryClient.uploadAttachment('doc/1', file, organizationId)).toEqual(attachment)
  const scope = organizationId ? '/api/v1/workspaces/organizations/org%2F1' : '/api/v1/workspaces/msp'
  const [url, request] = fetch.mock.calls[0] as [string, RequestInit]
  expect(url).toBe(`${scope}/content-graph/authoring/doc%2F1/attachments`)
  expect(request.method).toBe('POST')
  expect(request.credentials).toBe('same-origin')
  expect(new Headers(request.headers).get('X-CSRFToken')).toBe('repository-csrf')
  expect(new Headers(request.headers).has('Content-Type')).toBe(false)
  expect(request.body).toBeInstanceOf(FormData)
  expect((request.body as FormData).get('file')).toBe(file)
})

it('reports upload denial and refuses an unscanned response', async () => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Upload denied' }), { status: 403 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: '11111111-1111-4111-8111-111111111111', filename: 'steps.txt', size: 5, scan_status: 'pending' }), { status: 201 })))
  const file = new File(['steps'], 'steps.txt')
  await expect(browserRepositoryClient.uploadAttachment('doc-1', file)).rejects.toThrow('Upload denied')
  await expect(browserRepositoryClient.uploadAttachment('doc-1', file)).rejects.toThrow('could not be attached')
})

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

it('downloads a checked editable bundle from the exact selected Workspace', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('bundle', {
    status: 200,
    headers: {
      'Content-Type': 'application/zip',
      'Content-Disposition': 'attachment; filename="tekdocs-repository-editable-aaaaaaaaaaaa.zip"',
      'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
    },
  }))
  vi.stubGlobal('fetch', fetch)
  const result = await browserRepositoryClient.exportEditableBundle('org-1')
  expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/org-1/content-graph/authoring/export?bundle=editable', {
    credentials: 'same-origin',
  })
  expect(result.name).toBe('tekdocs-repository-editable-aaaaaaaaaaaa.zip')
  expect(result.content.size).toBe(6)
})

it('refuses an editable bundle response without the expected download headers', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>sign in</html>', {
    status: 200, headers: { 'Content-Type': 'text/html' },
  })))
  await expect(browserRepositoryClient.exportEditableBundle()).rejects.toThrow('could not be downloaded')
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

it.each([undefined, 'org-1'])('downloads a revision-labeled live PDF in workspace %s', async (organizationId) => {
  const commit = 'a'.repeat(40)
  const fetch = vi.fn().mockResolvedValue(new Response('%PDF-saved', {
    status: 200,
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': 'attachment; filename="repository-document.pdf"',
      'X-TekDocs-Export-Class': 'live_repository_revision',
      'X-TekDocs-Repository-Commit': commit,
      'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  }))
  vi.stubGlobal('fetch', fetch)
  const result = await browserRepositoryClient.exportPdf('content-1', organizationId)
  expect(result).toMatchObject({ name: 'repository-document.pdf', commit })
  expect(result.content.type).toBe('application/pdf')
  expect(result.content.size).toBe(10)
  const scope = organizationId ? `/api/v1/workspaces/organizations/${organizationId}` : '/api/v1/workspaces/msp'
  expect(fetch).toHaveBeenCalledWith(`${scope}/content-graph/documents/content-1/export/pdf`, {
    credentials: 'same-origin',
  })
})

it('refuses denied, mislabeled, or non-PDF live responses', async () => {
  const headers = {
    'Content-Type': 'application/pdf',
    'Content-Disposition': 'attachment; filename="repository-document.pdf"',
    'X-TekDocs-Export-Class': 'live_repository_revision',
    'X-TekDocs-Repository-Commit': 'a'.repeat(40),
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff',
  }
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('Denied', { status: 403 }))
    .mockResolvedValueOnce(new Response('%PDF-wrong', { status: 200, headers: { ...headers, 'X-TekDocs-Export-Class': 'immutable_static_publication' } }))
    .mockResolvedValueOnce(new Response('not a PDF', { status: 200, headers })))
  await expect(browserRepositoryClient.exportPdf('content-1')).rejects.toThrow('saved PDF could not be downloaded')
  await expect(browserRepositoryClient.exportPdf('content-1')).rejects.toThrow('saved PDF could not be downloaded')
  await expect(browserRepositoryClient.exportPdf('content-1')).rejects.toThrow('saved PDF could not be downloaded')
})

it.each([undefined, 'org-1'])('downloads a revision-labeled live DOCX in workspace %s', async (organizationId) => {
  const commit = 'a'.repeat(40)
  const mediaType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  const fetch = vi.fn().mockResolvedValue(new Response('PK\x03\x04saved', {
    status: 200,
    headers: {
      'Content-Type': mediaType,
      'Content-Disposition': 'attachment; filename="repository-document.docx"',
      'X-TekDocs-Export-Class': 'live_repository_revision',
      'X-TekDocs-Repository-Commit': commit,
      'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  }))
  vi.stubGlobal('fetch', fetch)
  const result = await browserRepositoryClient.exportDocx('content-1', organizationId)
  expect(result).toMatchObject({ name: 'repository-document.docx', commit })
  expect(result.content.type).toBe(mediaType)
  expect(result.content.size).toBe(9)
  const scope = organizationId ? `/api/v1/workspaces/organizations/${organizationId}` : '/api/v1/workspaces/msp'
  expect(fetch).toHaveBeenCalledWith(`${scope}/content-graph/documents/content-1/export/docx`, {
    credentials: 'same-origin',
  })
})

it('refuses denied, mislabeled, or non-DOCX live responses', async () => {
  const headers = {
    'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'Content-Disposition': 'attachment; filename="repository-document.docx"',
    'X-TekDocs-Export-Class': 'live_repository_revision',
    'X-TekDocs-Repository-Commit': 'a'.repeat(40),
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff',
  }
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('Denied', { status: 403 }))
    .mockResolvedValueOnce(new Response('PK\x03\x04wrong', { status: 200, headers: { ...headers, 'X-TekDocs-Export-Class': 'immutable_static_publication' } }))
    .mockResolvedValueOnce(new Response('PK\x03\x04wrong', { status: 200, headers: { ...headers, 'X-TekDocs-Repository-Commit': 'wrong' } }))
    .mockResolvedValueOnce(new Response('not a DOCX', { status: 200, headers })))
  for (let index = 0; index < 4; index += 1) {
    await expect(browserRepositoryClient.exportDocx('content-1')).rejects.toThrow('saved DOCX could not be downloaded')
  }
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

it.each([undefined, 'org-1'])('downloads a verified review PDF in workspace %s', async (organizationId) => {
  const fetch = vi.fn().mockResolvedValue(new Response('%PDF-review', {
    status: 200,
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': 'attachment; filename="repository-evidence-snapshot.pdf"',
      'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  }))
  vi.stubGlobal('fetch', fetch)
  const result = await browserRepositoryClient.reviewPdf('evidence-1', organizationId)
  expect(result.name).toBe('repository-evidence-snapshot.pdf')
  expect(result.content.size).toBe(11)
  const prefix = organizationId ? `/api/v1/workspaces/organizations/${organizationId}` : '/api/v1/workspaces/msp'
  expect(fetch).toHaveBeenCalledWith(`${prefix}/repository-publication-evidence/evidence-1/review/pdf`, {
    credentials: 'same-origin', signal: undefined,
  })
})

it('refuses denial, a mislabeled review response, or non-PDF bytes', async () => {
  const headers = {
    'Content-Type': 'application/pdf',
    'Content-Disposition': 'attachment; filename="repository-evidence-snapshot.pdf"',
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff',
  }
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('Denied', { status: 403 }))
    .mockResolvedValueOnce(new Response('%PDF-review', { status: 200, headers: { ...headers, 'Content-Disposition': 'inline' } }))
    .mockResolvedValueOnce(new Response('not a pdf', { status: 200, headers })))
  await expect(browserRepositoryClient.reviewPdf('evidence-1')).rejects.toThrow('review PDF could not be downloaded')
  await expect(browserRepositoryClient.reviewPdf('evidence-1')).rejects.toThrow('review PDF could not be downloaded')
  await expect(browserRepositoryClient.reviewPdf('evidence-1')).rejects.toThrow('review PDF could not be downloaded')
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
