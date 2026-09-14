import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { RackRegister } from './RackRegister'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup(denied = false, failed = false) {
  window.history.replaceState({}, '', '/networks?view=racks')
  const record = { id: 'rack-1', name: 'Core rack', site_id: 'site-1', site_name: 'Main site', location_id: 'room-1', location_name: 'Room', unit_count: 42, status: 'active', device_count: 1 }
  const rackCollection = vi.fn().mockResolvedValue({ results: [record], count: 31, page: 1, page_size: 25, has_more: true, can_manage: !denied })
  const write = failed ? vi.fn().mockRejectedValue(new Error('Move installed devices first.')) : vi.fn().mockImplementation((_workspace, _id, values) => Promise.resolve({ ...record, ...values }))
  const deviceCollection = vi.fn().mockResolvedValue({ results: [{ id: 'device-1', name: 'Switch', rack_unit: 1, rack_units: 2, status: 'active' }], count: 1, page: 1, page_size: 25, has_more: false })
  const assignmentChoices = vi.fn().mockResolvedValue({ results: [{ id: 'site-2', name: 'Other site', identifier: 'OTHER' }], count: 1, page: 1, page_size: 25, has_more: false })
  const locationChoices = vi.fn().mockResolvedValue({ results: [], count: 0, page: 1, page_size: 25, has_more: false })
  const client = { rackCollection, rackDetail: vi.fn().mockResolvedValue(record), updateRack: write, createRack: write, deviceCollection, assignmentChoices, locationChoices } as unknown as NetworksClient
  const preferences = defaultPreferences(['name', 'site', 'location', 'status', 'unit_count', 'device_count'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  render(<ApplicationRouter><RackRegister workspace={workspace} client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { rackCollection, deviceCollection, write, assignmentChoices, locationChoices, user: userEvent.setup() }
}
it('searches bounded summaries and lazily opens installed devices in the same drawer', async () => {
  const { user, rackCollection, deviceCollection } = setup()
  await user.type(await screen.findByRole('searchbox', { name: 'Search racks' }), 'Core')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(rackCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: 'Core', page: 1, page_size: 25 }), expect.any(AbortSignal)))
  await user.click(screen.getByRole('button', { name: 'Core rack' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core rack' })
  expect(within(drawer).getByText('Main site')).toBeInTheDocument()
  expect(deviceCollection).not.toHaveBeenCalled()
  await user.click(within(drawer).getByRole('link', { name: 'Devices' }))
  await within(drawer).findByRole('button', { name: 'Switch' })
  expect(deviceCollection).toHaveBeenCalledWith(workspace, expect.objectContaining({ rack_id: 'rack-1', page_size: 25 }), expect.any(AbortSignal))
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
})
it('preserves failed values and clears the old location only when the site changes', async () => {
  const { user, write, locationChoices } = setup(false, true)
  await user.click(await screen.findByRole('button', { name: 'Core rack' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core rack' })
  await user.click(within(drawer).getByRole('button', { name: 'Edit rack' }))
  await user.selectOptions(await within(drawer).findByRole('combobox', { name: 'Site results' }), 'site-2')
  await waitFor(() => expect(locationChoices).toHaveBeenLastCalledWith(workspace, 'site-2', '', 1, expect.any(AbortSignal)))
  await user.click(within(drawer).getByRole('button', { name: 'Save rack' }))
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('Move installed devices first.')
  expect(write).toHaveBeenCalledWith(workspace, 'rack-1', expect.objectContaining({ site_id: 'site-2', location_id: null }))
  fireEvent(drawer, new Event('cancel', { cancelable: true }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(within(drawer).getByRole('combobox', { name: 'Site results' })).toHaveValue('site-2')
  expect(write).toHaveBeenCalledTimes(1)
})
it('saves ordinary edits without changing assignments and dismisses immediately', async () => {
  const { user, write } = setup()
  await user.click(await screen.findByRole('button', { name: 'Core rack' }))
  const drawer = await screen.findByRole('dialog', { name: 'Core rack' })
  await user.click(within(drawer).getByRole('button', { name: 'Edit rack' }))
  await user.selectOptions(within(drawer).getByLabelText('Status'), 'retired')
  await user.click(within(drawer).getByRole('button', { name: 'Save rack' }))
  await within(drawer).findByRole('button', { name: 'Edit rack' })
  expect(write).toHaveBeenCalledWith(workspace, 'rack-1', expect.objectContaining({ site_id: 'site-1', location_id: 'room-1', status: 'retired' }))
  fireEvent(drawer, new Event('cancel', { cancelable: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Core rack' })).toHaveFocus()
})
it('requires a selected site on creation and protects read-only records', async () => {
  const { user, write } = setup()
  await user.click(await screen.findByRole('button', { name: 'New rack' }))
  const drawer = await screen.findByRole('dialog', { name: 'New rack' })
  await user.type(within(drawer).getByLabelText('Name'), 'New rack')
  await user.click(within(drawer).getByRole('button', { name: 'Save rack' }))
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('Choose a site')
  expect(write).not.toHaveBeenCalled()
})
it('omits creation and editing when permission is denied', async () => {
  const { user } = setup(true)
  await user.click(await screen.findByRole('button', { name: 'Core rack' }))
  await screen.findByRole('dialog', { name: 'Core rack' })
  expect(screen.queryByRole('button', { name: 'Edit rack' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'New rack' })).not.toBeInTheDocument()
})
