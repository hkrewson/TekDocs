import { afterEach, describe, expect, it, vi } from 'vitest'
import { browserDocumentsClient } from './api'

describe('documentation placement API client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('requests bounded revision-history pages', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ results: [], count: 0, page: 3, page_size: 50, has_more: false }), { status: 200 }))
    await browserDocumentsClient.listRevisions({ organizationId: 'org' }, 'doc', 3)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/org/documents/doc/revisions?page=3&page_size=50')
  })

  it('adds a pinned placement inside the selected organization route with CSRF', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=document-csrf' })
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 })))

    await browserDocumentsClient.addPlacement(
      { organizationId: 'client/id' },
      'document/id',
      { source_document_id: 'source/id', resolution_mode: 'pinned', pinned_revision_id: 'revision/id' },
    )

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/client%2Fid/documents/document%2Fid/placements')
    const request = fetchMock.mock.calls[0]?.[1]
    expect(request?.method).toBe('POST')
    expect(request?.body).toBe(
      JSON.stringify({ source_document_id: 'source/id', resolution_mode: 'pinned', pinned_revision_id: 'revision/id' }),
    )
    expect(new Headers(request?.headers).get('X-CSRFToken')).toBe('document-csrf')
  })

  it('switches a placement to live and removes it through its scoped identifier', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=document-csrf' })
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 })))

    await browserDocumentsClient.updatePlacement({}, 'document/id', 'placement/id', { resolution_mode: 'live', pinned_revision_id: null })
    await browserDocumentsClient.removePlacement({}, 'document/id', 'placement/id')

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/documents/document%2Fid/placements/placement%2Fid')
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'PATCH' })
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: 'DELETE' })
  })

  it('reviews, updates, and detaches a shared block through destination-scoped routes', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=document-csrf' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 })))

    await browserDocumentsClient.getReuseImpact({ organizationId: 'org' }, 'doc', 'placement')
    await browserDocumentsClient.updateSharedBlock({ organizationId: 'org' }, 'doc', 'placement', 'updated', 'revision')
    await browserDocumentsClient.detachPlacement({ organizationId: 'org' }, 'doc', 'placement')
    await browserDocumentsClient.searchMentionEntities({ organizationId: 'org' }, 'router')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/workspaces/organizations/org/documents/doc/placements/placement/reuse',
      '/api/v1/workspaces/organizations/org/documents/doc/placements/placement/reuse',
      '/api/v1/workspaces/organizations/org/documents/doc/placements/placement/detach',
      '/api/v1/workspaces/organizations/org/documents/mention-entities?q=router&page_size=20',
    ])
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({ markdown: 'updated', base_revision_id: 'revision' }))
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe('POST')
  })

  it('filters, imports, attaches, and builds private transfer routes', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=document-csrf' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ results: [], count: 0 }), { status: 200 })))
    const scope = { organizationId: 'org' }

    await browserDocumentsClient.list(scope, undefined, { q: 'router', category: 'guide', template: 'templates' })
    await browserDocumentsClient.importMarkdown(scope, new File(['# Guide'], 'guide.md'), 'Guide', 'guide', true)
    await browserDocumentsClient.uploadAttachment(scope, 'doc', new File(['notes'], 'notes.txt'))
    await browserDocumentsClient.archiveAttachment(scope, 'doc', 'attachment')

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/org/documents?q=router&category=guide&template=templates')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/workspaces/organizations/org/documents/import')
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBeInstanceOf(FormData)
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/workspaces/organizations/org/documents/doc/attachments')
    expect(fetchMock.mock.calls[3]?.[1]?.method).toBe('DELETE')
    expect(browserDocumentsClient.exportUrl(scope, 'doc').endsWith('/documents/doc/export')).toBe(true)
    expect(browserDocumentsClient.attachmentDownloadUrl(scope, 'doc', 'attachment').endsWith('/attachments/attachment/download')).toBe(true)
  })

  it('publishes and retrieves STATIC artifacts through workspace-scoped routes', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=document-csrf' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ verification: { valid: true } }), { status: 200 })))
    const scope = { organizationId: 'org' }

    await browserDocumentsClient.publish(scope, 'doc', { reason: 'Approved', audience: 'client_visible', retention: 'permanent' })
    await browserDocumentsClient.getPublication(scope, 'doc', 'publication')

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/workspaces/organizations/org/documents/doc/publications')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ reason: 'Approved', audience: 'client_visible', retention: 'permanent' }))
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/workspaces/organizations/org/documents/doc/publications/publication')
    expect(browserDocumentsClient.publicationMarkdownUrl(scope, 'doc', 'publication')).toContain('/publications/publication/markdown')
    expect(browserDocumentsClient.publicationManifestUrl(scope, 'doc', 'publication')).toContain('/publications/publication/manifest')
    expect(browserDocumentsClient.publicationArtifactUrl(scope, 'doc', 'publication', 'artifact')).toContain('/publications/publication/artifacts/artifact/download')
  })
})
