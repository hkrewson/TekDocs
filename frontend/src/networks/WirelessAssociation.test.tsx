import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { WirelessAssociation } from './WirelessAssociation'
import type { NetworksClient, WirelessNetwork } from './api'
import type { WorkspaceContext } from '../workspaces/api'
const workspace = { kind: 'msp', id: 'msp', name: 'MSP' } as WorkspaceContext
for (const kind of ['site', 'vlan'] as const) {
  const label = kind === 'site' ? 'site' : 'VLAN'
  it(`searches and saves only the wireless ${label} assignment`, async () => {
    const assignmentChoices = vi.fn().mockResolvedValue({ results: [{ id: 'new', name: 'Choice 31', identifier: '31' }], count: 31, page: 1, page_size: 25, has_more: true })
    const updateWireless = vi.fn().mockResolvedValue({ id: 'wifi' })
    const onCancel = vi.fn(), onSaved = vi.fn()
    render(<ApplicationRouter><WirelessAssociation kind={kind} workspace={workspace} record={{ id: 'wifi', site_id: null, vlan_id: null } as WirelessNetwork} client={{ assignmentChoices, updateWireless } as unknown as NetworksClient} onSaved={onSaved} onCancel={onCancel} /></ApplicationRouter>)
    const user = userEvent.setup()
    await user.type(screen.getByRole('searchbox'), '31')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(assignmentChoices).toHaveBeenLastCalledWith(workspace, kind, '31', 1, expect.any(AbortSignal)))
    await user.selectOptions(await screen.findByRole('combobox'), 'new')
    await user.click(screen.getByRole('button', { name: `Save ${label}` }))
    await waitFor(() => expect(onCancel).toHaveBeenCalled())
    expect(updateWireless).toHaveBeenCalledWith(workspace, 'wifi', { [`${kind}_id`]: 'new' })
    expect(onSaved).toHaveBeenCalled()
  })
  it(`preserves denied ${label} selection through cancel and never retries the mutation`, async () => {
    const assignmentChoices = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValue({ results: [], count: 0, has_more: false, page: 1, page_size: 25 })
    const updateWireless = vi.fn().mockRejectedValue(new Error('Assignment denied'))
    const onCancel = vi.fn()
    render(<ApplicationRouter><WirelessAssociation kind={kind} workspace={workspace} record={{ id: 'wifi', site_id: 'old', vlan_id: 'old', site_name: null, vlan_name: null } as WirelessNetwork} client={{ assignmentChoices, updateWireless } as unknown as NetworksClient} onSaved={vi.fn()} onCancel={onCancel} /></ApplicationRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
    expect(screen.getByText('Current assignment is unavailable.')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText(`No ${label}s match this search.`)
    await user.click(screen.getByRole('button', { name: `Use no ${label}` }))
    await user.click(screen.getByRole('button', { name: `Save ${label}` }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Assignment denied')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(await screen.findByRole('button', { name: 'Keep editing' }))
    expect(onCancel).not.toHaveBeenCalled()
    expect(updateWireless).toHaveBeenCalledTimes(1)
  })
}
