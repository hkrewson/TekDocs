import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { NetworkAddresses } from './NetworkAddresses'

const workspace: WorkspaceContext = { kind: 'organization', id: 'client-1', name: 'Client', classifications: ['client'], capabilities: [], organization: null }
const record = { id: 'ip-1', address: '192.0.2.10', subnet_id: 'network-1', status: 'active', dns_name: 'host.example.invalid', description: '', hardware_asset_name: 'Switch', interface_name: 'eth0' }
function setup(overrides: Partial<NetworksClient> = {}) {
  const preferences = defaultPreferences(['name', 'status', 'dns_name'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  const addressCollection = vi.fn().mockResolvedValue({ results: [record], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true })
  const updateIPAddress = vi.fn().mockResolvedValue({ ...record, status: 'reserved' })
  const client = {
    addressCollection,
    addressDetail: vi.fn().mockResolvedValue(record), createIPAddress: vi.fn().mockResolvedValue(record),
    updateIPAddress, ...overrides,
  } as unknown as NetworksClient
  render(<ApplicationRouter><NetworkAddresses workspace={workspace} subnetId="network-1" client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { addressCollection, updateIPAddress, preferenceClient, user: userEvent.setup() }
}
beforeEach(() => { window.history.replaceState({}, '', '/networks?section=addresses') })

it('loads a bounded parent collection and selected facts only on demand', async () => {
  const { addressCollection, user, preferenceClient } = setup()
  await user.click(await screen.findByRole('button', { name: '192.0.2.10' }))
  expect(addressCollection).toHaveBeenCalledWith(workspace, expect.objectContaining({ subnet_id: 'network-1', page: 1, page_size: 25 }), expect.any(AbortSignal))
  expect(await screen.findByText('Switch')).toBeInTheDocument()
  expect(screen.getByText('eth0')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Back to addresses' }))
  await user.type(screen.getByRole('searchbox', { name: 'Search addresses' }), 'host')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(addressCollection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: 'host', page: 1 }), expect.any(AbortSignal)))
  await user.selectOptions(screen.getByLabelText('Rows per page'), '50')
  await waitFor(() => expect(preferenceClient.save).toHaveBeenCalledWith(workspace, 'network-addresses', expect.objectContaining({ page_size: 50 })))
})

it('saves ordinary edits without overwriting assignment keys', async () => {
  const { updateIPAddress, user } = setup()
  await user.click(await screen.findByRole('button', { name: '192.0.2.10' }))
  await user.click(await screen.findByRole('button', { name: 'Edit address' }))
  await user.selectOptions(screen.getByLabelText('Status'), 'reserved')
  await user.clear(screen.getByLabelText('DNS name'))
  await user.type(screen.getByLabelText('DNS name'), 'updated.example.invalid')
  await user.type(screen.getByLabelText('Description'), 'Operational note')
  await user.click(screen.getByRole('button', { name: 'Save address' }))
  await screen.findByRole('button', { name: 'Edit address' })
  expect(updateIPAddress).toHaveBeenCalledWith(workspace, 'ip-1', { address: '192.0.2.10', status: 'reserved', dns_name: 'updated.example.invalid', description: 'Operational note' })
})

it('retains failed creation values and guards returning to the collection', async () => {
  const { user } = setup({ createIPAddress: vi.fn().mockRejectedValue(new Error('Address is already reserved.')) })
  await user.click(await screen.findByRole('button', { name: 'New IP address' }))
  await user.type(screen.getByLabelText('IP address'), '192.0.2.10')
  await user.click(screen.getByRole('button', { name: 'Save address' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already reserved')
  await user.click(screen.getByRole('button', { name: 'Back to addresses' }))
  await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('IP address')).toHaveValue('192.0.2.10')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(await screen.findByRole('button', { name: 'Discard changes' }))
  expect(await screen.findByRole('button', { name: '192.0.2.10' })).toBeInTheDocument()
})

it('reports unavailable details and retries failed collections', async () => {
  const collection = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValue({ results: [record], count: 1, page: 1, page_size: 25, has_more: false, can_manage: false })
  const { user } = setup({ addressCollection: collection, addressDetail: vi.fn().mockResolvedValue({ ...record, subnet_id: 'another-network' }) })
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await user.click(await screen.findByRole('button', { name: '192.0.2.10' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable')
  expect(screen.queryByText('Switch')).not.toBeInTheDocument()
})
