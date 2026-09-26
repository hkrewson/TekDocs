import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { defaultPreferences } from '../collections/preferences'
import { ApplicationRouter } from '../navigation/ApplicationRouter'
import type { WorkspaceContext } from '../workspaces/api'
import { NetworkNetBox } from './NetworkNetBox'
import type { NetBoxReference, NetworksClient } from './api'

const workspace: WorkspaceContext = { kind: 'organization', id: 'client-1', name: 'Acme', classifications: ['client'], capabilities: [], organization: null }
const reference: NetBoxReference = { id: 'reference-1', entity_id: 'rack-1', entity_name: 'Core rack', entity_type: 'network_rack', object_type: 'dcim.rack', object_id: 41, observed_fingerprint: '', last_observed_at: null }
const preferences = { load: vi.fn().mockResolvedValue(defaultPreferences(['name', 'type', 'object', 'observation'])), save: vi.fn().mockImplementation((_workspace, _feature, value) => Promise.resolve(value)), reset: vi.fn().mockResolvedValue(defaultPreferences(['name', 'type', 'object', 'observation'])) }

function client(overrides: Partial<NetworksClient> = {}) {
  return {
    netBoxReferenceCollection: vi.fn().mockResolvedValue({ results: [reference], page: 2, page_size: 25, count: 26, has_more: false, can_manage: true }),
    netBoxChoiceCollection: vi.fn().mockResolvedValue({ results: [{ id: 'rack-2', name: 'Edge rack', entity_type: 'network_rack', object_type: 'dcim.rack', linked: false }], selected: null, page: 1, page_size: 25, count: 1, has_more: false, can_manage: true }),
    setNetBoxReference: vi.fn().mockResolvedValue(reference), removeNetBoxReference: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as NetworksClient
}

describe('NetworkNetBox', () => {
  it('renders a bounded register and preserves page context while opening and closing the drawer', async () => {
    const collection = vi.fn().mockResolvedValue({ results: [reference], page: 2, page_size: 25, count: 26, has_more: false, can_manage: true })
    const api = client({ netBoxReferenceCollection: collection })
    const user = userEvent.setup()
    render(<ApplicationRouter initialPath="/networks?view=netbox&netbox_page=2"><NetworkNetBox workspace={workspace} client={api} preferenceClient={preferences} /></ApplicationRouter>)
    expect(await screen.findByText('Core rack')).toBeInTheDocument()
    expect(collection).toHaveBeenCalledWith(workspace, expect.objectContaining({ page: 2, page_size: 25 }), expect.any(AbortSignal))
    await user.click(screen.getByRole('button', { name: 'Link NetBox object' }))
    expect(await screen.findByRole('dialog', { name: 'Link NetBox object' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(collection).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ page: 2 }), expect.any(AbortSignal))
  })

  it('keeps link values and reports a failed mutation', async () => {
    const api = client({ setNetBoxReference: vi.fn().mockRejectedValue(new Error('Identity already linked.')) })
    const user = userEvent.setup()
    render(<ApplicationRouter initialPath="/networks?view=netbox&netbox_link=true"><NetworkNetBox workspace={workspace} client={api} preferenceClient={preferences} /></ApplicationRouter>)
    await user.click(await screen.findByRole('radio', { name: /Edge rack/ }))
    await user.type(screen.getByLabelText('NetBox ID'), '77')
    await user.click(screen.getByRole('button', { name: 'Link identity' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Identity already linked.')
    expect(screen.getByLabelText('NetBox ID')).toHaveValue(77)
  })
})
