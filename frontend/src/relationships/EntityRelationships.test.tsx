import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { EntityRelationships } from './EntityRelationships'
import type { EntityReference, EntityRelationship, RelationshipsClient } from './api'

const organizationId = '00000000-0000-4000-8000-000000000010'
const vendorId = '00000000-0000-4000-8000-000000000020'
const vendor: EntityReference = {
  id: vendorId,
  display_name: 'Northwind Supply',
  entity_type: 'organization' as const,
  visibility: 'msp_private',
  workspace_label: 'Vendor organization',
  eligible_link_types: ['related_to', 'supplied_by'],
}
const relationship: EntityRelationship = {
  id: '00000000-0000-4000-8000-000000000030',
  link_type: 'supplied_by',
  label: 'Supplied by',
  direction: 'outgoing',
  source_id: organizationId,
  target_id: vendorId,
  related_entity: vendor,
  created_at: '2026-08-08T12:00:00Z',
}

function relationshipsClient(overrides: Partial<RelationshipsClient> = {}): RelationshipsClient {
  return {
    linkTypes: vi.fn().mockResolvedValue([
      { value: 'related_to', forward_label: 'Related to', inverse_label: 'Related to', symmetric: true, target_types: ['organization'] },
      { value: 'supplied_by', forward_label: 'Supplied by', inverse_label: 'Supplies', symmetric: false, target_types: ['organization'] },
    ]),
    search: vi.fn().mockResolvedValue({ results: [vendor], page: 1, page_size: 15, count: 1, has_more: false }),
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn().mockResolvedValue(relationship),
    archive: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('EntityRelationships', () => {
  it('shows directional links and permission-aware backlinks', async () => {
    const incoming = { ...relationship, id: '00000000-0000-4000-8000-000000000031', direction: 'incoming' as const, label: 'Supplies' }
    render(<MemoryRouter><EntityRelationships organizationId={organizationId} organizationName="Acme Dental" client={relationshipsClient({ list: vi.fn().mockResolvedValue([relationship, incoming]) })} /></MemoryRouter>)

    expect(await screen.findByText('Supplied by')).toBeInTheDocument()
    expect(screen.getByText('Supplies')).toBeInTheDocument()
    expect(screen.getByText(/Outgoing · MSP private/)).toBeInTheDocument()
    expect(screen.getByText(/Backlink · MSP private/)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Northwind Supply' })[0]).toHaveAttribute('href', `/workspaces/organizations/${vendorId}/overview`)
  })

  it('searches, creates, and archives a typed relationship in the active workspace', async () => {
    const user = userEvent.setup()
    const search = vi.fn().mockResolvedValue({ results: [vendor], page: 1, page_size: 15, count: 1, has_more: false })
    const create = vi.fn().mockResolvedValue(relationship)
    const archive = vi.fn().mockResolvedValue(undefined)
    const client = relationshipsClient({ search, create, archive })
    render(<MemoryRouter><EntityRelationships organizationId={organizationId} organizationName="Acme Dental" client={client} /></MemoryRouter>)
    await screen.findByText('No relationships have been added.')

    await user.click(screen.getByRole('button', { name: 'Add relationship' }))
    await user.selectOptions(screen.getByLabelText('Relationship type'), 'supplied_by')
    await user.type(screen.getByRole('searchbox', { name: 'Related organization' }), 'Northwind')
    await user.click(await screen.findByRole('radio', { name: /Northwind Supply/ }))
    await user.click(screen.getByRole('button', { name: 'Add supplied by' }))

    expect(search).toHaveBeenLastCalledWith({ organizationId }, 'Northwind', 'organization', expect.any(AbortSignal))
    expect(create).toHaveBeenCalledWith({ organizationId }, organizationId, vendorId, 'supplied_by')
    expect(await screen.findByText('Relationship added.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Archive relationship with Northwind Supply/ }))
    const row = screen.getByRole('listitem')
    await user.click(within(row).getByRole('button', { name: 'Confirm archive' }))
    expect(archive).toHaveBeenCalledWith({ organizationId }, organizationId, relationship.id)
    expect(await screen.findByText('Relationship archived.')).toBeInTheDocument()
  })

  it('keeps the form open and reports an authorization denial', async () => {
    const user = userEvent.setup()
    const client = relationshipsClient({ create: vi.fn().mockRejectedValue(new Error('Your account is not authorized to manage relationships in this workspace.')) })
    render(<MemoryRouter><EntityRelationships organizationId={organizationId} organizationName="Acme Dental" client={client} /></MemoryRouter>)
    await screen.findByText('No relationships have been added.')

    await user.click(screen.getByRole('button', { name: 'Add relationship' }))
    await user.click(await screen.findByRole('radio', { name: /Northwind Supply/ }))
    await user.click(screen.getByRole('button', { name: 'Add related to' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('not authorized')
    expect(screen.getByRole('searchbox', { name: 'Related organization' })).toBeInTheDocument()
  })
})
