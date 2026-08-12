import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { Networks } from './Networks'
import type { NetworkRecord, NetworksClient } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'], capabilities: [], organization: null,
}
const network: NetworkRecord = {
  id: 'network-1', name: 'Office LAN', location_id: 'location-1', location_name: 'Server room', site_name: 'Headquarters',
  description: 'Primary office network', vlan: 20, cidr: '192.0.2.0/24', gateway: '192.0.2.1', use_full_range: true,
  range_start: '192.0.2.1', range_end: '192.0.2.254', primary_dns: '9.9.9.9', secondary_dns: '1.1.1.1', notes: '',
}

function networkClient(overrides: Partial<NetworksClient> = {}): NetworksClient {
  return {
    listNetworks: vi.fn().mockResolvedValue({ results: [network], page: 1, page_size: 100, count: 1, has_more: false, can_manage: true }),
    createNetwork: vi.fn().mockResolvedValue(network), updateNetwork: vi.fn().mockResolvedValue(network),
    choices: vi.fn().mockResolvedValue({ sites: [{ id: 'site-1', name: 'Headquarters' }], locations: [{ id: 'location-1', name: 'Server room', site_id: 'site-1' }], racks: [], hardware_assets: [] }),
    ...overrides,
  } as unknown as NetworksClient
}

const relationshipsClient = {
  list: vi.fn(), search: vi.fn(), create: vi.fn(), archive: vi.fn(), linkTypes: vi.fn(),
} as RelationshipsClient

describe('Networks', () => {
  it('shows one simple network list without NetBox-style object tabs', async () => {
    render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} />)
    expect(await screen.findByText('Office LAN')).toBeInTheDocument()
    expect(screen.getByText('Headquarters · Server room')).toBeInTheDocument()
    expect(screen.getByText('192.0.2.0/24')).toBeInTheDocument()
    expect(screen.getByText('192.0.2.1–192.0.2.254')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'NetBox' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Racks' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'IP addresses' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'MAC addresses' })).not.toBeInTheDocument()
  })

  it('creates one network and lets the server calculate gateway and range', async () => {
    const createNetwork = vi.fn().mockResolvedValue({ ...network, id: 'network-2', name: 'Guest Wi-Fi', vlan: 30, cidr: '198.51.100.0/24' })
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createNetwork })} relationshipsClient={relationshipsClient} />)
    await screen.findByText('Office LAN')
    await user.click(screen.getByRole('button', { name: 'New network' }))
    await user.type(screen.getByLabelText('Name'), 'Guest Wi-Fi')
    await user.selectOptions(screen.getByLabelText('Location'), 'location-1')
    await user.type(screen.getByLabelText('VLAN'), '30')
    await user.type(screen.getByLabelText(/^Network \(CIDR\)/), '198.51.100.0/24')
    await user.type(screen.getByLabelText('Primary DNS'), '9.9.9.9')
    expect(screen.queryByLabelText('Gateway')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save network' }))
    await waitFor(() => expect(createNetwork).toHaveBeenCalledWith(workspace, expect.objectContaining({
      name: 'Guest Wi-Fi', location_id: 'location-1', vlan: 30, cidr: '198.51.100.0/24', use_full_range: true,
      range_start: null, range_end: null,
    })))
  })

  it('reveals a bounded manual assignable range only when requested', async () => {
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} />)
    await screen.findByText('Office LAN')
    await user.click(screen.getByRole('button', { name: 'New network' }))
    expect(screen.queryByLabelText('Assignable range start')).not.toBeInTheDocument()
    await user.click(screen.getByLabelText('Use the full usable address range'))
    expect(screen.getByLabelText('Assignable range start')).toBeRequired()
    expect(screen.getByLabelText('Assignable range end')).toBeRequired()
  })

  it('searches only the simple network records and reports request failures', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} />)
    await screen.findByText('Office LAN')
    await user.type(screen.getByLabelText('Search networks'), 'missing')
    expect(screen.getByText('No networks match this search.')).toBeInTheDocument()

    const failed = networkClient({ listNetworks: vi.fn().mockRejectedValue(new Error('Networks unavailable.')) })
    rerender(<Networks workspace={{ ...workspace, id: 'client-2' }} client={failed} relationshipsClient={relationshipsClient} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Networks unavailable.')
  })
})
