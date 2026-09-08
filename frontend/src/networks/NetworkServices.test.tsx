import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { NetworkServices } from './NetworkServices'
import type { NetworksClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'], capabilities: [], organization: null,
}

const emptyResult = { results: [], page: 1, page_size: 100, count: 0, has_more: false, can_manage: true }

function client(overrides: Partial<NetworksClient> = {}): NetworksClient {
  return {
    listWireless: vi.fn().mockResolvedValue(emptyResult),
    listDNSZones: vi.fn().mockResolvedValue(emptyResult),
    listDNSRecords: vi.fn().mockResolvedValue(emptyResult),
    listVLANs: vi.fn().mockResolvedValue(emptyResult),
    listSubnets: vi.fn().mockResolvedValue(emptyResult),
    listIPAddresses: vi.fn().mockResolvedValue(emptyResult),
    choices: vi.fn().mockResolvedValue({ sites: [], locations: [], racks: [], hardware_assets: [] }),
    ...overrides,
  } as unknown as NetworksClient
}

describe('NetworkServices', () => {
  it('replaces one DNS editor with another and focuses its first entry field', async () => {
    const user = userEvent.setup()
    const api = client({ listDNSZones: vi.fn().mockResolvedValue({ ...emptyResult, results: [{ id: 'zone-1', name: 'example.com', description: '', record_count: 0 }] }) })
    render(<NetworkServices workspace={workspace} client={api} kind="dns" query="" />)

    await user.click(await screen.findByRole('button', { name: 'Add zone' }))
    expect(screen.getByRole('heading', { name: 'Add DNS zone' })).toBeInTheDocument()
    expect(screen.getByLabelText('Canonical zone name')).toHaveFocus()

    await user.click(screen.getByRole('button', { name: 'Add record' }))
    expect(screen.queryByRole('heading', { name: 'Add DNS zone' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Add DNS record' })).toBeInTheDocument()
    expect(screen.getByLabelText('Owner name')).toHaveFocus()
  })

  it('reports an initial load failure instead of remaining in a loading state', async () => {
    render(<NetworkServices workspace={workspace} client={client({ listWireless: vi.fn().mockRejectedValue(new Error('Network services unavailable.')) })} kind="wireless" query="" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Network services unavailable.')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
