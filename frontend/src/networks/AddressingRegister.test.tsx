import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { defaultPreferences } from '../collections/preferences'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient } from './api'
import { AddressingRegister } from './AddressingRegister'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
function setup(kind: 'vlans' | 'vrfs', denied = false, failed = false) {
  window.history.replaceState({}, '', `/networks?view=${kind}`)
  const record = { id: 'record-1', name: 'Office', description: 'Documented scope', ...(kind === 'vlans' ? { vlan_id: 20 } : { route_distinguisher: '64512:20' }) }
  const addressingCollection = vi.fn().mockResolvedValue({ results: [record], page: 1, page_size: 25, count: 31, has_more: true, can_manage: !denied })
  const write = failed ? vi.fn().mockRejectedValue(new Error('Record changed.')) : vi.fn().mockResolvedValue(record)
  const client = { addressingCollection, addressingDetail: vi.fn().mockResolvedValue(record), updateVLAN: write, createVLAN: write, updateVRF: write, createVRF: write } as unknown as NetworksClient
  const preferences = defaultPreferences(['name', kind === 'vlans' ? 'vlan_id' : 'route_distinguisher'])
  const preferenceClient = { load: vi.fn().mockResolvedValue(preferences), save: vi.fn().mockResolvedValue(preferences), reset: vi.fn().mockResolvedValue(preferences) }
  render(<ApplicationRouter><AddressingRegister kind={kind} workspace={workspace} client={client} preferenceClient={preferenceClient} /></ApplicationRouter>)
  return { addressingCollection, write, user: userEvent.setup() }
}
for (const kind of ['vlans', 'vrfs'] as const) {
  const label = kind === 'vlans' ? 'VLAN' : 'VRF'
  it(`${label} searches the full collection and opens only one record drawer`, async () => {
    const { user, addressingCollection } = setup(kind)
    await user.type(await screen.findByRole('searchbox'), 'Office')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(addressingCollection).toHaveBeenLastCalledWith(workspace, kind, expect.objectContaining({ q: 'Office', page_size: 25, page: 1 }), expect.any(AbortSignal)))
    await user.click(screen.getByRole('button', { name: 'Office' }))
    const drawer = await screen.findByRole('dialog', { name: 'Office' })
    expect(within(drawer).getByText('Documented scope')).toBeInTheDocument()
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    fireEvent(drawer, new Event('cancel', { cancelable: true }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Office' })).toHaveFocus()
  })
  it(`${label} preserves failed edits through guarded closing`, async () => {
    const { user, write } = setup(kind, false, true)
    await user.click(await screen.findByRole('button', { name: 'Office' }))
    const drawer = await screen.findByRole('dialog', { name: 'Office' })
    await user.click(within(drawer).getByRole('button', { name: `Edit ${label}` }))
    await user.type(within(drawer).getByLabelText('Name'), ' changed')
    await user.click(within(drawer).getByRole('button', { name: `Save ${label}` }))
    expect(await within(drawer).findByRole('alert')).toHaveTextContent('Record changed')
    fireEvent(drawer, new Event('cancel', { cancelable: true }))
    await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
    expect(within(drawer).getByLabelText('Name')).toHaveValue('Office changed')
    expect(write).toHaveBeenCalledTimes(1)
  })
  it(`${label} omits editing actions when denied`, async () => {
    const { user } = setup(kind, true)
    await user.click(await screen.findByRole('button', { name: 'Office' }))
    await screen.findByRole('dialog', { name: 'Office' })
    expect(screen.queryByRole('button', { name: `Edit ${label}` })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: `New ${label}` })).not.toBeInTheDocument()
  })
}
