import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { RelatedNetworks } from './RelatedNetworks'
import type { NetworksClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
for (const kind of ['vlans', 'vrfs'] as const) {
  it(`${kind} uses exact scope, preserves parent URL, and resets paging on search`, async () => {
    window.history.replaceState({}, '', `/networks?view=${kind}&${kind}=parent&${kind}_section=networks&${kind}_networks_page=2`)
    const collection = vi.fn().mockResolvedValue({ results: [{ id: 'child', name: 'Guest', cidr: '192.0.2.0/24' }], count: 31, page: 2, page_size: 25, has_more: false })
    render(<ApplicationRouter><RelatedNetworks kind={kind} recordId="parent" workspace={workspace} client={{ collection } as unknown as NetworksClient} /></ApplicationRouter>)
    const link = await screen.findByRole('link', { name: 'Guest' })
    const target = new URL(link.getAttribute('href')!, 'http://localhost')
    expect(target.searchParams.get('record')).toBe('child')
    expect(target.searchParams.has('view')).toBe(false)
    expect(target.searchParams.get(`${kind}_section`)).toBe('networks')
    expect(collection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ [kind === 'vlans' ? 'vlan_id' : 'vrf_id']: 'parent', page: 2 }), expect.any(AbortSignal))
    const user = userEvent.setup()
    await user.type(screen.getByRole('searchbox'), 'Guest')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(collection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: 'Guest', page: 1 }), expect.any(AbortSignal)))
  })
}
it('retries failed related lookup and shows an empty result without losing search', async () => {
  window.history.replaceState({}, '', '/networks?view=vrfs&vrfs=p&vrfs_networks_q=Missing')
  const collection = vi.fn().mockRejectedValueOnce(new Error('Denied')).mockResolvedValue({ results: [], count: 0, page: 1, page_size: 25, has_more: false })
  render(<ApplicationRouter><RelatedNetworks kind="vrfs" recordId="p" workspace={workspace} client={{ collection } as unknown as NetworksClient} /></ApplicationRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
  await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('No associated networks match this search.')).toBeInTheDocument()
  expect(screen.getByRole('searchbox')).toHaveValue('Missing')
})
