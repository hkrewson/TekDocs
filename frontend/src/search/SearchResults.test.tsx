import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { WorkspaceSearchClient, WorkspaceSearchResult } from './api'
import { SearchResults } from './SearchResults'

const firstPage: WorkspaceSearchResult = {
  results: [
    { id: 'document-1', result_type: 'document', entity_type: 'document', title: 'Firewall guide', excerpt: 'Allow the management subnet.', workspace_label: 'Example MSP', target: '/documentation?document=document-1', score: 1_000, updated_at: '2026-08-31T12:00:00Z', review_state: 'approved' },
    { id: 'certificate-1', result_type: 'certificate', entity_type: 'certificate_endpoint', title: 'mail.example.com', excerpt: 'Hostname: mail.example.com', workspace_label: 'Example MSP', target: '/certificates?q=mail.example.com', score: 850, updated_at: '2026-08-30T12:00:00Z', review_state: null },
  ],
  facets: [{ value: 'document', label: 'Documents', count: 1 }, { value: 'certificate', label: 'Certificates', count: 1 }],
  page: 1,
  page_size: 15,
  count: 17,
  has_more: true,
  truncated: false,
}

describe('SearchResults', () => {
  it('shows normalized results, facets, excerpts, and direct application targets', async () => {
    const search = vi.fn().mockResolvedValue(firstPage)
    const client = { search } as WorkspaceSearchClient
    render(<MemoryRouter initialEntries={['/search?q=firewall']}><SearchResults workspace={null} client={client} /></MemoryRouter>)

    expect(await screen.findByText('17 authorized records found.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Firewall guide/ })).toHaveAttribute('href', '/documentation?document=document-1')
    expect(screen.getByRole('link', { name: /mail.example.com/ })).toHaveAttribute('href', '/certificates?q=mail.example.com')
    expect(screen.getByText('Allow the management subnet.')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Documents (1)' })).toBeInTheDocument()
    expect(search).toHaveBeenCalledWith({}, 'firewall', '', 1, expect.any(AbortSignal))
  })

  it('applies a result type and moves through pages without changing the query', async () => {
    const search = vi.fn().mockResolvedValue(firstPage)
    const client = { search } as WorkspaceSearchClient
    render(<MemoryRouter initialEntries={['/search?q=firewall']}><SearchResults workspace={null} client={client} /></MemoryRouter>)

    await screen.findByText('17 authorized records found.')
    fireEvent.change(screen.getByLabelText('Result type'), { target: { value: 'document' } })
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({}, 'firewall', 'document', 1, expect.any(AbortSignal)))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({}, 'firewall', 'document', 2, expect.any(AbortSignal)))
  })

  it('does not submit a one-character query to the server', () => {
    const search = vi.fn()
    render(<MemoryRouter initialEntries={['/search?q=x']}><SearchResults workspace={null} client={{ search }} /></MemoryRouter>)

    expect(screen.getByText(/Enter at least two characters/)).toBeInTheDocument()
    expect(search).not.toHaveBeenCalled()
  })
})
