import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { NetworkRelationships } from './NetworkRelationships'

const workspace: WorkspaceContext = {
  kind: 'organization', id: 'client-1', name: 'Acme Dental', classifications: ['client'], capabilities: [], organization: null,
}
const relationship = {
  id: 'link-1',
  link_type: 'connected_to',
  label: 'Connected to',
  direction: 'outgoing',
  related_entity: { id: 'device-2', display_name: 'Distribution switch', entity_type: 'network_device' },
} as never

function client(overrides: Partial<RelationshipsClient> = {}): RelationshipsClient {
  return {
    list: vi.fn().mockResolvedValue([]),
    search: vi.fn().mockResolvedValue({
      results: [
        { id: 'device-1', display_name: 'Core switch', entity_type: 'network_device', eligible_link_types: ['connected_to'] },
        { id: 'device-2', display_name: 'Distribution switch', entity_type: 'network_device', eligible_link_types: ['connected_to', 'related_to'] },
      ],
      page: 1, page_size: 15, count: 2, has_more: false,
    }),
    create: vi.fn().mockResolvedValue(relationship),
    archive: vi.fn().mockResolvedValue(undefined),
    linkTypes: vi.fn().mockResolvedValue([]),
    ...overrides,
  }
}

describe('NetworkRelationships', () => {
  it('creates and archives a typed device relationship', async () => {
    const create = vi.fn().mockResolvedValue(relationship)
    const archive = vi.fn().mockResolvedValue(undefined)
    const api = client({ create, archive })
    const user = userEvent.setup()
    render(<NetworkRelationships workspace={workspace} deviceId="device-1" deviceName="Core switch" canCreate canArchive client={api} />)
    expect(await screen.findByText('No logical relationships have been added.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add relationship' }))
    await user.type(screen.getByLabelText('Find a network device'), 'distribution')
    await user.selectOptions(await screen.findByLabelText('Related device'), 'device-2')
    await user.click(screen.getByRole('button', { name: 'Add relationship' }))
    expect(await screen.findByText('Distribution switch')).toBeInTheDocument()
    expect(create).toHaveBeenCalledWith({ organizationId: 'client-1' }, 'device-1', 'device-2', 'connected_to')
    await user.click(screen.getByRole('button', { name: 'Archive relationship with Distribution switch' }))
    await waitFor(() => expect(archive).toHaveBeenCalledWith({ organizationId: 'client-1' }, 'device-1', 'link-1'))
    expect(screen.getByText('No logical relationships have been added.')).toBeInTheDocument()
  })

  it('keeps failures visible without exposing unavailable actions', async () => {
    render(<NetworkRelationships
      workspace={{ ...workspace, kind: 'msp' }}
      deviceId="device-1"
      deviceName="Core switch"
      canCreate={false}
      canArchive={false}
      client={client({ list: vi.fn().mockRejectedValue(new Error('Relationships unavailable.')) })}
    />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Relationships unavailable.')
    expect(screen.queryByRole('button', { name: 'Add relationship' })).not.toBeInTheDocument()
  })
})
