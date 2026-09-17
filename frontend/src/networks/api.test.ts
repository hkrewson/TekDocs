import { beforeEach, describe, expect, it, vi } from 'vitest'
import { browserNetworksClient } from './api'

describe('network inventory API client', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'cookie', { configurable: true, value: 'csrftoken=network-csrf' })
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ results: [] }), { status: 200 }))))
  })

  it('requests bounded inventory pages and independent details without changing legacy helpers', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    const signal = new AbortController().signal
    await browserNetworksClient.rackCollection(workspace, { q: 'rack / 31', page: 2, page_size: 25, ordering: '-name', status: 'active', site_id: 'site-1' }, signal)
    await browserNetworksClient.deviceCollection(workspace, { q: '', page: 1, page_size: 50, ordering: 'rack_unit', role: 'switch', rack_id: 'rack-1' }, signal)
    await browserNetworksClient.rackDetail(workspace, 'rack/1', signal)
    await browserNetworksClient.deviceDetail(workspace, 'device/1', signal)
    await browserNetworksClient.subnetCollection(workspace, { q: 'office / 31', page: 2, page_size: 25, ordering: 'name' }, signal)
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/racks?q=rack+%2F+31&page=2&page_size=25&ordering=-name&status=active&site_id=site-1', { credentials: 'same-origin', signal })
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/devices?q=&page=1&page_size=50&ordering=rack_unit&role=switch&rack_id=rack-1', { credentials: 'same-origin', signal })
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/racks/rack%2F1', { credentials: 'same-origin', signal })
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/devices/device%2F1', { credentials: 'same-origin', signal })
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/subnets?q=office+%2F+31&page=2&page_size=25&ordering=name&summary=true', { credentials: 'same-origin', signal })
  })

  it('requests independent circuit choice pages and retains the selected identifier', async () => {
    const signal = new AbortController().signal
    await browserNetworksClient.circuitChoicePage({ kind: 'organization', id: 'client/1' } as never, {
      choice: 'contracts', q: 'Fiber / service', page: 2, page_size: 25, provider_id: 'provider/1', selected_id: 'contract/1',
    }, signal)
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/circuits/choices?choice=contracts&q=Fiber+%2F+service&page=2&page_size=25&provider_id=provider%2F1&selected_id=contract%2F1', { credentials: 'same-origin', signal })
    await browserNetworksClient.circuitChoices({ kind: 'msp' } as never, signal)
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/circuits/choices', { credentials: 'same-origin', signal })
  })

  it('uses exact client workspace routes and CSRF-protected writes', async () => {
    const workspace = { kind: 'organization', id: 'client/1' } as never
    await browserNetworksClient.listNetworks(workspace)
    await browserNetworksClient.createNetwork(workspace, {} as never)
    await browserNetworksClient.updateNetwork(workspace, 'network/1', {} as never)
    await browserNetworksClient.listRacks(workspace)
    await browserNetworksClient.listDevices(workspace)
    await browserNetworksClient.listSubnets(workspace)
    await browserNetworksClient.listInterfaces(workspace)
    await browserNetworksClient.listIPAddresses(workspace)
    await browserNetworksClient.listMACAddresses(workspace)
    await browserNetworksClient.listWireless(workspace)
    await browserNetworksClient.listDNSZones(workspace)
    await browserNetworksClient.listDNSRecords(workspace)
    await browserNetworksClient.listCircuits(workspace)
    await browserNetworksClient.circuitChoices(workspace)
    await browserNetworksClient.listNetBoxReferences(workspace)
    await browserNetworksClient.searchNetwork(workspace, 'core / rack', 2)
    await browserNetworksClient.netBoxChoices(workspace)
    await browserNetworksClient.previewNetBoxReconciliation(workspace, [])
    await browserNetworksClient.setNetBoxReference(workspace, { entity_id: 'rack-1', object_type: 'dcim.rack', object_id: 41 })
    await browserNetworksClient.removeNetBoxReference(workspace, 'reference/1')
    await browserNetworksClient.createCircuit(workspace, {} as never)
    await browserNetworksClient.updateCircuit(workspace, 'circuit/1', {})
    await browserNetworksClient.createCircuitHandoff(workspace, 'circuit/1', {} as never)
    await browserNetworksClient.updateCircuitHandoff(workspace, 'circuit/1', 'handoff/1', {})
    await browserNetworksClient.createRack(workspace, { name: 'Core rack', site_id: 'site-1', location_id: null, unit_count: 42, status: 'active' })
    await browserNetworksClient.moveInterface(workspace, 'interface/1', 'device/2', 'device/1')
    await browserNetworksClient.moveDNSRecord(workspace, 'record/1', 'zone/2', 'zone/1', 'host.destination.invalid')

    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks', expect.objectContaining({ method: 'POST' }))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/network%2F1', expect.objectContaining({ method: 'PATCH' }))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/racks?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/subnets?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/interfaces?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/ip-addresses?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/mac-addresses?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/wireless?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/dns-zones?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/dns-records?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/circuits?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/circuits/choices', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/netbox/references', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/search?q=core+%2F+rack&page=2&page_size=50', expect.any(Object))
    expect(browserNetworksClient.networkExportUrl(workspace)).toBe('/api/v1/workspaces/organizations/client%2F1/networks/export')
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/netbox/references/reference%2F1', expect.objectContaining({ method: 'DELETE' }))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/netbox/reconcile-preview', expect.objectContaining({ method: 'POST' }))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/circuits/circuit%2F1', expect.objectContaining({ method: 'PATCH' }))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/circuits/circuit%2F1/handoffs/handoff%2F1', expect.objectContaining({ method: 'PATCH' }))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/interfaces/interface%2F1', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ device_id: 'device/2', expected_device_id: 'device/1' }) }))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/organizations/client%2F1/networks/dns-records/record%2F1', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ zone_id: 'zone/2', expected_zone_id: 'zone/1', owner_name: 'host.destination.invalid' }) }))
    const post = vi.mocked(fetch).mock.calls.find(([url, options]) => options?.method === 'POST' && typeof url === 'string' && url.endsWith('/racks'))
    expect(post?.[0]).toBe('/api/v1/workspaces/organizations/client%2F1/networks/racks')
    expect((post?.[1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('network-csrf')
  })

  it('keeps MSP network inventory on non-aggregating MSP routes', async () => {
    const workspace = { kind: 'msp', id: 'msp-1' } as never
    await browserNetworksClient.listNetworks(workspace)
    await browserNetworksClient.listRacks(workspace)
    await browserNetworksClient.choices(workspace)
    await browserNetworksClient.listVRFs(workspace)
    await browserNetworksClient.listNetBoxReferences(workspace)
    await browserNetworksClient.searchNetwork(workspace, '')
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/racks?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/choices', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/vrfs?page=1&page_size=100', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/netbox/references', expect.any(Object))
    expect(fetch).toHaveBeenCalledWith('/api/v1/workspaces/msp/networks/search?q=&page=1&page_size=50', expect.any(Object))
    expect(browserNetworksClient.networkExportUrl(workspace)).toBe('/api/v1/workspaces/msp/networks/export')
  })
})
