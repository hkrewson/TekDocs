import { afterEach, it, expect, vi } from 'vitest'
import { browserRepositoryClient, RepositoryPrimaryFileConflictError, RepositoryRecentAuthenticationRequiredError } from './repositoryApi'

afterEach(() => vi.unstubAllGlobals())

const primary = {
  id: '11111111-1111-4111-8111-111111111111', filename: 'primary.txt', size: 5, media_type: 'text/plain',
  checksum: 'a'.repeat(64), scan_status: 'clean' as const, scan_engine: 'synthetic',
  scanned_at: '2026-11-03T12:00:00Z', created_at: '2026-11-03T12:00:00Z',
  version_number: 1, replaces_id: null, is_current: true,
}

it.each([undefined, 'org/1'])('reads and downloads primary-file history in exact workspace %s', async organizationId => {
  const page = { results: [primary], count: 1, page: 1, page_size: 25, has_more: false }
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(page)))
  vi.stubGlobal('fetch', fetch)
  const controller = new AbortController()
  expect(await browserRepositoryClient.primaryFiles('doc/1', organizationId, 1, controller.signal)).toEqual(page)
  const scope = organizationId ? '/api/v1/workspaces/organizations/org%2F1/content-graph' : '/api/v1/workspaces/msp/content-graph'
  expect(fetch).toHaveBeenCalledWith(scope + '/authoring/doc%2F1/primary-file?page=1', {
    credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: controller.signal,
  })
  expect(browserRepositoryClient.primaryFileDownloadUrl('doc/1', 'file/1', organizationId)).toBe(scope + '/documents/doc%2F1/attachments/file%2F1/download')
})

it.each([null, '22222222-2222-4222-8222-222222222222'])('compares primary-file intake against reviewed predecessor %s', async expectedCurrentId => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  const result = { ...primary, version_number: expectedCurrentId ? 2 : 1, replaces_id: expectedCurrentId }
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 201 }))
  vi.stubGlobal('fetch', fetch)
  const file = new File(['first'], 'primary.txt')
  const controller = new AbortController()
  expect(await browserRepositoryClient.appendPrimaryFile('doc/1', file, expectedCurrentId, 'org/1', controller.signal)).toEqual(result)
  const [url, request] = fetch.mock.calls[0] as [string, RequestInit]
  expect(url).toBe('/api/v1/workspaces/organizations/org%2F1/content-graph/authoring/doc%2F1/primary-file')
  expect(request).toMatchObject({ method: 'POST', credentials: 'same-origin', signal: controller.signal })
  expect(new Headers(request.headers).get('X-CSRFToken')).toBe('repository-csrf')
  expect(new Headers(request.headers).has('Content-Type')).toBe(false)
  expect((request.body as FormData).get('file')).toBe(file)
  expect((request.body as FormData).get('expected_current_id')).toBe(expectedCurrentId)
})

it('keeps primary-version conflicts distinct from permission denial', async () => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('{}', { status: 409 })).mockResolvedValueOnce(new Response('{}', { status: 403 })))
  const file = new File(['first'], 'primary.txt')
  await expect(browserRepositoryClient.appendPrimaryFile('doc', file, null)).rejects.toBeInstanceOf(RepositoryPrimaryFileConflictError)
  await expect(browserRepositoryClient.appendPrimaryFile('doc', file, null)).rejects.not.toBeInstanceOf(RepositoryPrimaryFileConflictError)
})

it('downloads private complete primary-file bytes through the exact scoped route', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('first', { headers: {
    'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename="primary.txt"',
    'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
  } }))
  vi.stubGlobal('fetch', fetch)
  const controller = new AbortController()
  const result = await browserRepositoryClient.downloadPrimaryFile('doc/1', primary, 'org/1', controller.signal)
  expect(result.name).toBe(primary.filename)
  expect(result.content.size).toBe(5)
  expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/org%2F1/content-graph/documents/doc%2F1/attachments/' + primary.id + '/download', { credentials: 'same-origin', signal: controller.signal })
})

it.each([
  [403, 'first', 'application/octet-stream'],
  [206, 'first', 'application/octet-stream'],
  [200, 'shorter than expected', 'application/octet-stream'],
  [200, 'first', 'text/html'],
] as const)('refuses denied, partial or unexpected primary downloads', async (status, body, mediaType) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status, headers: {
    'Content-Type': mediaType, 'Content-Disposition': 'attachment; filename="primary.txt"',
    'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
  } })))
  await expect(browserRepositoryClient.downloadPrimaryFile('doc', primary)).rejects.toThrow('could not be downloaded')
})

it.each([
  { ...primary, scan_status: 'pending' },
  { ...primary, checksum: 'wrong' },
  { ...primary, version_number: 2 },
  { ...primary, replaces_id: primary.id },
])('refuses an unverified or inconsistent primary-file response', async result => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 201 })))
  await expect(browserRepositoryClient.appendPrimaryFile('doc', new File(['first'], 'primary.txt'), null)).rejects.toThrow('Invalid primary-file response')
})

it.each([
  { results: [primary], count: 2, page: 1, page_size: 25, has_more: false },
  { results: [{ ...primary, is_current: false }], count: 1, page: 1, page_size: 25, has_more: false },
  { results: [primary], count: 1, page: 2, page_size: 25, has_more: false },
])('refuses incomplete or misidentified primary history pages', async page => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(page))))
  await expect(browserRepositoryClient.primaryFiles('doc')).rejects.toThrow('Invalid primary-file history')
})

it('distinguishes recent-authentication denial from other permission failures', async () => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'recent_authentication_required' } }), { status: 403 })))
  await expect(browserRepositoryClient.publicationAction('evidence-1', 'authorize_delivery', 'Reviewed', null, 'org-1')).rejects.toBeInstanceOf(RepositoryRecentAuthenticationRequiredError)
})

