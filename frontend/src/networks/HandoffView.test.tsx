import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import { browserOperationsClient } from '../operations/api'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import type { WorkspaceContext } from '../workspaces/api'
import type { HandoffDetail, NetworksClient } from './api'
import { HandoffView } from './HandoffView'
const workspace = { kind: 'msp', id: 'msp' } as WorkspaceContext
const record: HandoffDetail = { id: 'handoff', circuit_id: 'circuit', name: 'Demarc', side: 'a', media: 'fiber', connector: 'LC', provider_reference: 'REF', description: 'Notes', site_id: 'site', site_name: 'Office', location_id: 'location', location_name: 'Closet', device_id: 'device', device_name: 'Router', interface_id: 'interface', interface_name: 'WAN1' }
function setup({ create = false, denied = false, fail = false } = {}) {
  const user = userEvent.setup(), saved = vi.fn(), returned = vi.fn()
  const update = fail ? vi.fn().mockRejectedValue(new Error('Interface already assigned. Your entries have been kept.')) : vi.fn().mockResolvedValue(record)
  const createHandoff = vi.fn().mockResolvedValue(record)
  const values = { results: [{ id: 'new', name: 'New choice' }], count: 31, page: 1, page_size: 25, has_more: true, can_manage: true }
  const sites = vi.fn().mockResolvedValue(values), locations = vi.fn().mockResolvedValue(values), devices = vi.fn().mockResolvedValue(values), interfaces = vi.fn().mockResolvedValue(values)
  const client = { updateCircuitHandoff: update, createCircuitHandoff: createHandoff, assignmentChoices: sites, locationChoices: locations, deviceCollection: devices, interfaceCollection: interfaces } as unknown as NetworksClient
  window.history.replaceState({}, '', '/networks?view=circuits&circuits=circuit&handoff=handoff')
  render(<ApplicationRouter><HandoffView record={create ? null : record} workspace={workspace} client={client} parentId="circuit" canManage={!denied} onSaved={saved} onReturn={returned} /></ApplicationRouter>)
  return { user, update, createHandoff, sites, locations, devices, interfaces, saved }
}
it('edits details without resubmitting placement and restores heading focus', async () => {
  const { user, update, sites } = setup()
  expect(screen.getByRole('heading', { name: 'Demarc' })).toHaveFocus()
  await user.click(screen.getByRole('button', { name: 'Edit handoff details' }))
  await user.type(screen.getByRole('textbox', { name: 'Description' }), ' updated')
  await user.click(screen.getByRole('button', { name: 'Save handoff' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith(workspace, 'circuit', 'handoff', expect.objectContaining({ description: 'Notes updated' })))
  expect(update.mock.calls[0]?.[3]).not.toHaveProperty('site_id')
  expect(sites).not.toHaveBeenCalled()
  expect(screen.getByRole('heading', { name: 'Demarc' })).toHaveFocus()
})
it('uses scoped choices, retains off-page labels, and clears child selections on parent change', async () => {
  const { user, update, sites, interfaces, locations } = setup()
  await user.click(screen.getByRole('button', { name: 'Edit handoff placement' }))
  expect(await screen.findByText('Closet')).toBeVisible()
  await waitFor(() => expect(locations).toHaveBeenCalledWith(workspace, 'site', '', 1, expect.any(AbortSignal)))
  await waitFor(() => expect(interfaces).toHaveBeenCalledWith(workspace, expect.objectContaining({ device_id: 'device', page_size: 25 }), expect.any(AbortSignal)))
  const site = screen.getByRole('region', { name: 'Site' })
  await user.click(within(site).getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(sites).toHaveBeenCalledWith(workspace, 'site', '', 2, expect.any(AbortSignal)))
  expect(within(site).getByText('Office')).toBeVisible()
  await user.selectOptions(within(site).getByRole('combobox'), 'new')
  expect(screen.queryByText('Closet')).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Interface' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Save handoff' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith(workspace, 'circuit', 'handoff', { site_id: 'new', location_id: null, device_id: null, interface_id: null }))
})
it('preserves placement conflicts and guards cancellation without retry', async () => {
  const { user, update } = setup({ fail: true })
  await user.click(screen.getByRole('button', { name: 'Edit handoff placement' }))
  await user.click(await screen.findByRole('button', { name: 'Clear handoff interface' }))
  await user.click(screen.getByRole('button', { name: 'Save handoff' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Interface already assigned')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByRole('button', { name: 'Clear handoff interface' })).toBeDisabled()
  expect(update).toHaveBeenCalledTimes(1)
})
it('creates a handoff with explicit unassigned placement and no choice downloads', async () => {
  const { user, createHandoff, sites, devices } = setup({ create: true })
  await user.type(screen.getByRole('textbox', { name: 'Name' }), 'New demarc')
  await user.click(screen.getByRole('button', { name: 'Save handoff' }))
  await waitFor(() => expect(createHandoff).toHaveBeenCalledWith(workspace, 'circuit', expect.objectContaining({ name: 'New demarc', side: 'a', media: 'fiber', site_id: null, device_id: null, interface_id: null })))
  expect(sites).not.toHaveBeenCalled(); expect(devices).not.toHaveBeenCalled()
})
it('hides edit actions from read-only viewers', () => {
  setup({ denied: true })
  expect(screen.queryByRole('button', { name: 'Edit handoff details' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit handoff placement' })).not.toBeInTheDocument()
})
it('clears the interface when changing devices while preserving site and location', async () => {
  const { user, update, interfaces } = setup()
  await user.click(screen.getByRole('button', { name: 'Edit handoff placement' }))
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Device' }), 'new')
  await waitFor(() => expect(interfaces).toHaveBeenCalledWith(workspace, expect.objectContaining({ device_id: 'new' }), expect.any(AbortSignal)))
  expect(screen.getByRole('button', { name: 'Clear handoff interface' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Save handoff' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith(workspace, 'circuit', 'handoff', { site_id: 'site', location_id: 'location', device_id: 'new', interface_id: null }))
})

it('loads only selected handoff history on demand, pages by URL, and restores details focus', async () => {
  const activity = vi.spyOn(browserOperationsClient, 'activity').mockReset().mockImplementation((_scope, query) => Promise.resolve({ results: [], count: 31, page: query.page ?? 1, page_size: 25, has_more: query.page !== 2, actions: [] }))
  const { user } = setup()
  expect(activity).not.toHaveBeenCalled()
  await user.click(screen.getByRole('link', { name: 'View handoff history' }))
  expect(await screen.findByText('No changes have been recorded for this handoff.')).toBeVisible()
  expect(activity).toHaveBeenLastCalledWith({}, { entity_id: 'circuit', handoff_id: 'handoff', page: 1, page_size: 25 }, expect.any(AbortSignal))
  await user.click(screen.getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(activity).toHaveBeenLastCalledWith({}, { entity_id: 'circuit', handoff_id: 'handoff', page: 2, page_size: 25 }, expect.any(AbortSignal)))
  expect(window.location.search).toContain('handoff_history_page=2')
  await user.click(screen.getByRole('link', { name: 'Back to handoff details' }))
  expect(screen.getByRole('heading', { name: 'Demarc' })).toHaveFocus()
  expect(screen.getByText('WAN1')).toBeVisible()
  expect(window.location.search).not.toContain('handoff_history_page')
})

it('keeps a return path after denied history and retries only when requested', async () => {
  const activity = vi.spyOn(browserOperationsClient, 'activity').mockReset().mockRejectedValueOnce(new AuthRequestError('Not allowed', 403)).mockResolvedValue({ results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] })
  const { user } = setup({ denied: true })
  await user.click(screen.getByRole('link', { name: 'View handoff history' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('You do not have permission to view this handoff history.')
  expect(activity).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('link', { name: 'Back to handoff details' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Retry history' }))
  expect(await screen.findByText('No changes have been recorded for this handoff.')).toBeVisible()
  expect(activity).toHaveBeenCalledTimes(2)
})
