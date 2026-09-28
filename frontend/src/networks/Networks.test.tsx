import type { ReactNode } from 'react'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import { render as rawRender, screen, waitFor } from '@testing-library/react'
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
  description: 'Primary office network', vlan: 20, cidr: '192.0.2.0/24', subnet_mask: '255.255.255.0', broadcast_ip: '192.0.2.255', gateway: '192.0.2.1', use_full_range: true,
  range_start: '192.0.2.1', range_end: '192.0.2.254', primary_dns: '9.9.9.9', secondary_dns: '1.1.1.1', dhcp_server: '192.0.2.2', notes: '',
}

function networkClient(overrides: Partial<NetworksClient> = {}): NetworksClient {
  return {
    detail: vi.fn().mockResolvedValue(network),
    collection: overrides.listNetworks ?? vi.fn().mockResolvedValue({ results: [network], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true }),
    listNetworks: vi.fn().mockResolvedValue({ results: [network], page: 1, page_size: 100, count: 1, has_more: false, can_manage: true }),
    createNetwork: vi.fn().mockResolvedValue(network), updateNetwork: vi.fn().mockResolvedValue(network),
    choices: vi.fn().mockResolvedValue({ sites: [{ id: 'site-1', name: 'Headquarters' }], locations: [{ id: 'location-1', name: 'Server room', site_id: 'site-1' }], racks: [], hardware_assets: [] }),
    ...overrides,
  } as unknown as NetworksClient
}

const relationshipsClient = {
  list: vi.fn(), search: vi.fn(), create: vi.fn(), archive: vi.fn(), linkTypes: vi.fn(),
} as RelationshipsClient

const preferenceClient = { load: vi.fn().mockResolvedValue(defaultPreferences(['cidr', 'vlan', 'subnet_mask'])), save: vi.fn(), reset: vi.fn() }
function render(children: ReactNode) { return rawRender(<ApplicationRouter>{children}</ApplicationRouter>) }

describe('Networks', () => {
  it('shows the network collection and exposes the separate NetBox register', async () => {
    render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} preferenceClient={preferenceClient} />)
    expect(await screen.findByRole('button', { name: '192.0.2.0/24' })).toBeInTheDocument()
    expect(screen.getByText('255.255.255.0')).toBeInTheDocument()
    expect(screen.queryByText('Headquarters · Server room')).not.toBeInTheDocument()
    expect(screen.queryByText('192.0.2.1–192.0.2.254')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'NetBox' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Racks' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'VLANs' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'VRFs' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Circuits' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'IP addresses' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'MAC addresses' })).not.toBeInTheDocument()
  })

  it('returns removed network views to the CIDR collection', async () => {
    window.history.replaceState({}, '', '/networks?view=vrfs')
    render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} preferenceClient={preferenceClient} />)
    expect(await screen.findByRole('button', { name: '192.0.2.0/24' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Networks' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByText('New VRF')).not.toBeInTheDocument()
  })

  it('creates one CIDR record and leaves mask and broadcast calculation to the server', async () => {
    const createNetwork = vi.fn().mockResolvedValue({ ...network, id: 'network-2', name: 'Guest Wi-Fi', vlan: 30, cidr: '198.51.100.0/24' })
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient({ createNetwork })} relationshipsClient={relationshipsClient} preferenceClient={preferenceClient} />)
    await screen.findByRole('button', { name: '192.0.2.0/24' })
    await user.click(screen.getByRole('button', { name: 'New network' }))
    await user.type(screen.getByLabelText('VLAN'), '30')
    await user.type(screen.getByLabelText(/^Network \(CIDR\)/), '198.51.100.0/24')
    await user.type(screen.getByLabelText('DHCP server IP'), '198.51.100.2')
    await user.type(screen.getByLabelText('DNS server 1'), '9.9.9.9')
    await user.click(screen.getByRole('button', { name: 'Save network' }))
    await waitFor(() => expect(createNetwork).toHaveBeenCalledWith(workspace, expect.objectContaining({
      name: '198.51.100.0/24', location_id: null, vlan: 30, cidr: '198.51.100.0/24', dhcp_server: '198.51.100.2',
    })))
  })

  it('does not expose legacy location, gateway, notes, or assignable-range fields', async () => {
    const user = userEvent.setup()
    render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} preferenceClient={preferenceClient} />)
    await screen.findByRole('button', { name: '192.0.2.0/24' })
    await user.click(screen.getByRole('button', { name: 'New network' }))
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Location')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Assignable range start')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Gateway')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Notes')).not.toBeInTheDocument()
  })

  it('searches only the simple network records and reports request failures', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<Networks workspace={workspace} client={networkClient()} relationshipsClient={relationshipsClient} preferenceClient={preferenceClient} />)
    await screen.findByRole('button', { name: '192.0.2.0/24' })
    await user.type(screen.getByLabelText('Search networks'), 'missing')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    const failed = networkClient({ listNetworks: vi.fn().mockRejectedValue(new Error('Networks unavailable.')) })
    rerender(<ApplicationRouter><Networks workspace={{ ...workspace, id: 'client-2' }} client={failed} relationshipsClient={relationshipsClient} preferenceClient={preferenceClient} /></ApplicationRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Networks could not be loaded.')
  })
})
