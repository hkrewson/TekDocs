import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { WorkspaceClient } from '../workspaces/api'
import { ProductCatalogs } from './ProductCatalogs'

describe('ProductCatalogs', () => {
  it('deduplicates suppliers and links directly to their product catalogs', async () => {
    const supplier = { id: 'supplier-1', name: 'Acme Supply', classifications: ['vendor', 'manufacturer'] as const, capabilities: ['overview', 'products'] as const }
    const searchOrganizations = vi.fn().mockResolvedValue({ results: [supplier], page: 1, page_size: 15, has_more: false })
    const client = { searchOrganizations } as unknown as WorkspaceClient
    render(<MemoryRouter><ProductCatalogs client={client} /></MemoryRouter>)

    expect(await screen.findByText('Acme Supply')).toBeInTheDocument()
    expect(screen.getAllByText('Acme Supply')).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Open catalog' })).toHaveAttribute('href', '/workspaces/organizations/supplier-1/products')
    expect(searchOrganizations).toHaveBeenCalledTimes(2)
  })
})
