import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { DocumentRelationshipRail } from './DocumentRelationshipRail'
import type { RelationshipsClient } from '../relationships/api'

it('searches authorized records and adds an exact document relationship', async () => {
  const user = userEvent.setup()
  const related = { id: 'asset-1', display_name: 'Core switch', entity_type: 'client_asset', visibility: 'client_visible' as const, workspace_label: 'Acme', eligible_link_types: ['references' as const] }
  const relationship = { id: 'link-1', link_type: 'references' as const, label: 'References', direction: 'outgoing' as const, source_id: 'doc-1', target_id: 'asset-1', related_entity: related, created_at: '2026-08-15T00:00:00Z' }
  const create = vi.fn().mockResolvedValue(relationship)
  const client: RelationshipsClient = {
    linkTypes: vi.fn().mockResolvedValue([]),
    search: vi.fn().mockResolvedValue({ results: [related], page: 1, page_size: 15, count: 1, has_more: false }),
    list: vi.fn().mockResolvedValue([]),
    create,
    archive: vi.fn().mockResolvedValue(undefined),
  }
  render(<DocumentRelationshipRail scope={{ organizationId: 'org-1' }} documentId="doc-1" client={client} />)
  await screen.findByText('No related records.')
  await user.type(screen.getByRole('searchbox', { name: 'Find a record' }), 'Core')
  await user.click(await screen.findByRole('button', { name: /Core switch/ }))
  await waitFor(() => expect(create).toHaveBeenCalledWith({ organizationId: 'org-1' }, 'doc-1', 'asset-1', 'references'))
  expect(screen.getByText('Core switch')).toBeVisible()
})
