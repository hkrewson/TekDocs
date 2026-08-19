import { afterEach, describe, expect, it, vi } from 'vitest'
import { browserRelationshipsClient } from './api'
import type { EntityRelationship } from './api'

/** The request target as a string, whatever form the caller passed it in. */
function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  return input instanceof URL ? input.href : input.url
}

describe('relationships API client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('searches inside the selected organization scope', async () => {
    const response = { results: [], page: 1, page_size: 15, count: 0, has_more: false }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(response), { status: 200 }))

    await expect(browserRelationshipsClient.search({ organizationId: 'client/id' }, 'Beacon & Co', 'organization')).resolves.toEqual(response)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2Fid/entities/search?q=Beacon+%26+Co&page=1&page_size=15&entity_type=organization',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
  })

  it('loads relationships from an encoded entity route', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ relationships: [] }), { status: 200 }))

    await expect(browserRelationshipsClient.list({}, 'entity/id')).resolves.toEqual([])

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/entities/entity%2Fid/links', expect.objectContaining({ credentials: 'same-origin' }))
  })

  it('creates a CSRF-protected typed relationship', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=relationship-csrf' })
    const relationship: EntityRelationship = {
      id: '00000000-0000-4000-8000-000000000001', link_type: 'supplied_by', label: 'Supplied by', direction: 'outgoing',
      source_id: '00000000-0000-4000-8000-000000000002', target_id: '00000000-0000-4000-8000-000000000003',
      related_entity: { id: '00000000-0000-4000-8000-000000000003', display_name: 'Vendor', entity_type: 'organization', visibility: 'msp_private', workspace_label: 'MSP organization directory', eligible_link_types: ['supplied_by'] },
      created_at: '2026-08-08T12:00:00Z',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(relationship), { status: 201 }))

    await browserRelationshipsClient.create({ organizationId: 'client-1' }, 'client-1', 'vendor-1', 'supplied_by')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client-1/entities/client-1/links',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ target_id: 'vendor-1', link_type: 'supplied_by' }),
      }),
    )
    const request = fetchMock.mock.calls.at(-1)?.[1]
    expect(request?.headers).toMatchObject({ 'X-CSRFToken': 'relationship-csrf' })
  })

  it('maps a server denial to a safe relationship error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 403 }))

    await expect(browserRelationshipsClient.list({}, 'entity-1')).rejects.toThrow('not authorized to view relationships')
  })
  it.each([
    [400, 'The selected relationship is not valid for these records.'],
    [403, 'Your account is not authorized to view relationships in this workspace.'],
    [404, 'The record or relationship is no longer available in this workspace.'],
    [500, 'Relationships could not be loaded.'],
  ])('describes a %i failure on a read without disclosing why the record is unavailable', async (status, message) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status }))

    await expect(browserRelationshipsClient.list({}, 'entity-1')).rejects.toThrow(message)
  })

  it.each([
    [400, 'The selected relationship is not valid for these records.'],
    [403, 'Your account is not authorized to manage relationships in this workspace.'],
    [404, 'The record or relationship is no longer available in this workspace.'],
    [500, 'Relationships could not be changed.'],
  ])('describes a %i failure on a change as a change rather than a read', async (status, message) => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=relationship-csrf' })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status }))

    await expect(browserRelationshipsClient.archive({}, 'entity-1', 'link-1')).rejects.toThrow(message)
  })

  it('reads the MSP routes when no organization is selected', async () => {
    // A fresh Response per call: a body can only be read once, so a shared instance
    // would fail the second call for a reason unrelated to the test.
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 })))
    const client = browserRelationshipsClient
    if (!client.graphViews) throw new Error('The browser client does not expose graph views.')

    await client.linkTypes()
    await client.search({}, 'Beacon')
    await client.graphViews({})

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/entity-link-types',
      // No entity_type parameter: an unfiltered search must not send an empty filter.
      '/api/v1/entities/search?q=Beacon&page=1&page_size=15',
      '/api/v1/relationship-graph/views',
    ])
  })

  it('bounds a graph request even when the caller supplies no options', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ nodes: [], edges: [] }), { status: 200 }))
    const client = browserRelationshipsClient
    if (!client.graph) throw new Error('The browser client does not expose a graph.')

    await client.graph({}, 'network')

    // Depth and edge limit are always sent, so an omitted option cannot become an
    // unbounded traversal request.
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/relationship-graph?family=network&depth=2&edge_limit=100')
  })

  it('sends an explicit root, depth, and edge limit when the caller supplies them', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ nodes: [], edges: [] }), { status: 200 }))
    const client = browserRelationshipsClient
    if (!client.graph) throw new Error('The browser client does not expose a graph.')

    await client.graph({ organizationId: 'client/id' }, 'asset', { rootId: 'entity/id', depth: 3, edgeLimit: 25 })

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/workspaces/organizations/client%2Fid/relationship-graph?family=asset&depth=3&edge_limit=25&root=entity%2Fid',
    )
  })

  it('encodes a saved view identifier into its own routes', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=relationship-csrf' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 })))
    const client = browserRelationshipsClient
    if (!client.saveGraphView || !client.updateGraphView || !client.snapshotGraphView) {
      throw new Error('The browser client does not expose saved views.')
    }
    const values = { name: 'Edge', family: 'network' as const, root_entity_id: null, depth: 2, edge_limit: 50, positions: {} }

    await client.saveGraphView({}, values)
    await client.updateGraphView({}, 'view/id', { ...values, name: 'Edge renamed' })
    await client.snapshotGraphView({}, 'view/id')

    expect(fetchMock.mock.calls.map((call) => [call[0], call[1]?.method])).toEqual([
      ['/api/v1/relationship-graph/views', 'POST'],
      ['/api/v1/relationship-graph/views/view%2Fid', 'PATCH'],
      ['/api/v1/relationship-graph/views/view%2Fid/snapshots', 'POST'],
    ])
    // A snapshot takes no body; sending "undefined" as JSON would be a malformed request.
    expect(fetchMock.mock.calls.at(-1)?.[1]?.body).toBeUndefined()
  })

  it('builds a snapshot export URL without issuing a request', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    const client = browserRelationshipsClient
    if (!client.graphSnapshotExportUrl) throw new Error('The browser client does not expose snapshot exports.')

    expect(client.graphSnapshotExportUrl({ organizationId: 'client/id' }, 'snapshot/id', 'svg')).toBe(
      '/api/v1/workspaces/organizations/client%2Fid/relationship-graph/snapshots/snapshot%2Fid/export/svg',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('reports an unreadable body rather than surfacing a parser failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('not json', { status: 200 }))

    await expect(browserRelationshipsClient.linkTypes()).rejects.toThrow('The server returned an unreadable response.')
  })

  it('recovers the security token from a session request before giving up', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: '' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      if (requestUrl(input).includes('/_allauth/')) {
        Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=recovered-csrf' })
        return Promise.resolve(new Response('{}', { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))
    })

    await browserRelationshipsClient.archive({}, 'entity-1', 'link-1')

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/_allauth/browser/v1/auth/session')
    expect(fetchMock.mock.calls.at(-1)?.[1]?.headers).toMatchObject({ 'X-CSRFToken': 'recovered-csrf' })
  })

  it('refuses to mutate at all when no security token can be obtained', async () => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: '' })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))

    await expect(browserRelationshipsClient.archive({}, 'entity-1', 'link-1')).rejects.toThrow(
      'The browser security token is unavailable. Refresh and try again.',
    )
    // Only the session recovery attempt: the mutation itself is never sent.
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(['/_allauth/browser/v1/auth/session'])
  })
})
