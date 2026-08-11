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
    ...overrides,
  }
}

const relationshipsClient = {
  list: vi.fn().mockResolvedValue([]), search: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 15, count: 0, has_more: false }),
  create: vi.fn(), archive: vi.fn(), linkTypes: vi.fn().mockResolvedValue([]),
} as RelationshipsClient

describe('Networks', () => {
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
