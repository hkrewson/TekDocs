import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { browserOperationsClient } from '../operations/api'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { CircuitRegister } from './CircuitRegister'
afterEach(() => vi.restoreAllMocks())
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup({ denied = false, fail = false, mismatch = false, initial = '', unavailable = false } = {}) {
  const activity = vi.spyOn(browserOperationsClient, 'activity').mockResolvedValue({ results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] })
  window.history.replaceState({}, '', `/networks?view=circuits${initial}`)
  const circuit = { id: 'circuit-1', name: 'Primary circuit', provider_id: 'carrier-1', provider_name: 'Carrier', service_identifier: 'CKT-1', kind: 'internet', status: 'active', bandwidth_down_mbps: '1000.000', bandwidth_up_mbps: null, installed_on: null, service_starts_on: null, review_on: null, planned_disconnect_on: null, description: 'Service notes', lifecycle_events: [{ kind: 'review', date: '2026-01-01', label: 'Review circuit', state: 'overdue' }] }
  const handoff = { id: 'handoff-1', circuit_id: mismatch ? 'foreign' : 'circuit-1', name: 'Carrier demarc', side: 'a', media: 'fiber', connector: 'LC', provider_reference: 'DEMARC-1', site_name: 'Main office', description: 'Handoff notes' }
  const result = { page: 1, page_size: 25, count: 31, has_more: true, can_manage: !denied, can_create: false }
  const write = fail ? vi.fn().mockRejectedValue(new Error('Record changed. Your entries have been kept.')) : vi.fn().mockImplementation((_workspace, _id, changes) => Promise.resolve({ ...circuit, ...changes }))
  const handoffCollection = vi.fn().mockResolvedValue({ ...result, results: [handoff] })
  const client = { circuitCollection: vi.fn().mockResolvedValue({ ...result, results: [circuit] }), circuitDetail: unavailable ? vi.fn().mockRejectedValue(new Error('Unavailable')) : vi.fn().mockResolvedValue(circuit), handoffCollection, handoffDetail: vi.fn().mockResolvedValue(handoff), updateCircuit: write } as unknown as NetworksClient
  const preferenceClient = { load: vi.fn().mockResolvedValue(defaultPreferences(['name', 'provider_name', 'service_identifier', 'kind', 'status', 'bandwidth_down_mbps'])), save: vi.fn(), reset: vi.fn() }
  render(<ApplicationRouter><CircuitRegister workspace={workspace} client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { user: userEvent.setup(), activity, write, handoffCollection }
}
it('loads scoped handoffs on demand in one drawer and restores child focus', async () => {
  const { user, handoffCollection } = setup()
  await user.click(await screen.findByRole('button', { name: 'Primary circuit' }))
  const drawer = await screen.findByRole('dialog', { name: 'Primary circuit' })
  expect(handoffCollection).not.toHaveBeenCalled()
  expect(within(drawer).getByText(/Overdue/)).toBeVisible()
  await user.click(within(drawer).getByRole('link', { name: 'Handoffs' }))
  await user.type(await within(drawer).findByRole('searchbox'), 'DEMARC')
  await user.click(within(drawer).getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(handoffCollection).toHaveBeenLastCalledWith(workspace, 'circuit-1', expect.objectContaining({ circuit_id: 'circuit-1', q: 'DEMARC', page: 1, page_size: 25 }), expect.any(AbortSignal)))
  await user.click(await within(drawer).findByRole('button', { name: 'Carrier demarc' }))
  expect(await within(drawer).findByText('Handoff notes')).toBeVisible()
  expect(within(drawer).getByRole('heading', { name: 'Carrier demarc' })).toHaveFocus()
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  await user.click(within(drawer).getByRole('button', { name: 'Back to handoffs' }))
  expect(await within(drawer).findByRole('button', { name: 'Carrier demarc' })).toHaveFocus()
})
it('keeps failed edits through tab navigation and backdrop dismissal without retry', async () => {
  const { user, write } = setup({ fail: true, initial: '&circuits=circuit-1' })
  const drawer = await screen.findByRole('dialog', { name: 'Primary circuit' })
  await user.click(await within(drawer).findByRole('button', { name: 'Edit service details' }))
  await user.type(within(drawer).getByRole('textbox', { name: 'Description' }), ' changed')
  await user.click(within(drawer).getByRole('button', { name: 'Save circuit details' }))
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('Record changed')
  expect(write.mock.calls[0]?.[2]).not.toHaveProperty('provider_id')
  expect(write.mock.calls[0]?.[2]).not.toHaveProperty('contract_id')
  expect(write.mock.calls[0]?.[2]).not.toHaveProperty('status')
  await user.click(within(drawer).getByRole('link', { name: 'Handoffs' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  fireEvent.pointerDown(drawer, { button: 0, clientX: -10, clientY: -10 })
  fireEvent.click(drawer, { clientX: -10, clientY: -10 })
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(within(drawer).getByRole('textbox', { name: 'Description' })).toHaveValue('Service notes changed')
  expect(write).toHaveBeenCalledTimes(1)
})
it('preserves service fields on successful partial edits', async () => {
  const { user } = setup({ initial: '&circuits=circuit-1' })
  const drawer = await screen.findByRole('dialog', { name: 'Primary circuit' })
  await user.click(await within(drawer).findByRole('button', { name: 'Edit service details' }))
  await user.type(within(drawer).getByRole('textbox', { name: 'Description' }), ' verified')
  await user.click(within(drawer).getByRole('button', { name: 'Save circuit details' }))
  expect(await within(drawer).findByText('Service notes verified')).toBeVisible()
  expect(within(drawer).getByText('Carrier', { selector: 'dd' })).toBeVisible()
})
it('updates kind separately and confirms consequential status changes', async () => {
  const { user, write } = setup({ initial: '&circuits=circuit-1' })
  const drawer = await screen.findByRole('dialog', { name: 'Primary circuit' })
  await user.click(within(drawer).getByRole('button', { name: 'Edit circuit kind' }))
  await user.selectOptions(within(drawer).getByRole('combobox', { name: 'Kind' }), 'wan')
  await user.click(within(drawer).getByRole('button', { name: 'Save circuit kind' }))
  await waitFor(() => expect(write).toHaveBeenLastCalledWith(workspace, 'circuit-1', { kind: 'wan' }))
  expect(await within(drawer).findByText('WAN', { selector: 'dd' })).toBeVisible()

  await user.click(within(drawer).getByRole('button', { name: 'Change circuit status' }))
  await user.selectOptions(within(drawer).getByRole('combobox', { name: 'Status' }), 'suspended')
  await user.click(within(drawer).getByRole('button', { name: 'Review status change' }))
  const confirmation = within(drawer).getByRole('alertdialog')
  expect(confirmation).toHaveTextContent('It does not contact the provider or interrupt service.')
  expect(write).toHaveBeenCalledTimes(1)
  await user.click(within(confirmation).getByRole('button', { name: 'Change status' }))
  await waitFor(() => expect(write).toHaveBeenLastCalledWith(workspace, 'circuit-1', { status: 'suspended' }))
  expect(await within(drawer).findByText('Suspended', { selector: 'dd' })).toBeVisible()
})
it('keeps a failed disconnected status draft and does not retry it automatically', async () => {
  const { user, write } = setup({ fail: true, initial: '&circuits=circuit-1' })
  const drawer = await screen.findByRole('dialog', { name: 'Primary circuit' })
  await user.click(within(drawer).getByRole('button', { name: 'Change circuit status' }))
  await user.selectOptions(within(drawer).getByRole('combobox', { name: 'Status' }), 'disconnected')
  await user.click(within(drawer).getByRole('button', { name: 'Review status change' }))
  await user.click(within(drawer).getByRole('button', { name: 'Change status' }))
  expect(await within(drawer).findByRole('alert')).toHaveTextContent('Record changed')
  expect(within(drawer).getByRole('combobox', { name: 'Status' })).toHaveValue('disconnected')
  expect(within(drawer).getByRole('alertdialog')).toBeVisible()
  expect(write).toHaveBeenCalledTimes(1)
})
it('supports read-only history while hiding edit and create controls', async () => {
  const { user, activity } = setup({ denied: true, initial: '&circuits=circuit-1' })
  const drawer = await screen.findByRole('dialog', { name: 'Primary circuit' })
  expect(within(drawer).queryByRole('button', { name: 'Edit service details' })).not.toBeInTheDocument()
  expect(within(drawer).queryByRole('button', { name: 'Edit circuit kind' })).not.toBeInTheDocument()
  expect(within(drawer).queryByRole('button', { name: 'Change circuit status' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'New circuit' })).not.toBeInTheDocument()
  expect(activity).not.toHaveBeenCalled()
  await user.click(within(drawer).getByRole('link', { name: 'History' }))
  expect(await within(drawer).findByText('No circuit history is available.')).toBeVisible()
  expect(activity).toHaveBeenCalledWith({}, expect.objectContaining({ entity_id: 'circuit-1' }), expect.any(AbortSignal))
})
it('rejects a handoff that does not belong to the selected parent', async () => {
  setup({ mismatch: true, initial: '&circuits=circuit-1&circuits_section=handoffs&handoff=handoff-1' })
  const drawer = await screen.findByRole('dialog', { name: 'Primary circuit' })
  expect(await within(drawer).findByRole('alert')).toBeVisible()
  expect(within(drawer).queryByText('Handoff notes')).not.toBeInTheDocument()
})
it('keeps a return path for unavailable circuit links', async () => {
  setup({ unavailable: true, initial: '&circuits=missing' })
  const drawer = await screen.findByRole('dialog', { name: 'Circuits' })
  expect(await within(drawer).findByRole('alert')).toBeVisible()
  expect(within(drawer).getByRole('button', { name: 'Back to circuits' })).toBeVisible()
})
