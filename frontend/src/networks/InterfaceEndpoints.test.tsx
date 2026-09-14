import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { AddressQuery, NetworksClient } from './api'
import { InterfaceEndpoints } from './InterfaceEndpoints'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup(kind: 'ip' | 'mac', { failed = false, denied = false, foreign = false } = {}) {
  window.history.replaceState({}, '', `/networks?devices=device-1&interface=port-1&interface_view=${kind}`)
  const record = { id: 'endpoint-1', address: kind === 'ip' ? '192.0.2.1' : '02:00:00:00:00:01', interface_id: foreign ? 'port-2' : 'port-1', description: 'Cable destination', ...(kind === 'ip' ? { status: 'active', dns_name: '', subnet_cidr: '192.0.2.0/24' } : {}) }
  const collection = vi.fn().mockImplementation((_workspace: WorkspaceContext, query: AddressQuery) => Promise.resolve({ results: [{ ...record, interface_id: query.unassigned ? null : record.interface_id }], count: 31, page: query.page, page_size: 25, has_more: true, can_manage: !denied }))
  const update = vi.fn().mockImplementation((_workspace, _id, values) => Promise.resolve({ ...record, ...values }))
  const assign = failed ? vi.fn().mockRejectedValue(new Error('The assignment changed. Reload before trying again.')) : vi.fn().mockImplementation((_workspace: WorkspaceContext, _kind: string, _id: string, parent: string | null) => Promise.resolve({ ...record, interface_id: parent }))
  const client = { addressCollection: collection, macCollection: collection, addressDetail: vi.fn().mockResolvedValue(record), macDetail: vi.fn().mockResolvedValue(record), updateIPAddress: update, updateMACAddress: update, assignEndpoint: assign } as unknown as NetworksClient
  const preferences = defaultPreferences(kind === 'ip' ? ['name', 'status', 'dns_name'] : ['name'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  render(<ApplicationRouter><InterfaceEndpoints kind={kind} workspace={workspace} interfaceId="port-1" client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { user: userEvent.setup(), collection, update, assign, address: record.address }
}
for (const kind of ['ip', 'mac'] as const) {
  it(`${kind} scopes collection and edits without resending assignment fields`, async () => {
    const { user, collection, update, address } = setup(kind)
    await user.click(await screen.findByRole('button', { name: address }))
    await waitFor(() => expect(collection).toHaveBeenCalledWith(workspace, expect.objectContaining({ interface_id: 'port-1', page_size: 25 }), expect.any(AbortSignal)))
    await user.click(await screen.findByRole('button', { name: 'Edit address details' }))
    await user.type(screen.getByRole('textbox', { name: 'Description' }), ' updated')
    await user.click(screen.getByRole('button', { name: 'Save address details' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith(workspace, 'endpoint-1', { address, description: 'Cable destination updated', ...(kind === 'ip' ? { status: 'active', dns_name: '' } : {}) }))
    await user.click(await screen.findByRole('button', { name: kind === 'ip' ? 'Back to IP addresses' : 'Back to MAC addresses' }))
    await waitFor(() => expect(screen.getByRole('button', { name: address })).toHaveFocus())
  })
  it(`${kind} confirms removal and submits the expected current interface`, async () => {
    const { user, assign, address } = setup(kind)
    await user.click(await screen.findByRole('button', { name: address }))
    await user.click(await screen.findByRole('button', { name: 'Remove from interface' }))
    expect(assign).not.toHaveBeenCalled()
    expect(screen.getByText(/record and its history are retained/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Confirm removal' }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith(workspace, kind, 'endpoint-1', null, 'port-1'))
    expect(await screen.findByRole('searchbox', { name: kind === 'ip' ? 'Search IP addresses' : 'Search MAC addresses' })).toBeVisible()
  })
  it(`${kind} retains a stale assignment choice through guarded return without retry`, async () => {
    const { user, collection, assign } = setup(kind, { failed: true })
    await user.click(await screen.findByRole('button', { name: kind === 'ip' ? 'Assign existing IP address' : 'Assign existing MAC address' }))
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Available address records' }), 'endpoint-1')
    expect(collection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ unassigned: 'true', page_size: 25 }), expect.any(AbortSignal))
    await user.click(screen.getByRole('button', { name: 'Confirm assignment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('assignment changed')
    await user.click(screen.getByRole('button', { name: kind === 'ip' ? 'Back to IP addresses' : 'Back to MAC addresses' }))
    await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
    expect(screen.getByRole('combobox', { name: 'Available address records' })).toHaveValue('endpoint-1')
    expect(assign).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith(workspace, kind, 'endpoint-1', 'port-1', null)
  })
}
it('denies foreign interface children and hides changes from read-only users', async () => {
  const { user, address } = setup('ip', { denied: true, foreign: true })
  await user.click(await screen.findByRole('button', { name: address }))
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable')
  expect(screen.queryByRole('button', { name: 'Edit address details' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Assign existing IP address' })).not.toBeInTheDocument()
})
