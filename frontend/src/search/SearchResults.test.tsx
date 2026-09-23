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
  page_size: 25,
  count: 27,
  has_more: true,
  truncated: false,
}

describe('SearchResults', () => {
  it('shows normalized results, facets, excerpts, and direct application targets', async () => {
    const search = vi.fn().mockResolvedValue(firstPage)
    const client = { search } as WorkspaceSearchClient
    render(<MemoryRouter initialEntries={['/search?q=firewall']}><SearchResults workspace={null} client={client} /></MemoryRouter>)

    expect(await screen.findByText('27 records found.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Firewall guide/ })).toHaveAttribute('href', '/documentation?document=document-1')
    expect(screen.getByRole('link', { name: /mail.example.com/ })).toHaveAttribute('href', '/certificates?q=mail.example.com')
    expect(screen.getByText('Allow the management subnet.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Filters$/ }))
    fireEvent.click(screen.getByText('Result type', { exact: true }))
    expect(screen.getByRole('radio', { name: 'Documents (1)' })).toBeInTheDocument()
    expect(search).toHaveBeenCalledWith({}, 'firewall', '', 1, 25, expect.any(AbortSignal))
  })

  it('applies a result type and moves through pages without changing the query', async () => {
    const search = vi.fn().mockResolvedValue(firstPage)
    const client = { search } as WorkspaceSearchClient
    render(<MemoryRouter initialEntries={['/search?q=firewall']}><SearchResults workspace={null} client={client} /></MemoryRouter>)

    await screen.findByText('27 records found.')
    fireEvent.click(screen.getByRole('button', { name: /^Filters$/ }))
    fireEvent.click(screen.getByText('Result type', { exact: true }))
    fireEvent.click(screen.getByRole('radio', { name: 'Documents (1)' }))
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({}, 'firewall', 'document', 1, 25, expect.any(AbortSignal)))
    expect(screen.getByRole('button', { name: /Result type: Document/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({}, 'firewall', 'document', 2, 25, expect.any(AbortSignal)))
    fireEvent.change(screen.getByLabelText('Rows per page'), { target: { value: '50' } })
    await waitFor(() => expect(search).toHaveBeenLastCalledWith({}, 'firewall', 'document', 1, 50, expect.any(AbortSignal)))
  })

  it('does not submit a one-character query to the server', () => {
    const search = vi.fn()
    render(<MemoryRouter initialEntries={['/search?q=x']}><SearchResults workspace={null} client={{ search }} /></MemoryRouter>)

    expect(screen.getByText(/Enter at least two characters/)).toBeInTheDocument()
    expect(search).not.toHaveBeenCalled()
  })

  it('opens provider ticket results outside TekDocs', async () => {
    const search = vi.fn().mockResolvedValue({
      ...firstPage,
      results: [{ id: 'ticket-1042', result_type: 'external_ticket', entity_type: 'external_ticket', title: '#1042 Printer queue unavailable', excerpt: 'In progress · High', workspace_label: 'Acme Dental', target: 'https://support.example.com/tickets?id=1042', score: 900, updated_at: '2026-09-01T12:00:00Z', review_state: null }],
      count: 1,
      has_more: false,
    })
    render(<MemoryRouter initialEntries={['/search?q=1042']}><SearchResults workspace={null} client={{ search }} /></MemoryRouter>)

    expect(await screen.findByRole('link', { name: /#1042 Printer queue unavailable/ })).toHaveAttribute('target', '_blank')
    expect(screen.getByRole('link', { name: /#1042 Printer queue unavailable/ })).toHaveAttribute('href', 'https://support.example.com/tickets?id=1042')
  })

  it('retries a failed search without changing its collection state', async () => {
    const search = vi.fn().mockRejectedValueOnce(new Error('Search is temporarily unavailable.')).mockResolvedValue(firstPage)
    render(<MemoryRouter initialEntries={['/search?q=firewall&page_size=50']}><SearchResults workspace={null} client={{ search }} /></MemoryRouter>)

    expect(await screen.findByText('Search is temporarily unavailable.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('27 records found.')).toBeInTheDocument()
    expect(search).toHaveBeenLastCalledWith({}, 'firewall', '', 1, 50, expect.any(AbortSignal))
  })
})
