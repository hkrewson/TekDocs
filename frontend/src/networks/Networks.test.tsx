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
    ...overrides,
  }
}

const relationshipsClient = {
  list: vi.fn().mockResolvedValue([]), search: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 15, count: 0, has_more: false }),
  create: vi.fn(), archive: vi.fn(), linkTypes: vi.fn().mockResolvedValue([]),
} as RelationshipsClient

describe('Networks', () => {
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
