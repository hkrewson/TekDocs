import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Vendors } from './Vendors'
import type { DerivedVendor, InventoryClient } from './api'

const supplier: DerivedVendor = { id: 'supplier-1', name: 'Northwind', legal_name: 'Northwind, Inc.', website: 'https://example.invalid', classifications: ['manufacturer'], asset_count: 2 }
const workspace = { kind: 'organization', id: 'client-1', name: 'Contoso' } as never

function Location() {
  return <output data-testid="location">{useLocation().search}</output>
}

function client(overrides: Partial<InventoryClient> = {}) {
  return {
    listVendors: vi.fn().mockResolvedValue({ results: [supplier], page: 1, page_size: 25, count: 1, has_more: false }),
    retrieveVendor: vi.fn().mockResolvedValue(supplier),
    ...overrides,
  } as unknown as InventoryClient
}

describe('Vendors', () => {
  it('opens a complete supplier record with workspace and catalog links', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Vendors workspace={workspace} client={client()} /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: 'Northwind' }))
    expect(await screen.findByRole('heading', { name: 'Northwind' })).toHaveFocus()
    const drawer = within(screen.getByRole('dialog'))
    expect(drawer.getByText('Northwind, Inc.')).toBeInTheDocument()
    expect(drawer.getByText('2 assets')).toBeInTheDocument()
    expect(drawer.getByRole('link', { name: 'Open vendor workspace' })).toHaveAttribute('href', '/workspaces/organizations/supplier-1/overview')
    expect(drawer.getByRole('link', { name: 'Open product catalog' })).toHaveAttribute('href', '/workspaces/organizations/supplier-1/products')
  })

  it('restores query state and loads a supplier outside the current page', async () => {
    const listVendors = vi.fn().mockResolvedValue({ results: [], page: 2, page_size: 25, count: 30, has_more: false })
    const retrieveVendor = vi.fn().mockResolvedValue(supplier)
    const api = client({ listVendors, retrieveVendor })
    render(<MemoryRouter initialEntries={['/workspaces/organizations/client-1/vendors?q=north&vendor_order=-asset_count&vendor_page=2&vendor=supplier-1']}><Vendors workspace={workspace} client={api} /><Location /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Northwind' })).toBeInTheDocument()
    await waitFor(() => expect(listVendors).toHaveBeenCalledWith(workspace, { q: 'north', ordering: '-asset_count', page: 2, page_size: 25 }, expect.any(AbortSignal)))
    expect(retrieveVendor).toHaveBeenCalledWith(workspace, 'supplier-1', expect.any(AbortSignal))
    expect(screen.getByTestId('location')).toHaveTextContent('vendor_page=2')
  })

  it('searches, sorts by asset count, and retains those controls in the URL', async () => {
    const user = userEvent.setup()
    const listVendors = vi.fn().mockResolvedValue({ results: [supplier], page: 1, page_size: 25, count: 1, has_more: false })
    const api = client({ listVendors })
    render(<MemoryRouter><Vendors workspace={workspace} client={api} /><Location /></MemoryRouter>)
    await screen.findByRole('button', { name: 'Northwind' })
    await user.type(screen.getByRole('searchbox', { name: 'Search suppliers' }), 'wind')
    await user.click(screen.getByRole('button', { name: 'Assets' }))
    await waitFor(() => expect(listVendors).toHaveBeenLastCalledWith(workspace, expect.objectContaining({ q: 'wind', ordering: 'asset_count' }), expect.any(AbortSignal)))
    expect(screen.getByTestId('location')).toHaveTextContent('q=wind')
    expect(screen.getByTestId('location')).toHaveTextContent('vendor_order=asset_count')
  })
})
