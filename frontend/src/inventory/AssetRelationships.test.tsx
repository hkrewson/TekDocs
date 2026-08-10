import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RelationshipsClient } from '../relationships/api'
import { AssetRelationships } from './AssetRelationships'

const workspace = { kind: 'organization', id: 'client-1', name: 'Contoso', classifications: ['client'] } as never

describe('AssetRelationships', () => {
  it('loads, creates, and archives exact-workspace asset links', async () => {
    const relationship = {
      id: 'link-1', link_type: 'depends_on', label: 'Depends on', direction: 'outgoing', source_id: 'asset-1', target_id: 'asset-2',
      related_entity: { id: 'asset-2', display_name: 'Core firewall', entity_type: 'client_asset', visibility: 'msp_private', workspace_label: 'Contoso', eligible_link_types: ['related_to', 'depends_on', 'references'] },
      created_at: '2026-08-10T12:00:00Z',
    } as const
    const create = vi.fn().mockResolvedValue(relationship)
    const archive = vi.fn().mockResolvedValue(undefined)
    const client: RelationshipsClient = {
      linkTypes: vi.fn(),
      list: vi.fn().mockResolvedValue([]),
      search: vi.fn().mockResolvedValue({ results: [relationship.related_entity], page: 1, page_size: 15, count: 1, has_more: false }),
      create,
      archive,
    }
    const user = userEvent.setup()
    render(<AssetRelationships workspace={workspace} assetId="asset-1" assetName="Core switch" canCreate canArchive client={client} />)
    expect(await screen.findByText('No asset relationships have been added.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add relationship' }))
    await user.type(screen.getByLabelText('Find an asset'), 'firewall')
    await waitFor(() => expect(screen.getByRole('option', { name: 'Core firewall' })).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText('Relationship'), 'depends_on')
    await user.selectOptions(screen.getByLabelText('Related asset'), 'asset-2')
    await user.click(screen.getByRole('button', { name: 'Add relationship' }))
    expect(await screen.findByText(/Core firewall/)).toBeInTheDocument()
    expect(create).toHaveBeenCalledWith({ organizationId: 'client-1' }, 'asset-1', 'asset-2', 'depends_on')
    await user.click(screen.getByRole('button', { name: 'Archive relationship with Core firewall' }))
    await waitFor(() => expect(archive).toHaveBeenCalledWith({ organizationId: 'client-1' }, 'asset-1', 'link-1'))
  })
})
