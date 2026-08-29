import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { RelationshipsClient } from '../relationships/api'
import { SearchResults } from './SearchResults'

describe('SearchResults', () => {
  it('uses permission-filtered entity search and links supported results to working surfaces', async () => {
    const search = vi.fn().mockResolvedValue({ results: [
      { id: 'document-1', display_name: 'Firewall guide', entity_type: 'document', visibility: 'msp_private', workspace_label: 'Example MSP', eligible_link_types: [] },
      { id: 'certificate-1', display_name: 'mail.example.com', entity_type: 'certificate_endpoint', visibility: 'msp_private', workspace_label: 'Example MSP', eligible_link_types: [] },
    ], page: 1, page_size: 15, count: 2, has_more: false })
    const client = { search } as unknown as RelationshipsClient
    render(<MemoryRouter initialEntries={['/search?q=firewall']}><SearchResults workspace={null} client={client} /></MemoryRouter>)

    expect(await screen.findByText('2 authorized records found.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Firewall guide/ })).toHaveAttribute('href', '/documentation?document=document-1')
    expect(screen.getByRole('link', { name: /mail.example.com/ })).toHaveAttribute('href', '/certificates?q=mail.example.com')
    expect(search).toHaveBeenCalledWith({}, 'firewall', undefined, expect.any(AbortSignal))
  })
})
