import { beforeEach, describe, expect, it, vi } from 'vitest'
import { browserInventoryClient } from './api'

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
    await browserInventoryClient.listVendors(workspace)
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/v1/workspaces/organizations/client%2F1/assets/model-choices?q=edge%20switch',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
    const post = vi.mocked(fetch).mock.calls.find(([, options]) => options?.method === 'POST')
    expect(post?.[0]).toBe('/api/v1/workspaces/organizations/client%2F1/assets')
    expect((post?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('inventory-csrf')
  })

  it('uses dedicated MSP-owned routes without an organization identifier', async () => {
    const workspace = { kind: 'msp', id: 'tenant/1' } as never
    await browserInventoryClient.listAssets(workspace, 1)
    await browserInventoryClient.listLicenses(workspace, 3)
    await browserInventoryClient.listVendors(workspace)

    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/workspaces/msp/assets?page=1&page_size=50', expect.any(Object))
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/workspaces/msp/licenses?page=3&page_size=50', expect.any(Object))
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/v1/workspaces/msp/vendors', expect.any(Object))
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
