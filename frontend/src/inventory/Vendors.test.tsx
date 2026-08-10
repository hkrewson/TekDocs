import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Vendors } from './Vendors'
import type { InventoryClient } from './api'

describe('Vendors', () => {
  it('shows suppliers derived from client assets', async () => {
    const client = {
      listVendors: vi.fn().mockResolvedValue({ results: [{ id: 'supplier-1', name: 'Northwind', legal_name: 'Northwind, Inc.', website: 'https://example.invalid', classifications: ['manufacturer'], asset_count: 2 }], count: 1 }),
    } as unknown as InventoryClient
    render(<Vendors workspace={{ id: 'client-1' } as never} client={client} />)
    expect(await screen.findByText('Northwind')).toBeInTheDocument()
    expect(screen.getByText('2 assets')).toBeInTheDocument()
  })
})
