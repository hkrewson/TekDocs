import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { Networks } from './Networks'
import type { NetworksClient } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'], capabilities: [], organization: null,
}
const rack = { id: 'rack-1', name: 'Core rack', site_id: 'site-1', site_name: 'Headquarters', location_id: null, location_name: null, unit_count: 42, status: 'active' as const, device_count: 1 }
const device = { id: 'device-1', name: 'Core switch', role: 'switch' as const, status: 'active' as const, hardware_asset_id: 'asset-1', hardware_asset_name: 'EdgeSwitch 24', site_id: 'site-1', site_name: 'Headquarters', location_id: null, location_name: null, rack_id: 'rack-1', rack_name: 'Core rack', rack_unit: 20, rack_units: 2 }

function networkClient(overrides: Partial<NetworksClient> = {}): NetworksClient {
  return {
    listRacks: vi.fn().mockResolvedValue({ results: [rack], page: 1, page_size: 100, count: 1, has_more: false, can_manage: true }),
    listDevices: vi.fn().mockResolvedValue({ results: [device], page: 1, page_size: 100, count: 1, has_more: false, can_manage: true, can_view_relationships: true, can_create_relationships: true, can_archive_relationships: true }),
    choices: vi.fn().mockResolvedValue({ sites: [{ id: 'site-1', name: 'Headquarters' }], locations: [], racks: [{ id: 'rack-1', name: 'Core rack', site_id: 'site-1' }], hardware_assets: [{ id: 'asset-1', name: 'EdgeSwitch 24' }] }),
    createRack: vi.fn().mockResolvedValue(rack), updateRack: vi.fn().mockResolvedValue(rack),
    createDevice: vi.fn().mockResolvedValue(device), updateDevice: vi.fn().mockResolvedValue(device),
    listVRFs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createVRF: vi.fn(), updateVRF: vi.fn(),
    listVLANs: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createVLAN: vi.fn(), updateVLAN: vi.fn(),
    listSubnets: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createSubnet: vi.fn(), updateSubnet: vi.fn(),
    listInterfaces: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createInterface: vi.fn(), updateInterface: vi.fn(),
    listIPAddresses: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createIPAddress: vi.fn(), updateIPAddress: vi.fn(),
    listMACAddresses: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createMACAddress: vi.fn(), updateMACAddress: vi.fn(),
    listWireless: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createWireless: vi.fn(), updateWireless: vi.fn(),
    listDNSZones: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createDNSZone: vi.fn(), updateDNSZone: vi.fn(),
    listDNSRecords: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }),
    createDNSRecord: vi.fn(), updateDNSRecord: vi.fn(),
    listCircuits: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true, can_view_contracts: true }),
    circuitChoices: vi.fn().mockResolvedValue({ providers: [{ id: 'provider-1', name: 'Example Carrier' }], contracts: [{ id: 'contract-1', name: 'Internet agreement', provider_id: 'provider-1' }], sites: [{ id: 'site-1', name: 'Headquarters' }], locations: [], devices: [{ id: 'device-1', name: 'Core switch' }], interfaces: [{ id: 'interface-1', name: 'WAN1', device_id: 'device-1' }], can_view_contracts: true }),
    createCircuit: vi.fn(), updateCircuit: vi.fn(), createCircuitHandoff: vi.fn(), updateCircuitHandoff: vi.fn(),
    listNetBoxReferences: vi.fn().mockResolvedValue([]),
    netBoxChoices: vi.fn().mockResolvedValue({ results: [], can_manage: true }),
    setNetBoxReference: vi.fn(), removeNetBoxReference: vi.fn(), previewNetBoxReconciliation: vi.fn(),
    ...overrides,
  }
}

const relationshipsClient = {
  list: vi.fn().mockResolvedValue([]), search: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 15, count: 0, has_more: false }),
  create: vi.fn(), archive: vi.fn(), linkTypes: vi.fn().mockResolvedValue([]),
} as RelationshipsClient

