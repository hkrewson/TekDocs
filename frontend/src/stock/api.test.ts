import { afterEach, describe, expect, it, vi } from 'vitest'
import { browserStockClient } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('stock API', () => {
  it('encodes bounded collection state and retrieves a direct record', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [], page: 2, page_size: 25, count: 0, has_more: false, can_manage: true, vendors: [], clients: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'stock/1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await browserStockClient.list({ q: 'cable & parts', ordering: '-quantity_on_hand', page: 2, page_size: 25 })
    await browserStockClient.retrieve('stock/1')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/workspaces/msp/stock?ordering=-quantity_on_hand&page=2&page_size=25&q=cable+%26+parts')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/workspaces/msp/stock/stock%2F1')
  })
})
