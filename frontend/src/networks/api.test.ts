import { beforeEach, describe, expect, it, vi } from 'vitest'
import { browserNetworksClient } from './api'

describe('network inventory API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=network-csrf' })
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ results: [] }), { status: 200 }))))
  })

  it('uses exact client workspace routes and CSRF-protected writes', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    await browserNetworksClient.listRacks(workspace)
    await browserNetworksClient.listDevices(workspace)
    await browserNetworksClient.listSubnets(workspace)
    await browserNetworksClient.listInterfaces(workspace)
    await browserNetworksClient.listIPAddresses(workspace)
    await browserNetworksClient.listMACAddresses(workspace)
    await browserNetworksClient.listWireless(workspace)
    await browserNetworksClient.listDNSZones(workspace)
    await browserNetworksClient.listDNSRecords(workspace)
    await browserNetworksClient.createRack(workspace, { name: 'Core rack', site_id: 'site-1', location_id: null, unit_count: 42, status: 'active' })

    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/racks?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/subnets?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/interfaces?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/ip-addresses?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/mac-addresses?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/wireless?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/dns-zones?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/dns-records?page=1&page_size=100', expect.any(Object))
    const post = vi.mocked(fetch).mock.calls.find(([, options]) => options?.method === 'POST')
    expect(post?.[0]).toBe('/api/v1/workspaces/organizations/client%2F1/networks/racks')
    expect((post?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('network-csrf')
  })

  it('keeps MSP network inventory on non-aggregating MSP routes', async () => {
    const workspace = { kind: 'msp', id: 'msp-1' } as never
    await browserNetworksClient.listRacks(workspace)
    await browserNetworksClient.choices(workspace)
    await browserNetworksClient.listVRFs(workspace)
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/racks?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/choices', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/vrfs?page=1&page_size=100', expect.any(Object))
  })
})
