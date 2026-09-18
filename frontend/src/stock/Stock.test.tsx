import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
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
    list: vi.fn().mockResolvedValue({ results: [item], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true, vendors: [{ id: 'vendor-1', name: 'Cable Supplier' }], clients: [{ id: 'client-1', name: 'Client Site' }] }),
    retrieve: vi.fn().mockResolvedValue(item),
    create: vi.fn().mockResolvedValue(item), update: vi.fn().mockResolvedValue(item), archive: vi.fn().mockResolvedValue(undefined), move: vi.fn().mockResolvedValue({ ...item, quantity_on_hand: '875.000' }), ...overrides,
  }
}

function renderStock(client = stockClient(), initialEntry = '/stock') {
  return render(<MemoryRouter initialEntries={[initialEntry]}><Stock client={client} /></MemoryRouter>)
}

describe('Stock', () => {
  it('shows exact stock and supplier provenance', async () => {
    renderStock()
    expect(await screen.findByRole('heading', { name: 'Stock' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Cat6 bulk cable' }))
    expect(screen.getAllByText('1000.000 foot').length).toBeGreaterThan(0)
    expect(screen.getAllByText('USD 0.145430').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /ORDER-1001/ })).toHaveAttribute('href', item.order_url)
  })

  it('records client use with a negative quantity and previews the result', async () => {
    const move = vi.fn().mockResolvedValue({ ...item, quantity_on_hand: '875.000' })
    renderStock(stockClient({ move }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cat6 bulk cable' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Adjust stock' }))
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'used' } })
    fireEvent.change(screen.getByLabelText('Quantity (foot)'), { target: { value: '125' } })
    fireEvent.change(screen.getByLabelText('Client'), { target: { value: 'client-1' } })
    expect(screen.getByText(/875.000 foot/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save change' }))
    await waitFor(() => expect(move).toHaveBeenCalledWith('stock-1', expect.objectContaining({ movement_type: 'used', quantity_change: '-125', client_id: 'client-1' })))
  })

  it('uses plain grouped fields when creating an item', async () => {
    renderStock()
    fireEvent.click(await screen.findByRole('button', { name: 'New item' }))
    expect(screen.getByRole('group', { name: 'Item' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Quantity and pricing' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Latest order' })).toBeInTheDocument()
    expect(screen.getByLabelText('Cost per unit')).toHaveAttribute('step', '0.000001')
  })

  it('does not expose creation through a direct URL without manage permission', async () => {
    renderStock(stockClient({
      list: vi.fn().mockResolvedValue({ results: [item], page: 1, page_size: 25, count: 1, has_more: false, can_manage: false, vendors: [], clients: [] }),
    }), '/stock?stock=new')
    expect(await screen.findByRole('alert')).toHaveTextContent('You do not have permission to manage stock.')
    expect(screen.queryByLabelText('Item name')).not.toBeInTheDocument()
  })

  it('loads an off-page record from the URL and protects unfinished edits', async () => {
    const retrieve = vi.fn().mockResolvedValue(item)
    renderStock(stockClient({
      list: vi.fn().mockResolvedValue({ results: [], page: 2, page_size: 25, count: 26, has_more: false, can_manage: true, vendors: [], clients: [] }),
      retrieve,
    }), '/stock?stock=stock-1&stock_page=2')
    expect(await screen.findByRole('heading', { name: 'Cat6 bulk cable' })).toBeInTheDocument()
    expect(retrieve).toHaveBeenCalledWith('stock-1', expect.any(AbortSignal))
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Changed cable' } })
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Unsaved changes')
    expect(screen.getByLabelText('Item name')).toHaveValue('Changed cable')
  })
})