describe('Networks', () => {
  it('links a lightweight record to a stable NetBox identity', async () => {
    const reference = { id: 'reference-1', entity_id: 'rack-1', entity_name: 'Core rack', entity_type: 'network_rack', object_type: 'dcim.rack' as const, object_id: 41, observed_fingerprint: '', last_observed_at: null }
    const listNetBoxReferences = vi.fn().mockResolvedValueOnce([]).mockResolvedValueOnce([reference])
    const netBoxChoices = vi.fn().mockResolvedValue({ results: [{ id: 'rack-1', name: 'Core rack', entity_type: 'network_rack', object_type: 'dcim.rack', linked: false }], can_manage: true })
    const setNetBoxReference = vi.fn().mockResolvedValue(reference)
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ listNetBoxReferences, netBoxChoices, setNetBoxReference })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })
    await user.click(screen.getByRole('button', { name: 'NetBox' }))
    expect(await screen.findByText('No NetBox identities match this workspace and search.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Link record' }))
    await user.selectOptions(screen.getByLabelText('TekDocs record'), 'rack-1')
    await user.type(screen.getByLabelText('NetBox numeric ID'), '41')
    await user.click(screen.getByRole('button', { name: 'Link identity' }))
    await waitFor(() => expect(setNetBoxReference).toHaveBeenCalledWith(workspace, { entity_id: 'rack-1', object_type: 'dcim.rack', object_id: 41 }))
    expect(await screen.findByRole('cell', { name: '41' })).toBeInTheDocument()
  })

  it('creates a canonical subnet from the workspace addressing surface', async () => {
    const createSubnet = vi.fn().mockResolvedValue({ id: 'subnet-1', name: 'Guest', cidr: '192.0.2.0/24', address_family: 4, vrf_id: null, vrf_name: null, vlan_id: null, vlan_name: null, vlan_number: null, description: '' })
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createSubnet })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })
    await user.click(screen.getByRole('button', { name: 'Subnets' }))
    await screen.findByText('No subnets match this workspace and search.')
    await user.click(screen.getByRole('button', { name: 'Add subnet' }))
    await user.type(screen.getByLabelText('Name'), 'Guest')
    await user.type(screen.getByLabelText(/^CIDR/), '192.0.2.0/24')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(createSubnet).toHaveBeenCalledWith(workspace, expect.objectContaining({ name: 'Guest', cidr: '192.0.2.0/24', vrf_id: null })))
    expect(await screen.findByText('IPv4')).toBeInTheDocument()
  })

  it('shows workspace-scoped device placement and logical relationship surface', async () => {
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} />)
    expect(await screen.findByRole('button', { name: 'Core switch' })).toBeInTheDocument()
    expect(screen.getByText('Core rack · U20–21')).toBeInTheDocument()
    expect(screen.getByText('EdgeSwitch 24')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Core switch' }))
    expect(await screen.findByRole('heading', { name: /Core switch/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Logical relationships' })).toBeInTheDocument()
  })

  it('creates an interface and exposes endpoint assignment tabs', async () => {
    const created = { id: 'interface-1', name: 'ethernet1', device_id: 'device-1', device_name: 'Core switch', kind: 'physical' as const, status: 'active' as const, description: '' }
    const createInterface = vi.fn().mockResolvedValue(created)
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createInterface })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })
    await user.click(screen.getByRole('button', { name: 'Interfaces' }))
    expect(await screen.findByText('No interface records match this workspace and search.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add interface' }))
    await user.type(screen.getByLabelText('Name'), 'ethernet1')
    await user.selectOptions(screen.getByLabelText('Device'), 'device-1')
    await user.click(screen.getByRole('button', { name: 'Save interface' }))
    await waitFor(() => expect(createInterface).toHaveBeenCalledWith(workspace, expect.objectContaining({ name: 'ethernet1', device_id: 'device-1' })))
    expect(await screen.findByText('ethernet1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'IP addresses' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'MAC addresses' })).toBeInTheDocument()
  })

  it('creates assigned IP and MAC records from canonical values', async () => {
    const networkInterface = { id: 'interface-1', name: 'ethernet1', device_id: 'device-1', device_name: 'Core switch', kind: 'physical' as const, status: 'active' as const, description: '' }
    const subnet = { id: 'subnet-1', name: 'LAN', cidr: '192.0.2.0/24', address_family: 4 as const, vrf_id: null, vrf_name: null, vlan_id: null, vlan_name: null, vlan_number: null, description: '' }
    const createIPAddress = vi.fn().mockResolvedValue({ id: 'ip-1', address: '192.0.2.10', address_family: 4, subnet_id: subnet.id, subnet_cidr: subnet.cidr, vrf_id: null, vrf_name: null, interface_id: networkInterface.id, interface_name: networkInterface.name, device_name: device.name, status: 'active', dns_name: '', description: '' })
    const createMACAddress = vi.fn().mockResolvedValue({ id: 'mac-1', address: '02:00:00:00:00:01', interface_id: networkInterface.id, interface_name: networkInterface.name, device_name: device.name, description: '' })
    const client = networkClient({
      listInterfaces: vi.fn().mockResolvedValue({ results: [networkInterface], page: 1, page_size: 100, count: 1, has_more: false, can_manage: true }),
      listSubnets: vi.fn().mockResolvedValue({ results: [subnet], page: 1, page_size: 100, count: 1, has_more: false, can_manage: true }),
      createIPAddress,
      createMACAddress,
    })
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={client} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })

    await user.click(screen.getByRole('button', { name: 'IP addresses' }))
    await screen.findByText('No IP address records match this workspace and search.')
    await user.click(screen.getByRole('button', { name: 'Add IP address' }))
    await user.type(screen.getByLabelText('IP address'), '192.0.2.10')
    await user.selectOptions(screen.getByLabelText('Subnet'), 'subnet-1')
    await user.selectOptions(screen.getByLabelText('Interface'), 'interface-1')
    await user.click(screen.getByRole('button', { name: 'Save IP address' }))
    await waitFor(() => expect(createIPAddress).toHaveBeenCalledWith(workspace, expect.objectContaining({ address: '192.0.2.10', subnet_id: 'subnet-1', interface_id: 'interface-1' })))

    await user.click(screen.getByRole('button', { name: 'MAC addresses' }))
    await screen.findByText('No MAC address records match this workspace and search.')
    await user.click(screen.getByRole('button', { name: 'Add MAC address' }))
    await user.type(screen.getByLabelText('MAC address'), '02:00:00:00:00:01')
    await user.selectOptions(screen.getByLabelText('Interface'), 'interface-1')
    await user.click(screen.getByRole('button', { name: 'Save MAC address' }))
    await waitFor(() => expect(createMACAddress).toHaveBeenCalledWith(workspace, expect.objectContaining({ address: '02:00:00:00:00:01', interface_id: 'interface-1' })))
  })

  it('creates wireless inventory without accepting a credential value', async () => {
    const created = { id: 'wifi-1', ssid: 'Acme Staff', purpose: 'corporate' as const, security: 'wpa3_enterprise' as const, status: 'active' as const, hidden: false, client_isolation: true, site_id: null, site_name: null, vlan_id: null, vlan_name: null, vlan_number: null, subnet_id: null, subnet_cidr: null, description: '' }
    const createWireless = vi.fn().mockResolvedValue(created)
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createWireless })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })
    await user.click(screen.getByRole('button', { name: 'Wireless' }))
    await screen.findByText('No wireless networks match this workspace and search.')
    await user.click(screen.getByRole('button', { name: 'Add wireless network' }))
    expect(screen.getByText(/never a Wi-Fi password/i)).toBeInTheDocument()
    await user.type(screen.getByLabelText('SSID'), 'Acme Staff')
    await user.click(screen.getByLabelText('Client isolation'))
    await user.click(screen.getByRole('button', { name: 'Save wireless network' }))
    await waitFor(() => expect(createWireless).toHaveBeenCalledWith(workspace, expect.objectContaining({ ssid: 'Acme Staff', client_isolation: true })))
    expect(createWireless.mock.calls[0]?.[1]).not.toHaveProperty('password')
  })

  it('creates a permission-scoped DNS zone and record', async () => {
    const zone = { id: 'zone-1', name: 'example.invalid', description: '', record_count: 0 }
    const createDNSZone = vi.fn().mockResolvedValue(zone)
    const createDNSRecord = vi.fn().mockResolvedValue({ id: 'record-1', zone_id: zone.id, zone_name: zone.name, owner_name: 'app.example.invalid', record_type: 'A', value: '192.0.2.10', ttl: 300, priority: null, weight: null, port: null, ip_address_id: null, description: '' })
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createDNSZone, createDNSRecord })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })
    await user.click(screen.getByRole('button', { name: 'DNS' }))
    await screen.findByText('No DNS zones match this workspace and search.')
    await user.click(screen.getByRole('button', { name: 'Add zone' }))
    await user.type(screen.getByLabelText('Canonical zone name'), 'example.invalid')
    await user.click(screen.getByRole('button', { name: 'Save zone' }))
    await waitFor(() => expect(createDNSZone).toHaveBeenCalled())
    await user.click(screen.getByRole('button', { name: 'Add record' }))
    await user.type(screen.getByLabelText('Owner name'), 'app.example.invalid')
    await user.type(screen.getByLabelText('Value'), '192.0.2.10')
    await user.clear(screen.getByLabelText('TTL')); await user.type(screen.getByLabelText('TTL'), '300')
    await user.click(screen.getByRole('button', { name: 'Save DNS record' }))
    await waitFor(() => expect(createDNSRecord).toHaveBeenCalledWith(workspace, expect.objectContaining({ zone_id: 'zone-1', owner_name: 'app.example.invalid', record_type: 'A', value: '192.0.2.10' })))
  })

  it('creates a provider circuit and records an exact device handoff', async () => {
    const circuit = { id: 'circuit-1', name: 'Headquarters DIA', provider_id: 'provider-1', provider_name: 'Example Carrier', contract: { id: 'contract-1', name: 'Internet agreement', status: 'active', renews_on: '2027-09-01', ends_on: '2027-09-30', auto_renew: true, renewal_notice_days: 30 }, service_identifier: 'CKT-1000', kind: 'internet' as const, status: 'active' as const, bandwidth_down_mbps: '1000.000', bandwidth_up_mbps: '1000.000', installed_on: null, service_starts_on: null, review_on: '2027-07-01', planned_disconnect_on: null, description: '', handoffs: [], lifecycle_events: [{ kind: 'review' as const, date: '2027-07-01', label: 'Review circuit', state: 'upcoming' as const }] }
    const handoff = { id: 'handoff-1', name: 'Carrier demarc', side: 'a' as const, media: 'fiber' as const, connector: 'LC', provider_reference: '', site_id: 'site-1', site_name: 'Headquarters', location_id: null, location_name: null, device_id: 'device-1', device_name: 'Core switch', interface_id: 'interface-1', interface_name: 'WAN1', description: '' }
    const createCircuit = vi.fn().mockResolvedValue(circuit)
    const createCircuitHandoff = vi.fn().mockResolvedValue(handoff)
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createCircuit, createCircuitHandoff })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })
    await user.click(screen.getByRole('button', { name: 'Circuits' }))
    await screen.findByText('No circuits match this workspace and search.')
    await user.click(screen.getByRole('button', { name: 'Add circuit' }))
    await user.type(screen.getByLabelText('Name'), 'Headquarters DIA')
    await user.selectOptions(screen.getByLabelText('Provider'), 'provider-1')
    await user.selectOptions(screen.getByLabelText('Contract'), 'contract-1')
    await user.type(screen.getByLabelText('Service identifier'), 'CKT-1000')
    await user.click(screen.getByRole('button', { name: 'Save circuit' }))
    await waitFor(() => expect(createCircuit).toHaveBeenCalledWith(workspace, expect.objectContaining({ provider_id: 'provider-1', contract_id: 'contract-1', service_identifier: 'CKT-1000' })))
    await user.click(screen.getByRole('button', { name: 'Add handoff' }))
    await user.type(screen.getByLabelText('Name'), 'Carrier demarc')
    await user.type(screen.getByLabelText('Connector'), 'LC')
    await user.selectOptions(screen.getByLabelText('Site'), 'site-1')
    await user.selectOptions(screen.getByLabelText('Device'), 'device-1')
    await user.selectOptions(screen.getByLabelText('Interface'), 'interface-1')
    await user.click(screen.getByRole('button', { name: 'Save handoff' }))
    await waitFor(() => expect(createCircuitHandoff).toHaveBeenCalledWith(workspace, 'circuit-1', expect.objectContaining({ interface_id: 'interface-1', device_id: 'device-1' })))
    expect(await screen.findByText(/A side · fiber · LC · WAN1/)).toBeInTheDocument()
  })

  it('creates a rack from the restrained physical-placement form', async () => {
    const createRack = vi.fn().mockResolvedValue({ ...rack, id: 'rack-2', name: 'Distribution rack' })
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createRack })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })
    await user.click(screen.getByRole('button', { name: 'Racks' }))
    await user.click(screen.getByRole('button', { name: 'Add rack' }))
    await user.type(screen.getByLabelText('Name'), 'Distribution rack')
    await user.selectOptions(screen.getByLabelText('Site'), 'site-1')
    await user.click(screen.getByRole('button', { name: 'Save rack' }))
    await waitFor(() => expect(createRack).toHaveBeenCalledWith(workspace, expect.objectContaining({ name: 'Distribution rack', site_id: 'site-1', unit_count: 42 })))
  })

  it('creates and edits physical device placement', async () => {
    const createDevice = vi.fn().mockResolvedValue({ ...device, id: 'device-2', name: 'Edge firewall' })
    const updateDevice = vi.fn().mockResolvedValue({ ...device, name: 'Core switch revised' })
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createDevice, updateDevice })} relationshipsClient={relationshipsClient} />)
    await screen.findByRole('button', { name: 'Core switch' })

    await user.click(screen.getByRole('button', { name: 'Add device' }))
    await user.type(screen.getByLabelText('Name'), 'Edge firewall')
    await user.selectOptions(screen.getByLabelText('Role'), 'firewall')
    await user.selectOptions(screen.getByLabelText('Rack'), 'rack-1')
    await user.clear(screen.getByLabelText('Starting unit'))
    await user.type(screen.getByLabelText('Starting unit'), '10')
    await user.click(screen.getByRole('button', { name: 'Save device' }))
    await waitFor(() => expect(createDevice).toHaveBeenCalledWith(workspace, expect.objectContaining({
      name: 'Edge firewall', role: 'firewall', rack_id: 'rack-1', rack_unit: 10,
    })))

    await user.click(screen.getAllByRole('button', { name: 'Edit' })[0])
    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'Core switch revised')
    await user.click(screen.getByRole('button', { name: 'Save device' }))
    await waitFor(() => expect(updateDevice).toHaveBeenCalledWith(
      workspace,
      'device-1',
      expect.objectContaining({ name: 'Core switch revised' }),
    ))
  })

  it('shows bounded empty and request-failure states', async () => {
    const empty = networkClient({
      listRacks: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: false }),
      listDevices: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: false, can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false }),
    })
    const { rerender } = render(<Networks workspace={workspace} client={empty} relationshipsClient={relationshipsClient} />)
    expect(await screen.findByText('No network devices match this workspace and search.')).toBeInTheDocument()

    const failed = networkClient({ listRacks: vi.fn().mockRejectedValue(new Error('Network inventory unavailable.')) })
    rerender(<Networks workspace={{ ...workspace, id: 'client-2' }} client={failed} relationshipsClient={relationshipsClient} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Network inventory unavailable.')
  })
})