it.each([undefined, 'org/1'])('retains only the exact reviewed revision in workspace %s', async organizationId => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'evidence-1' }), { status: 201 }))
  vi.stubGlobal('fetch', fetch)
  await browserRepositoryClient.createEvidence('doc/1', 'msp_internal', 'a'.repeat(40), organizationId)
  const [url, request] = fetch.mock.calls[0] as [string, RequestInit]
  expect(url).toContain(organizationId ? '/organizations/org%2F1/' : '/workspaces/msp/')
  expect(JSON.parse(request.body as string)).toEqual({ content_id: 'doc/1', audience: 'msp_internal', expected_commit: 'a'.repeat(40) })
  expect(new Headers(request.headers).get('X-CSRFToken')).toBe('repository-csrf')
})

it.each([
  ['accept_review', '/decision', { outcome: 'accepted_for_packaging', reason: 'Reviewed' }],
  ['reject_review', '/decision', { outcome: 'rejected', reason: 'Reviewed' }],
  ['create_package', '/package', {}],
  ['authorize_package', '/package/authorization', { outcome: 'authorized_for_publication', reason: 'Reviewed' }],
  ['reject_package', '/package/authorization', { outcome: 'rejected', reason: 'Reviewed' }],
  ['create_static', '/package/static-publication', {}],
  ['release_client', '/package/static-publication/control', { action: 'released', reason: 'Reviewed', supersedes_id: 'previous' }],
  ['withdraw_client', '/package/static-publication/control', { action: 'withdrawn', reason: 'Reviewed' }],
  ['authorize_delivery', '/package/static-publication/delivery-authorization', { reason: 'Reviewed' }],
  ['release_internal', '/internal-publication', { action: 'released', reason: 'Reviewed', supersedes_id: 'previous' }],
  ['withdraw_internal', '/internal-publication', { action: 'withdrawn', reason: 'Reviewed' }],
] as const)('sends %s through its guarded native endpoint', async (action, suffix, body) => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 201 }))
  vi.stubGlobal('fetch', fetch)
  await browserRepositoryClient.publicationAction('evidence/1', action, 'Reviewed', 'previous', 'org/1')
  const [url, request] = fetch.mock.calls[0] as [string, RequestInit]
  expect(url).toBe(`/api/v1/workspaces/organizations/org%2F1/repository-publication-evidence/evidence%2F1${suffix}`)
  expect(request.method).toBe('POST')
  expect(JSON.parse(request.body as string)).toEqual(body)
})

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

it.each([undefined, 'org/1'])('lists and archives only the selected repository document in workspace %s', async (organizationId) => {
  Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=repository-csrf' })
  const page = { results: [], page: 1, page_size: 25, count: 0, has_more: false }
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(page), { status: 200 }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetch)
  expect(await browserRepositoryClient.listAttachments('doc/1', organizationId)).toEqual(page)
  await browserRepositoryClient.archiveAttachment('doc/1', 'file/1', organizationId)
  const scope = organizationId ? '/api/v1/workspaces/organizations/org%2F1' : '/api/v1/workspaces/msp'
  expect(fetch.mock.calls[0][0]).toBe(`${scope}/content-graph/authoring/doc%2F1/attachments?page=1`)
  expect(fetch.mock.calls[1][0]).toBe(`${scope}/content-graph/authoring/doc%2F1/attachments/file%2F1`)
  expect(fetch.mock.calls[1][1]).toMatchObject({ method: 'DELETE', credentials: 'same-origin' })
  const archiveRequest = fetch.mock.calls[1][1] as RequestInit
  expect(new Headers(archiveRequest.headers).get('X-CSRFToken')).toBe('repository-csrf')
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

const keyState = {
  source_blob: 'a'.repeat(40), accepted_commit: 'b'.repeat(40), read_only: false,
  key_bindings: { site: primary.id }, targets: [{ id: primary.id, title: 'Synthetic site', kind: 'entity', entity_type: 'site', fields: ['name'] }],
  bound_targets: [], has_more: false, report: [{ expression: 'site.name', state: 'resolved', label: 'Site', reason: null }], report_has_more: false,
}

it.each([undefined, 'org/1'])('reads only the scoped key configuration and reauthorizes pending targets %s', async organizationId => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(keyState)))
  vi.stubGlobal('fetch', fetch)
  const controller = new AbortController()
  expect(await browserRepositoryClient.keys('doc/1', organizationId, 'site & name', [primary.id], controller.signal)).toEqual(keyState)
  const scope = organizationId ? '/api/v1/workspaces/organizations/org%2F1/content-graph' : '/api/v1/workspaces/msp/content-graph'
  expect(fetch).toHaveBeenCalledWith(scope + '/authoring/doc%2F1/keys?q=site+%26+name&target_id=' + primary.id, {
    credentials: 'same-origin', headers: { Accept: 'application/json' }, signal: controller.signal,
  })
})

it.each([
  { ...keyState, source_blob: 'bad' }, { ...keyState, read_only: 'false' },
  { ...keyState, key_bindings: { Bad: primary.id } }, { ...keyState, key_bindings: { site: 'not-a-uuid' } },
  { ...keyState, targets: [{ ...keyState.targets[0], kind: 'secret' }] },
  { ...keyState, report: [{ ...keyState.report[0], state: 'unknown' }] },
])('refuses malformed key configuration', async result => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(result))))
  await expect(browserRepositoryClient.keys('doc')).rejects.toThrow()
})

it.each([403, 404, 409])('refuses denied, hidden or stale key state %s', async status => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status })))
  await expect(browserRepositoryClient.keys('doc')).rejects.toThrow()
})
