import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Invoices } from './Invoices'
import type { InvoiceClient, InvoiceDraft } from './api'
import type { WorkspaceContext } from '../workspaces/api'

const workspace: WorkspaceContext = {
  kind: 'organization',
  id: 'client-1',
  name: 'Example Client',
  classifications: ['client'],
  capabilities: ['overview', 'accounting'],
  organization: null,
}

const draft: InvoiceDraft = {
  id: 'invoice-1',
  state: 'draft',
  currency: 'USD',
  invoice_date: '2026-08-29',
  due_date: '2026-09-28',
  reference: 'PO-44',
  notes: '',
  subtotal: '125.00',
  tax_total: '12.50',
  total: '137.50',
  lines: [{
    id: 'line-1',
    position: 1,
    description: 'Managed firewall',
    quantity: '1.000',
    unit_amount: '125.00',
    currency: 'USD',
    tax_rate_name: 'Sales tax',
    tax_rate_value: '0.100000',
    tax_inclusive: false,
    net: '125.00',
    tax: '12.50',
    total: '137.50',
    origin_type: 'catalog_product',
    origin_id: 'product-1',
  }],
  created_at: '2026-08-29T12:00:00Z',
  updated_at: '2026-08-29T12:00:00Z',
}

function invoiceClient(overrides: Partial<InvoiceClient> = {}): InvoiceClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [draft], can_manage: true }),
    choices: vi.fn().mockResolvedValue({
      origins: [{ id: 'rate-1', origin_type: 'service_rate', name: 'Remote support', description: '', unit_amount: '90.00', currency: 'USD', quantity: '1.000' }],
      tax_rates: [],
    }),
    create: vi.fn().mockResolvedValue(draft),
    update: vi.fn().mockResolvedValue(draft),
    remove: vi.fn().mockResolvedValue(undefined),
    addLine: vi.fn().mockResolvedValue(draft),
    updateLine: vi.fn().mockResolvedValue(draft),
    removeLine: vi.fn().mockResolvedValue({ ...draft, lines: [], subtotal: '0.00', tax_total: '0.00', total: '0.00' }),
    ...overrides,
  }
}

describe('Invoices', () => {
  it('shows exact draft totals and creates a snapshotted origin line', async () => {
    const addLine = vi.fn().mockResolvedValue(draft)
    const client = invoiceClient({ addLine })
    render(<Invoices workspace={workspace} client={client} />)

    expect(await screen.findByRole('heading', { name: 'Draft · Aug 29, 2026' })).toBeInTheDocument()
    expect(screen.getAllByText('USD 137.50')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Add line' }))
    fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'service_rate:rate-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save line' }))

    await waitFor(() => expect(addLine).toHaveBeenCalledWith(
      workspace,
      'invoice-1',
      { origin_type: 'service_rate', origin_id: 'rate-1', tax_rate_id: null },
    ))
  })

  it('keeps a read-only draft useful without requesting edit-only choices', async () => {
    const choices = vi.fn()
    const client = invoiceClient({
      list: vi.fn().mockResolvedValue({ results: [draft], can_manage: false }),
      choices,
    })
    render(<Invoices workspace={workspace} client={client} />)

    expect(await screen.findByText('Managed firewall')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add line' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New draft' })).not.toBeInTheDocument()
    expect(choices).not.toHaveBeenCalled()
  })

  it('retains the snapshotted tax when an existing line is edited', async () => {
    const updateLine = vi.fn().mockResolvedValue(draft)
    render(<Invoices workspace={workspace} client={invoiceClient({ updateLine })} />)

    await screen.findByRole('heading', { name: 'Draft · Aug 29, 2026' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit line Managed firewall' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save line' }))

    await waitFor(() => expect(updateLine).toHaveBeenCalledWith(
      workspace,
      'invoice-1',
      'line-1',
      expect.objectContaining({
        tax_rate_name: 'Sales tax',
        tax_rate_value: '0.100000',
        tax_inclusive: false,
      }),
    ))
  })

  it('shows a bounded error state when the workspace request fails', async () => {
    const client = invoiceClient({ list: vi.fn().mockRejectedValue(new Error('Denied')) })
    render(<Invoices workspace={workspace} client={client} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Invoice drafts could not be loaded.')
  })
})
