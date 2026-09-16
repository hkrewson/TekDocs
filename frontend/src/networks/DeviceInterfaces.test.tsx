import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { AddressQuery, NetworksClient } from './api'
import { DeviceInterfaces } from './DeviceInterfaces'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup({ failed = false, failedMove = false, denied = false, otherParent = false } = {}) {
  window.history.replaceState({}, '', '/networks?view=devices&devices=device-1&devices_section=interfaces')
  const record = { id: 'port-1', name: 'Port 01', device_id: otherParent ? 'device-2' : 'device-1', device_name: 'Switch', kind: 'physical', status: 'active', description: 'Cable destination' }
  const interfaceCollection = vi.fn().mockImplementation((_workspace, query: AddressQuery) => {
    const visible = record.device_id === query.device_id || otherParent
    return Promise.resolve({ results: visible ? [record] : [], count: visible ? 31 : 0, page: 1, page_size: 25, has_more: visible, can_manage: !denied })
  })
  const interfaceDetail = vi.fn().mockResolvedValue(record)
  const updateInterface = failed ? vi.fn().mockRejectedValue(new Error('Permission changed. Your entries are retained.')) : vi.fn().mockImplementation((_workspace, _id, values) => Promise.resolve({ ...record, ...values }))
  const destination = { id: 'device-2', name: 'Edge router', role: 'router', status: 'active', hardware_asset_id: null, hardware_asset_name: null, site_id: null, site_name: null, location_id: null, location_name: null, rack_id: null, rack_name: null, rack_unit: null, rack_units: 1 }
  const deviceCollection = vi.fn().mockResolvedValue({ results: [destination], count: 1, page: 1, page_size: 25, has_more: false, can_manage: true, can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false })
  const moveInterface = failedMove ? vi.fn().mockRejectedValue(new Error('Device assignment changed. Your choice has been kept.')) : vi.fn().mockImplementation(() => { Object.assign(record, { device_id: destination.id, device_name: destination.name }); return Promise.resolve({ ...record }) })
  const createInterface = vi.fn().mockImplementation((_workspace, values) => Promise.resolve({ ...record, ...values }))
  const client = { interfaceCollection, interfaceDetail, updateInterface, createInterface, deviceCollection, moveInterface } as unknown as NetworksClient
  const preferences = defaultPreferences(['name', 'kind', 'status'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  render(<ApplicationRouter><DeviceInterfaces workspace={workspace} deviceId="device-1" client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { user: userEvent.setup(), interfaceCollection, interfaceDetail, updateInterface, createInterface, deviceCollection, moveInterface }
}
it('loads the parent page, opens selected details and saves without resending the parent', async () => {
  const { user, interfaceCollection, interfaceDetail, updateInterface } = setup()
  await user.type(await screen.findByRole('searchbox', { name: 'Search interfaces' }), 'Cable')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(interfaceCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ device_id: 'device-1', q: 'Cable', page_size: 25 }), expect.any(AbortSignal)))
  expect(interfaceDetail).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Port 01' }))
  await user.click(await screen.findByRole('button', { name: 'Edit interface' }))
  await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'disabled')
  await user.click(screen.getByRole('button', { name: 'Save interface' }))
  await waitFor(() => expect(updateInterface).toHaveBeenCalledWith(workspace, 'port-1', { name: 'Port 01', kind: 'physical', status: 'disabled', description: 'Cable destination' }))
  await user.click(await screen.findByRole('button', { name: 'Back to interfaces' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Port 01' })).toHaveFocus())
})
it('creates in the selected device and protects a new draft through return navigation', async () => {
  const { user, createInterface } = setup()
  await user.click(await screen.findByRole('button', { name: 'New interface' }))
  await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Uplink')
  await user.click(screen.getByRole('button', { name: 'Back to interfaces' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Uplink')
  await user.click(screen.getByRole('button', { name: 'Save interface' }))
  await waitFor(() => expect(createInterface).toHaveBeenCalledWith(workspace, { name: 'Uplink', kind: 'physical', status: 'active', description: '', device_id: 'device-1' }))
})
it('retains denied saves and does not retry after keeping the draft', async () => {
  const { user, updateInterface } = setup({ failed: true })
  await user.click(await screen.findByRole('button', { name: 'Port 01' }))
  await user.click(await screen.findByRole('button', { name: 'Edit interface' }))
  await user.type(screen.getByRole('textbox', { name: 'Description' }), ' changed')
  await user.click(screen.getByRole('button', { name: 'Save interface' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Permission changed')
  await user.click(screen.getByRole('button', { name: 'Back to interfaces' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByRole('textbox', { name: 'Description' })).toHaveValue('Cable destination changed')
  expect(updateInterface).toHaveBeenCalledTimes(1)
})
it('moves to a searched device with the expected parent and returns to the source list', async () => {
  const { user, deviceCollection, moveInterface } = setup()
  await user.click(await screen.findByRole('button', { name: 'Port 01' }))
  await user.click(await screen.findByRole('button', { name: 'Move to another device' }))
  await user.type(screen.getByRole('searchbox', { name: 'Search destination devices' }), 'Edge')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(deviceCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: 'Edge', page_size: 25 }), expect.any(AbortSignal)))
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Available devices' }), 'device-2')
  await user.click(screen.getByRole('button', { name: 'Confirm device move' }))
  await waitFor(() => expect(moveInterface).toHaveBeenCalledWith(workspace, 'port-1', 'device-2', 'device-1'))
  expect(await screen.findByText('0 interfaces')).toBeVisible()
})
it('retains a failed destination choice through guarded return without retrying', async () => {
  const { user, moveInterface } = setup({ failedMove: true })
  await user.click(await screen.findByRole('button', { name: 'Port 01' }))
  await user.click(await screen.findByRole('button', { name: 'Move to another device' }))
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Available devices' }), 'device-2')
  await user.click(screen.getByRole('button', { name: 'Confirm device move' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Device assignment changed')
  await user.click(screen.getByRole('button', { name: 'Back to interfaces' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByRole('combobox', { name: 'Available devices' })).toHaveValue('device-2')
  expect(moveInterface).toHaveBeenCalledTimes(1)
})
it('rejects a child from another device and retains a return path', async () => {
  const { user } = setup({ otherParent: true })
  await user.click(await screen.findByRole('button', { name: 'Port 01' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable')
  expect(screen.queryByRole('button', { name: 'Edit interface' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Back to interfaces' }))
  expect(await screen.findByRole('button', { name: 'Port 01' })).toHaveFocus()
})
it('keeps read-only details while hiding create and edit', async () => {
  const { user } = setup({ denied: true })
  await user.click(await screen.findByRole('button', { name: 'Port 01' }))
  expect(await screen.findByText('Cable destination')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Edit interface' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'New interface' })).not.toBeInTheDocument()
})
