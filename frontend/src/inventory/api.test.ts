import { beforeEach, describe, expect, it, vi } from 'vitest'
import { browserAssetCollectionClient, browserInventoryClient } from './api'

describe('inventory API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=inventory-csrf' })
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ results: [] }), { status: 200 }))))
  })

  it('uses exact client routes and CSRF for asset creation', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    await browserInventoryClient.listAssets(workspace, 2)
    await browserInventoryClient.listModelChoices(workspace, 'edge switch')
    await browserInventoryClient.createAsset(workspace, 'model/1', 'Core switch')
    await browserInventoryClient.listVendors(workspace, { q: 'north wind', ordering: '-asset_count', page: 2, page_size: 25 })
    await browserInventoryClient.retrieveVendor(workspace, 'vendor/1')
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/assets/model-choices?q=edge%20switch',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/vendors?ordering=-asset_count&page=2&page_size=25&q=north+wind',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/vendors/vendor%2F1', expect.any(Object))
    const post = vi.mocked(fetch).mock.calls.find(([, options]) => options?.method === 'POST')
    expect(post?.[0]).toBe('/api/v1/workspaces/organizations/client%2F1/assets')
    expect((post?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('inventory-csrf')
  })

  it('uses dedicated MSP-owned routes without an organization identifier', async () => {
    const workspace = { kind: 'msp', id: 'tenant/1' } as never
    await browserInventoryClient.listAssets(workspace, 1)
    await browserInventoryClient.listLicenses(workspace, 3)
    await browserInventoryClient.listVendors(workspace, { q: '', ordering: 'name', page: 1, page_size: 25 })

    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/workspaces/msp/assets?page=1&page_size=50', expect.any(Object))
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/workspaces/msp/licenses?page=3&page_size=50', expect.any(Object))
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/workspaces/msp/vendors?ordering=name&page=1&page_size=25', expect.any(Object))
  })

  it('sends CSV preview and apply as CSRF-protected multipart requests', async () => {
    const workspace = { kind: 'organization', id: 'client-1' } as never
    const file = new File(['schema_version\n'], 'assets.csv', { type: 'text/csv' })
    await browserInventoryClient.previewAssetCsv(workspace, file)
    await browserInventoryClient.applyAssetCsv(workspace, file, 'signed-preview')

    const calls = vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(calls.map(([url]) => url)).toEqual([
      '/api/v1/workspaces/organizations/client-1/assets/csv/preview',
      '/api/v1/workspaces/organizations/client-1/assets/csv/apply',
    ])
    const applyBody = calls[1][1]?.body as FormData
    expect(applyBody.get('file')).toBe(file)
    expect(applyBody.get('preview_token')).toBe('signed-preview')
    expect((calls[1][1]?.headers as Record<string, string>)['Content-Type']).toBeUndefined()
    expect((calls[1][1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('inventory-csrf')
  })
})


describe('asset summary browsing', () => {
  it('encodes collection conditions, retains false filters, and propagates cancellation', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [], count: 0 }), { status: 200 }))
    vi.stubGlobal('fetch', request)
    const controller = new AbortController()
    await browserAssetCollectionClient.list({ kind: 'organization', id: 'client/1' } as never, {
      search: 'serial & tag', page: 2, page_size: 25, assigned: false, ordering: '-name', kind: undefined,
    }, controller.signal)
    expect(request).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/assets/collection?search=serial+%26+tag&page=2&page_size=25&assigned=false&ordering=-name',
      expect.objectContaining({ credentials: 'same-origin', signal: controller.signal }),
    )
  })

  it('loads only the requested detail and surfaces failures without retrying', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Unavailable' }), { status: 404 }))
    vi.stubGlobal('fetch', request)
    await expect(browserAssetCollectionClient.detail({ kind: 'msp' } as never, 'asset/1')).rejects.toThrow('Unavailable')
    expect(request).toHaveBeenCalledTimes(1)
    expect(request).toHaveBeenCalledWith('/api/v1/workspaces/msp/assets/asset%2F1', expect.any(Object))
  })
})
