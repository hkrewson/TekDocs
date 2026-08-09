import { afterEach, describe, expect, it, vi } from 'vitest'
import { browserDocumentsClient } from './api'

describe('documentation placement API client', () => {
  afterEach(() => vi.restoreAllMocks())

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
})
