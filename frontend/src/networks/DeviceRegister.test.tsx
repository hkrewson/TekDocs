import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { DeviceRegister } from './DeviceRegister'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup(denied = false, failed = false, createAllowed = true) {
  window.history.replaceState({}, '', '/networks?view=devices')
  const record = { id: 'device-1', name: 'Core switch', role: 'switch', status: 'active', hardware_asset_id: null, hardware_asset_name: null, site_id: 'site-1', site_name: 'Campus', location_id: null, location_name: null, rack_id: 'rack-1', rack_name: 'Core rack', rack_unit: 2, rack_units: 1 }
  const deviceCollection = vi.fn().mockResolvedValue({ results: [record], count: 31, page: 1, page_size: 25, has_more: true, can_manage: !denied, can_create: createAllowed && !denied })
  const updateDevice = failed ? vi.fn().mockRejectedValue(new Error('Those units overlap.')) : vi.fn().mockImplementation((_workspace, _id, values) => Promise.resolve({ ...record, ...values }))
  const createDevice = vi.fn().mockImplementation((_workspace, values) => Promise.resolve({ ...record, ...values }))
  const choices = { results: [{ id: 'asset-1', name: 'Available switch' }], count: 1, page: 1, page_size: 25, has_more: false }
  const hardwareAssetChoices = vi.fn().mockResolvedValue(choices)
  const client = { deviceCollection, deviceDetail: vi.fn().mockResolvedValue(record), updateDevice, createDevice, hardwareAssetChoices, rackCollection: vi.fn().mockResolvedValue({ ...choices, results: [{ id: 'rack-2', name: 'New rack' }] }) } as unknown as NetworksClient
  const preferences = defaultPreferences(['name', 'role', 'status', 'site', 'rack', 'rack_unit'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  render(<ApplicationRouter><DeviceRegister workspace={workspace} client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { deviceCollection, updateDevice, createDevice, hardwareAssetChoices, user: userEvent.setup() }
}
it('searches the authorized collection and edits facts without changing restricted bindings or placement', async () => {
  const { user, deviceCollection, updateDevice, hardwareAssetChoices } = setup()
  await user.type(await screen.findByRole('searchbox', { name: 'Search devices' }), 'Core')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(deviceCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: 'Core', page_size: 25 }), expect.any(AbortSignal)))
  await user.click(screen.getByRole('button', { name: 'Core switch' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core switch' })
  expect(within(drawer).getByText('Unassigned or unavailable')).toBeInTheDocument()
  await user.click(within(drawer).getByRole('button', { name: 'Edit device details' }))
  await user.selectOptions(within(drawer).getByLabelText('Status'), 'offline')
  await user.click(within(drawer).getByRole('button', { name: 'Save device' }))
  await within(drawer).findByRole('button', { name: 'Edit device details' })
  expect(updateDevice).toHaveBeenCalledWith(workspace, 'device-1', { name: 'Core switch', role: 'switch', status: 'offline' })
  expect(hardwareAssetChoices).not.toHaveBeenCalled()
  fireEvent(drawer, new Event('cancel', { cancelable: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})
it('keeps failed rack placement drafts and never overwrites device facts', async () => {
  const { user, updateDevice } = setup(false, true)
  await user.click(await screen.findByRole('button', { name: 'Core switch' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core switch' })
  await user.click(within(drawer).getByRole('link', { name: 'Placement' }))
  await user.click(within(drawer).getByRole('button', { name: 'Edit placement' }))
  await user.selectOptions(await within(drawer).findByRole('combobox', { name: 'Rack results' }), 'rack-2')
  await user.click(within(drawer).getByRole('button', { name: 'Save placement' }))
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('Those units overlap.')
  expect(updateDevice).toHaveBeenCalledWith(workspace, 'device-1', { site_id: 'site-1', location_id: null, rack_id: 'rack-2', rack_unit: 2, rack_units: 1 })
  fireEvent(drawer, new Event('cancel', { cancelable: true }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(within(drawer).getByRole('combobox', { name: 'Rack results' })).toHaveValue('rack-2')
  expect(updateDevice).toHaveBeenCalledTimes(1)
})
it('requires an available asset and creates an unplaced device before placement editing', async () => {
  const { user, createDevice } = setup()
  await user.click(await screen.findByRole('button', { name: 'New device' }))
  const drawer = await screen.findByRole('dialog', { name: 'New device' })
  await user.type(within(drawer).getByLabelText('Name'), 'New switch')
  await user.click(within(drawer).getByRole('button', { name: 'Save device' }))
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('Choose a hardware asset')
  expect(createDevice).not.toHaveBeenCalled()
  await user.selectOptions(await within(drawer).findByRole('combobox', { name: 'Hardware asset results' }), 'asset-1')
  await user.click(within(drawer).getByRole('button', { name: 'Save device' }))
  expect(createDevice).toHaveBeenCalledWith(workspace, { name: 'New switch', role: 'switch', status: 'active', hardware_asset_id: 'asset-1', site_id: null, location_id: null, rack_id: null, rack_unit: null, rack_units: 1 })
})
it('does not offer creation when asset permission is absent', async () => {
  const { user } = setup(false, false, false)
  await user.click(await screen.findByRole('button', { name: 'Core switch' }))
  await screen.findByRole('dialog', { name: 'Core switch' })
  expect(screen.queryByRole('button', { name: 'New device' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit device details' })).toBeInTheDocument()
})
it('omits all editing actions when network editing is denied', async () => {
  const { user } = setup(true)
  await user.click(await screen.findByRole('button', { name: 'Core switch' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core switch' })
  expect(screen.queryByRole('button', { name: 'Edit device details' })).not.toBeInTheDocument()
  await user.click(within(drawer).getByRole('link', { name: 'Placement' }))
  expect(screen.queryByRole('button', { name: 'Edit placement' })).not.toBeInTheDocument()
})
