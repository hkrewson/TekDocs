import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import { Invoices } from './Invoices'
import type { InvoiceClient, InvoiceDraft } from './api'
import type { WorkspaceContext } from '../workspaces/api'

const workspace: WorkspaceContext = {
  kind: 'organization',
  id: 'client-1',
  name: 'Example Client',
  classifications: ['client'],
  capabilities: ['overview', 'invoices'],
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
  const settings = {
    configured: true, issue_ready: true, legal_name: 'Example MSP, LLC', address_line_1: '100 Main Street',
    address_line_2: '', city: 'Austin', region: 'TX', postal_code: '78701', country_code: 'US',
    billing_email: 'billing@example.invalid', phone: '', tax_registration: '', default_currency: 'USD',
    payment_terms_days: 30, invoice_prefix: 'INV', invoice_date_component: 'none', invoice_separator: '-',
    invoice_sequence_digits: 6, invoice_reset_period: 'never', country_choices: [{ value: 'US', label: 'United States' }],
  }
  return {
    list: vi.fn().mockResolvedValue({ results: [draft], can_manage: true, can_issue: true }),
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
    issueSettings: vi.fn().mockResolvedValue(settings),
    saveIssueSettings: vi.fn().mockResolvedValue(settings),
    issue: vi.fn().mockResolvedValue({ ...draft, state: 'issued', number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z', signature_algorithm: 'Ed25519', content_digest: 'a'.repeat(64), key_fingerprint: 'b'.repeat(64) }),
    deliver: vi.fn().mockResolvedValue({ ...draft, state: 'issued', number: 'INV-000001', delivered_at: '2026-08-29T14:00:00Z', delivery_count: 1 }),
    pdfUrl: vi.fn().mockReturnValue('/invoice.pdf'),
    csvUrl: vi.fn().mockReturnValue('/invoice.csv'),
    ...overrides,
  }
}

describe('Invoices', () => {
  it('keeps MSP settings out of the client workspace and links there when setup is incomplete', async () => {
    const client = invoiceClient({ issue: vi.fn().mockRejectedValue(new Error('Configure invoice issue settings first.')) })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<MemoryRouter><Invoices workspace={workspace} client={client} /></MemoryRouter>)

    expect(await screen.findByRole('heading', { name: 'Invoices' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invoice settings' })).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Issue invoice' }))
    expect(await screen.findByRole('link', { name: 'Open invoice settings' })).toHaveAttribute('href', '/accounting')
  })

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
      list: vi.fn().mockResolvedValue({ results: [draft], can_manage: false, can_issue: false }),
      choices,
    })
    render(<Invoices workspace={workspace} client={client} />)

    expect(await screen.findByText('Managed firewall')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add line' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New draft' })).not.toBeInTheDocument()
    expect(choices).not.toHaveBeenCalled()
  })

  it('issues a configured draft and replaces editing controls with signed proof', async () => {
    const issue = vi.fn().mockResolvedValue({ ...draft, state: 'issued', number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z', signature_algorithm: 'Ed25519', content_digest: 'a'.repeat(64), key_fingerprint: 'b'.repeat(64) })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<Invoices workspace={workspace} client={invoiceClient({ issue })} />)

    await screen.findByRole('button', { name: 'Issue invoice' })
    fireEvent.click(screen.getByRole('button', { name: 'Issue invoice' }))

    expect(await screen.findByRole('heading', { name: 'INV-000001' })).toBeInTheDocument()
    expect(issue).toHaveBeenCalledWith(workspace, 'invoice-1')
    expect(screen.queryByRole('button', { name: 'Edit draft' })).not.toBeInTheDocument()
    expect(screen.getByText(/Ed25519 signing key/)).toBeInTheDocument()
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

  it('downloads and emails an issued invoice with PDF and CSV parity', async () => {
    const issued = { ...draft, state: 'issued' as const, number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z' }
    const delivered = { ...issued, delivered_at: '2026-08-29T14:00:00Z', delivery_count: 1 }
    const deliver = vi.fn().mockResolvedValue(delivered)
    render(<Invoices workspace={workspace} client={invoiceClient({
      list: vi.fn().mockResolvedValue({ results: [issued], can_manage: true, can_issue: true }),
      deliver,
    })} />)

    expect(await screen.findByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/invoice.pdf')
    expect(screen.getByRole('link', { name: 'Download CSV' })).toHaveAttribute('href', '/invoice.csv')
    fireEvent.click(screen.getByRole('button', { name: 'Email invoice' }))
    fireEvent.change(screen.getByLabelText('Recipient email'), { target: { value: 'accounts@example.invalid' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send invoice' }))

    await waitFor(() => expect(deliver).toHaveBeenCalledWith(workspace, 'invoice-1', 'accounts@example.invalid'))
    expect(await screen.findByText(/Delivery count 1/)).toBeInTheDocument()
  })

  it('shows a bounded error state when the workspace request fails', async () => {
    const client = invoiceClient({ list: vi.fn().mockRejectedValue(new Error('Denied')) })
    render(<Invoices workspace={workspace} client={client} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Invoices could not be loaded.')
  })
})
