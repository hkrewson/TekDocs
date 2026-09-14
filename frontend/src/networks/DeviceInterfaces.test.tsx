import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { DeviceInterfaces } from './DeviceInterfaces'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup({ failed = false, denied = false, otherParent = false } = {}) {
  window.history.replaceState({}, '', '/networks?view=devices&devices=device-1&devices_section=interfaces')
  const record = { id: 'port-1', name: 'Port 01', device_id: otherParent ? 'device-2' : 'device-1', device_name: 'Switch', kind: 'physical', status: 'active', description: 'Cable destination' }
  const interfaceCollection = vi.fn().mockResolvedValue({ results: [record], count: 31, page: 1, page_size: 25, has_more: true, can_manage: !denied })
  const interfaceDetail = vi.fn().mockResolvedValue(record)
  const updateInterface = failed ? vi.fn().mockRejectedValue(new Error('Permission changed. Your entries are retained.')) : vi.fn().mockImplementation((_workspace, _id, values) => Promise.resolve({ ...record, ...values }))
  const createInterface = vi.fn().mockImplementation((_workspace, values) => Promise.resolve({ ...record, ...values }))
  const client = { interfaceCollection, interfaceDetail, updateInterface, createInterface } as unknown as NetworksClient
  const preferences = defaultPreferences(['name', 'kind', 'status'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  render(<ApplicationRouter><DeviceInterfaces workspace={workspace} deviceId="device-1" client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { user: userEvent.setup(), interfaceCollection, interfaceDetail, updateInterface, createInterface }
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
