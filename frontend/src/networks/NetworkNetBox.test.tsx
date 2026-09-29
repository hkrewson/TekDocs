import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { defaultPreferences } from '../collections/preferences'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import type { WorkspaceContext } from '../workspaces/api'
import { NetworkNetBox } from './NetworkNetBox'
import type { NetBoxReference, NetworksClient } from './api'

const workspace: WorkspaceContext = { kind: 'organization', id: 'client-1', name: 'Acme', classifications: ['client'], capabilities: [], organization: null }
const reference: NetBoxReference = { id: 'reference-1', entity_id: 'asset-1', entity_name: 'Core switch', entity_type: 'asset', object_type: 'dcim.device', object_id: 41, observed_fingerprint: '', last_observed_at: null }
const preferences = { load: vi.fn().mockResolvedValue(defaultPreferences(['name', 'type', 'object', 'observation'])), save: vi.fn().mockImplementation((_workspace, _feature, value) => Promise.resolve(value)), reset: vi.fn().mockResolvedValue(defaultPreferences(['name', 'type', 'object', 'observation'])) }

function client(overrides: Partial<NetworksClient> = {}) {
  return {
    netBoxReferenceCollection: vi.fn().mockResolvedValue({ results: [reference], page: 2, page_size: 25, count: 26, has_more: false, can_manage: true }),
    ...overrides,
  } as unknown as NetworksClient
}

describe('NetworkNetBox', () => {
  it('renders bounded synchronization evidence without manual identity controls', async () => {
    const collection = vi.fn().mockResolvedValue({ results: [reference], page: 2, page_size: 25, count: 26, has_more: false, can_manage: true })
    const api = client({ netBoxReferenceCollection: collection })
    render(<ApplicationRouter initialPath="/networks?view=netbox&netbox_page=2"><NetworkNetBox workspace={workspace} client={api} preferenceClient={preferences} /></ApplicationRouter>)

    expect(await screen.findByText('Core switch')).toBeInTheDocument()
    expect(collection).toHaveBeenCalledWith(workspace, expect.objectContaining({ page: 2, page_size: 25 }), expect.any(AbortSignal))
    expect(screen.queryByRole('button', { name: /Link NetBox object/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Unlink/i })).not.toBeInTheDocument()
    expect(screen.getByText('Device')).toBeInTheDocument()
  })

  it('keeps the collection retryable after a failed evidence read', async () => {
    const collection = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValue({ results: [reference], page: 1, page_size: 25, count: 1, has_more: false, can_manage: false })
    const user = userEvent.setup()
    render(<ApplicationRouter initialPath="/networks?view=netbox"><NetworkNetBox workspace={workspace} client={client({ netBoxReferenceCollection: collection })} preferenceClient={preferences} /></ApplicationRouter>)

    await user.click(await screen.findByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByText('Core switch')).toBeInTheDocument())
  })
})
