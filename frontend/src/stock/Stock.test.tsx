import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Stock } from './Stock'
import type { StockClient, StockItem } from './api'

const item: StockItem = {
  id: 'stock-1', name: 'Cat6 bulk cable', description: 'Riser-rated solid copper cable', vendor_id: 'vendor-1',
  vendor_name: 'Cable Supplier', vendor_part_number: 'PART-1000', unit: 'foot', quantity_on_hand: '1000.000',
  reorder_level: '150.000', currency: 'USD', cost_per_unit: '0.145430', client_price_per_unit: '0.30',
  purchase_quantity: '1000.000', purchase_price: '107.99', order_total: '145.43', order_number: 'ORDER-1001',
  order_url: 'https://orders.example.invalid/ORDER-1001', ordered_on: '2026-08-01', tracking_number: 'TRACK-1001',
  tracking_url: 'https://tracking.example.invalid/TRACK-1001', movements: [{ id: 'move-1', movement_type: 'received', quantity_change: '1000.000', quantity_after: '1000.000', client_id: null, client_name: null, note: 'Initial stock', occurred_at: '2026-08-01T12:00:00Z', recorded_at: '2026-08-01T12:00:00Z', actor: 'Owner' }],
  created_at: '2026-08-01T12:00:00Z', updated_at: '2026-08-01T12:00:00Z',
}

function stockClient(overrides: Partial<StockClient> = {}): StockClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [item], can_manage: true, vendors: [{ id: 'vendor-1', name: 'Cable Supplier' }], clients: [{ id: 'client-1', name: 'Client Site' }] }),
    create: vi.fn().mockResolvedValue(item), update: vi.fn().mockResolvedValue(item), archive: vi.fn().mockResolvedValue(undefined), move: vi.fn().mockResolvedValue({ ...item, quantity_on_hand: '875.000' }), ...overrides,
  }
}

describe('Stock', () => {
  it('shows exact stock and supplier provenance', async () => {
    render(<Stock client={stockClient()} />)
    expect(await screen.findByRole('heading', { name: 'Stock' })).toBeInTheDocument()
    expect(screen.getAllByText('1000.000 foot').length).toBeGreaterThan(0)
    expect(screen.getAllByText('USD 0.145430').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /ORDER-1001/ })).toHaveAttribute('href', item.order_url)
  })

  it('records client use with a negative quantity and previews the result', async () => {
    const move = vi.fn().mockResolvedValue({ ...item, quantity_on_hand: '875.000' })
    render(<Stock client={stockClient({ move })} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Adjust stock' }))
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'used' } })
    fireEvent.change(screen.getByLabelText('Quantity (foot)'), { target: { value: '125' } })
    fireEvent.change(screen.getByLabelText('Client'), { target: { value: 'client-1' } })
    expect(screen.getByText(/875.000 foot/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save change' }))
    await waitFor(() => expect(move).toHaveBeenCalledWith('stock-1', expect.objectContaining({ movement_type: 'used', quantity_change: '-125', client_id: 'client-1' })))
  })

  it('uses plain grouped fields when creating an item', async () => {
    render(<Stock client={stockClient()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'New item' }))
    expect(screen.getByRole('group', { name: 'Item' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Quantity and pricing' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Latest order' })).toBeInTheDocument()
    expect(screen.getByLabelText('Cost per unit')).toHaveAttribute('step', '0.000001')
  })
})
