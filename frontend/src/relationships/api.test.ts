import { afterEach, describe, expect, it, vi } from 'vitest'
import { browserRelationshipsClient } from './api'
import type { EntityRelationship } from './api'

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
      related_entity: { id: '00000000-0000-4000-8000-000000000003', display_name: 'Vendor', entity_type: 'organization', workspace_label: 'MSP organization directory', eligible_link_types: ['supplied_by'] },
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
})
