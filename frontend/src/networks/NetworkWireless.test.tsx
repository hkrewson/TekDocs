import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { NetworkWireless } from './NetworkWireless'

const workspace: WorkspaceContext = { kind: 'organization', id: 'client-1', name: 'Client', classifications: ['client'], capabilities: [], organization: null }
const record = { id: 'wifi-1', ssid: 'Office Staff', subnet_id: 'network-1', status: 'active', purpose: 'corporate', security: 'wpa3_enterprise', hidden: false, client_isolation: true, description: '', site_id: 'site-1', site_name: 'Headquarters', vlan_id: 'vlan-1', vlan_name: 'Office', vlan_number: 20, subnet_cidr: '192.0.2.0/24' }
function setup(overrides: Partial<NetworksClient> = {}) {
  const preferences = defaultPreferences(['name', 'status', 'purpose', 'security'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  const wirelessCollection = vi.fn().mockResolvedValue({ results: [record], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true })
  const wirelessDetail = vi.fn().mockResolvedValue(record)
  const updateWireless = vi.fn().mockResolvedValue({ ...record, status: 'disabled' })
  const createWireless = vi.fn().mockResolvedValue(record)
  const client = { wirelessCollection, wirelessDetail, updateWireless, createWireless, ...overrides } as unknown as NetworksClient
  render(<ApplicationRouter><NetworkWireless workspace={workspace} subnetId="network-1" client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { wirelessCollection, wirelessDetail, updateWireless, createWireless, preferenceClient, user: userEvent.setup() }
}
beforeEach(() => { window.history.replaceState({}, '', '/networks?section=wireless') })

it('fetches summaries before details and searches the full parent collection', async () => {
  const { wirelessCollection, wirelessDetail, user, preferenceClient } = setup()
  await screen.findByRole('button', { name: 'Office Staff' })
  expect(wirelessDetail).not.toHaveBeenCalled()
  await user.type(screen.getByRole('searchbox', { name: 'Search wireless networks' }), 'staff')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(wirelessCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ subnet_id: 'network-1', q: 'staff', page: 1, page_size: 25 }), expect.any(AbortSignal)))
  await user.selectOptions(screen.getByLabelText('Rows per page'), '50')
  await waitFor(() => expect(preferenceClient.save).toHaveBeenCalledWith(workspace, 'network-wireless', expect.objectContaining({ page_size: 50 })))
  await user.click(screen.getByRole('button', { name: 'Office Staff' }))
  expect(await screen.findByText('Headquarters')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Back to wireless networks' }))
  expect(await screen.findByRole('button', { name: 'Office Staff' })).toHaveFocus()
})

it('edits wireless facts without replacing site, VLAN or parent associations', async () => {
  const { updateWireless, user } = setup()
  await user.click(await screen.findByRole('button', { name: 'Office Staff' }))
  await user.click(await screen.findByRole('button', { name: 'Edit wireless network' }))
  await user.clear(screen.getByLabelText('SSID'))
  await user.type(screen.getByLabelText('SSID'), 'Office Guest')
  await user.selectOptions(screen.getByLabelText('Status'), 'disabled')
  await user.selectOptions(screen.getByLabelText('Purpose'), 'guest')
  await user.selectOptions(screen.getByLabelText('Security'), 'owe')
  await user.click(screen.getByLabelText('Hidden SSID'))
  await user.click(screen.getByLabelText('Client isolation'))
  await user.type(screen.getByLabelText('Description'), 'Visitor network')
  await user.click(screen.getByRole('button', { name: 'Save wireless network' }))
  await screen.findByRole('button', { name: 'Edit wireless network' })
  expect(updateWireless).toHaveBeenCalledWith(workspace, 'wifi-1', { ssid: 'Office Guest', status: 'disabled', purpose: 'guest', security: 'owe', hidden: true, client_isolation: false, description: 'Visitor network' })
})

it('retains failed values and cancels a new wireless record after one confirmation', async () => {
  const { user } = setup({ createWireless: vi.fn().mockRejectedValue(new Error('SSID is already recorded.')) })
  await user.click(await screen.findByRole('button', { name: 'New wireless network' }))
  await user.type(screen.getByLabelText('SSID'), 'Office Staff')
  await user.click(screen.getByRole('button', { name: 'Save wireless network' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already recorded')
  await user.click(screen.getByRole('button', { name: 'Back to wireless networks' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('SSID')).toHaveValue('Office Staff')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  expect(await screen.findByRole('button', { name: 'Office Staff' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('creates a wireless record under its parent and accepts the saved detail', async () => {
  const { user, createWireless } = setup()
  await user.click(await screen.findByRole('button', { name: 'New wireless network' }))
  await user.type(screen.getByLabelText('SSID'), 'Office Staff')
  await user.click(screen.getByRole('button', { name: 'Save wireless network' }))
  expect(await screen.findByRole('heading', { name: 'Office Staff' })).toBeInTheDocument()
  expect(createWireless).toHaveBeenCalledWith(workspace, expect.objectContaining({ ssid: 'Office Staff', subnet_id: 'network-1', site_id: null, vlan_id: null }))
})

it('keeps foreign-parent details unavailable and does not offer denied edits', async () => {
  const { user } = setup({ wirelessDetail: vi.fn().mockResolvedValue({ ...record, subnet_id: 'another-parent' }), wirelessCollection: vi.fn().mockResolvedValue({ results: [record], page: 1, page_size: 25, count: 1, has_more: false, can_manage: false }) })
  await user.click(await screen.findByRole('button', { name: 'Office Staff' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable')
  expect(screen.queryByText('Headquarters')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'New wireless network' })).not.toBeInTheDocument()
})
