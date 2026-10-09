import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { Invoices } from './Invoices'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import { InvoiceRequestError } from './api'
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
  document_kind: 'invoice',
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
    unit: 'each',
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
  issuer: { legal_name: 'Example MSP, LLC', billing_email: 'billing@example.invalid', address_line_1: '100 Main Street', city: 'Austin', region: 'TX', postal_code: '78701', country_code: 'US' },
  bill_to: { legal_name: 'Example Client, LLC', contact_name: 'Morgan Lee', billing_email: 'accounts@example.invalid', address_line_1: '400 Congress Avenue', city: 'Austin', region: 'TX', postal_code: '78701', country_code: 'US' },
  created_at: '2026-08-29T12:00:00Z',
  updated_at: '2026-08-29T12:00:00Z',
}

function invoiceClient(overrides: Partial<InvoiceClient> = {}): InvoiceClient {
  const settings = {
    configured: true, issue_ready: true, readiness_issues: [], legal_name: 'Example MSP, LLC', address_line_1: '100 Main Street',
    address_line_2: '', city: 'Austin', region: 'TX', postal_code: '78701', country_code: 'US',
    billing_email: 'billing@example.invalid', phone: '', tax_registration: '', payment_instructions: '', default_currency: 'USD',
    payment_terms_days: 30, invoice_prefix: 'INV', credit_note_prefix: 'CR', invoice_date_component: 'none', invoice_separator: '-',
    invoice_sequence_digits: 6, invoice_reset_period: 'never', country_choices: [{ value: 'US', label: 'United States' }],
  }
  return {
    list: vi.fn().mockResolvedValue({ results: [draft], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true, can_issue: true, can_void: true }),
    get: vi.fn().mockResolvedValue(draft),
    choices: vi.fn().mockResolvedValue({
      origins: [{ id: 'rate-1', origin_type: 'service_rate', name: 'Remote support', description: '', unit_amount: '75.00', currency: 'USD', quantity: '1.000' }],
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
    withdrawRecurring: vi.fn().mockResolvedValue(draft),
    deliver: vi.fn().mockResolvedValue({ ...draft, state: 'issued', number: 'INV-000001', delivered_at: '2026-08-29T14:00:00Z', delivery_count: 1 }),
    recordEvent: vi.fn().mockResolvedValue({ ...draft, state: 'issued', number: 'INV-000001' }),
    followUp: vi.fn().mockResolvedValue(draft),
    createCreditNote: vi.fn().mockResolvedValue({ ...draft, id: 'credit-1', document_kind: 'credit_note', reference: 'Service adjustment' }),
    voidInvoice: vi.fn().mockResolvedValue({ ...draft, state: 'issued', number: 'INV-000001', lifecycle_state: 'voided' }),
    pdfUrl: vi.fn().mockReturnValue('/invoice.pdf'),
    csvUrl: vi.fn().mockReturnValue('/invoice.csv'),
    accountingExportUrl: vi.fn().mockReturnValue('/invoice-accounting.json'),
    ...overrides,
  }
}

function renderInvoice(client: InvoiceClient, path = '/workspaces/organizations/client-1/invoices?invoice=invoice-1', authClient = { reauthenticate: vi.fn().mockResolvedValue(undefined) }) {
  const router = createMemoryRouter([{ path: '*', element: <NavigationGuardProvider><Invoices workspace={workspace} client={client} authClient={authClient} /></NavigationGuardProvider> }], { initialEntries: [path] })
  return render(<RouterProvider router={router} />)
}

describe('Invoices', () => {
  it('starts in the invoice collection and opens a focused URL-addressed record', async () => {
    renderInvoice(invoiceClient(), '/workspaces/organizations/client-1/invoices')

    expect(await screen.findByRole('heading', { name: 'Invoices' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Draft · Aug 29, 2026' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Aug 29, 2026' }))

    expect(await screen.findByRole('heading', { name: 'Draft · Aug 29, 2026' })).toBeInTheDocument()
  })

  it('keeps an unavailable direct invoice bounded with a return to the collection', async () => {
    renderInvoice(invoiceClient({ get: vi.fn().mockRejectedValue(new Error('Missing')) }), '/workspaces/organizations/client-1/invoices?invoice=missing')

    expect(await screen.findByRole('alert')).toHaveTextContent('Reload this page to try again.')
    expect(screen.getByRole('link', { name: 'Back to invoices' })).toHaveAttribute('href', '/workspaces/organizations/client-1/invoices')
  })

  it('keeps MSP settings out of the client workspace and links there when setup is incomplete', async () => {
    const client = invoiceClient({ issue: vi.fn().mockRejectedValue(new Error('Configure invoice issue settings first.')) })
    renderInvoice(client)

    expect(await screen.findByRole('heading', { name: 'Invoices' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invoice settings' })).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Review and issue' }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Issue invoice' }))
    expect(await screen.findByRole('link', { name: 'Open invoice settings' })).toHaveAttribute('href', '/invoices')
  })

  it('shows the calculated amount and honors quantity for a sourced line', async () => {
    const addLine = vi.fn().mockResolvedValue(draft)
    const client = invoiceClient({ addLine })
    renderInvoice(client)

    expect(await screen.findByRole('heading', { name: 'Draft · Aug 29, 2026' })).toBeInTheDocument()
    expect(screen.getAllByText('USD 137.50')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Add item' }))
    fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'service_rate:rate-1' } })
    expect(screen.getByLabelText('Unit label (optional)')).not.toBeRequired()
    fireEvent.change(screen.getByLabelText('Invoice description'), { target: { value: 'Remote support · network cutover' } })
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '24' } })
    expect(screen.getByText('$1,800.00')).toBeInTheDocument()
    expect(screen.getByText('Quantity × price per unit, before tax')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save item' }))

    await waitFor(() => expect(addLine).toHaveBeenCalledWith(
      workspace,
      'invoice-1',
      { origin_type: 'service_rate', origin_id: 'rate-1', description: 'Remote support · network cutover', quantity: '24', unit: '', tax_rate_id: null },
    ))
  })

  it('uses the selected stock quantity for the client in one save', async () => {
    const addLine = vi.fn().mockResolvedValue(draft)
    const client = invoiceClient({
      addLine,
      choices: vi.fn().mockResolvedValue({
        origins: [{
          id: 'stock-1', origin_type: 'stock_item', name: 'Cat6 bulk cable', description: '',
          unit_amount: '0.30', currency: 'USD', quantity: '1.000', available_quantity: '1000.000', unit: 'foot',
        }],
        tax_rates: [],
      }),
    })
    renderInvoice(client)

    fireEvent.click(await screen.findByRole('button', { name: 'Add item' }))
    fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'stock_item:stock-1' } })
    expect(screen.getByRole('option', { name: 'In-stock item · Cat6 bulk cable · 1000.000 foot available · USD 0.30' })).toBeInTheDocument()
    expect(screen.getByText('Saving this item uses the quantity from stock for this client. 1000.000 foot are currently available.')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toHaveAttribute('max', '1000.000')
    fireEvent.change(screen.getByLabelText('Invoice description'), { target: { value: 'Cat6 bulk cable · lobby camera run' } })
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '125.500' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save item' }))

    await waitFor(() => expect(addLine).toHaveBeenCalledWith(
      workspace,
      'invoice-1',
      { origin_type: 'stock_item', origin_id: 'stock-1', description: 'Cat6 bulk cable · lobby camera run', quantity: '125.500', unit: 'foot', tax_rate_id: null },
    ))
  })

  it('keeps a read-only draft useful without requesting edit-only choices', async () => {
    const choices = vi.fn()
    const client = invoiceClient({
      list: vi.fn().mockResolvedValue({ results: [draft], can_manage: false, can_issue: false, can_void: false }),
      choices,
    })
    renderInvoice(client)

    expect(await screen.findByText('Managed firewall')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add item' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New draft' })).not.toBeInTheDocument()
    expect(choices).not.toHaveBeenCalled()
  })

  it('issues a configured draft and replaces editing controls with signed proof', async () => {
    const issue = vi.fn().mockResolvedValue({ ...draft, state: 'issued', number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z', signature_algorithm: 'Ed25519', content_digest: 'a'.repeat(64), key_fingerprint: 'b'.repeat(64) })
    renderInvoice(invoiceClient({ issue }))

    await screen.findByRole('button', { name: 'Review and issue' })
    fireEvent.click(screen.getByRole('button', { name: 'Review and issue' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Issue the draft dated Aug 29, 2026?')
    expect(screen.getByRole('alertdialog')).toHaveTextContent('You cannot undo this.')
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Issue invoice' }))

    expect(await screen.findByRole('heading', { name: 'INV-000001' })).toBeInTheDocument()
    expect(issue).toHaveBeenCalledWith(workspace, 'invoice-1')
    expect(screen.queryByRole('button', { name: 'Edit draft' })).not.toBeInTheDocument()
    expect(screen.getByText(/verification ID/)).toBeInTheDocument()
  })

  it('reviews and edits invoice-specific billing details before issue', async () => {
    const update = vi.fn().mockResolvedValue(draft)
    renderInvoice(invoiceClient({ update }))

    expect(await screen.findByText('Example Client, LLC')).toBeInTheDocument()
    expect(screen.getByText('Example MSP, LLC')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit billing details' }))
    expect(screen.getByRole('heading', { name: 'Invoice billing details' })).toBeInTheDocument()
    const legalNames = screen.getAllByLabelText('Legal name')
    fireEvent.change(legalNames[1], { target: { value: 'Client AP Office' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save billing details' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const saved = update.mock.calls[0]?.[2] as { bill_to: { legal_name?: string } }
    expect(saved.bill_to.legal_name).toBe('Client AP Office')

    fireEvent.click(screen.getByRole('button', { name: 'Review and issue' }))
    const review = screen.getByRole('alertdialog')
    expect(review).toHaveTextContent('Example MSP, LLC')
    expect(review).toHaveTextContent('Example Client, LLC')
    expect(review).toHaveTextContent('USD 137.50')
  })

  it('creates a complete linked revision draft from an issued invoice', async () => {
    const issued = { ...draft, state: 'issued' as const, number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z' }
    const revision = { ...draft, id: 'invoice-2', reference: 'Replacement to INV-000001', source: { id: 'invoice-1', number: 'INV-000001', kind: 'replacement' as const } }
    const followUp = vi.fn().mockResolvedValue(revision)
    renderInvoice(invoiceClient({ get: vi.fn().mockImplementation((_workspace, id: string) => Promise.resolve(id === 'invoice-2' ? revision : issued)), followUp }))

    fireEvent.click(await screen.findByRole('button', { name: 'Revise invoice' }))
    await waitFor(() => expect(followUp).toHaveBeenCalledWith(workspace, 'invoice-1', 'replacement'))
    expect(await screen.findByText(/Every original item was carried forward/)).toBeInTheDocument()
  })

  it('shows every line and the exact server validation message before a retry', async () => {
    const issue = vi.fn().mockRejectedValue(new InvoiceRequestError('Complete the invoice-specific bill-to identity before issuing', 400))
    renderInvoice(invoiceClient({ issue }))

    fireEvent.click(await screen.findByRole('button', { name: 'Review and issue' }))
    const review = screen.getByRole('alertdialog')
    expect(review).toHaveTextContent('Managed firewall')
    expect(review).toHaveTextContent('1.000 each × USD 125.00')
    fireEvent.click(within(review).getByRole('button', { name: 'Issue invoice' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Complete the invoice-specific bill-to identity before issuing')
  })

  it('confirms the password and retries issuance when recent authentication expired', async () => {
    const issued = { ...draft, state: 'issued' as const, number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z' }
    const issue = vi.fn()
      .mockRejectedValueOnce(new InvoiceRequestError('Recent password or MFA reauthentication is required.', 403, 'recent_authentication_required'))
      .mockResolvedValueOnce(issued)
    const reauthenticate = vi.fn().mockResolvedValue(undefined)
    renderInvoice(invoiceClient({ issue }), undefined, { reauthenticate })

    fireEvent.click(await screen.findByRole('button', { name: 'Review and issue' }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Issue invoice' }))
    expect(await screen.findByRole('heading', { name: 'Confirm invoice issue' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'current-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and issue' }))

    await waitFor(() => expect(reauthenticate).toHaveBeenCalledWith('current-password'))
    await waitFor(() => expect(issue).toHaveBeenCalledTimes(2))
    expect(await screen.findByRole('heading', { name: 'INV-000001' })).toBeInTheDocument()
  })

  it('names the draft and consequence before deleting it', async () => {
    const remove = vi.fn().mockResolvedValue(undefined)
    renderInvoice(invoiceClient({ remove }))

    fireEvent.click(await screen.findByRole('button', { name: 'Delete draft' }))
    const confirmation = screen.getByRole('alertdialog')
    expect(confirmation).toHaveTextContent('Delete the draft dated Aug 29, 2026?')
    expect(confirmation).toHaveTextContent('permanently deleted')
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete draft' }))

    await waitFor(() => expect(remove).toHaveBeenCalledWith(workspace, 'invoice-1'))
    expect(await screen.findByText('No invoices have been created for this client.')).toBeInTheDocument()
  })

  it('withdraws a recurring draft with retained reason and removes mutation controls', async () => {
    const recurring = { ...draft, recurring: { starts_on: '2026-08-01', ends_before: '2026-09-01', disposition: 'active' as const, withdrawn_at: null, withdrawal_reason: '' } }
    const withdrawn = { ...recurring, recurring: { ...recurring.recurring, disposition: 'withdrawn' as const, withdrawn_at: '2026-08-30T10:00:00Z', withdrawal_reason: 'Client cancelled before issue' } }
    const withdrawRecurring = vi.fn().mockResolvedValue(withdrawn)
    renderInvoice(invoiceClient({ list: vi.fn().mockResolvedValue({ results: [recurring], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true, can_issue: true, can_void: true }), get: vi.fn().mockResolvedValue(recurring), withdrawRecurring }))

    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw draft' }))
    const confirmation = screen.getByRole('alertdialog')
    expect(confirmation).toHaveTextContent('invoice and claimed billing period remain in history')
    fireEvent.change(within(confirmation).getByLabelText('Reason for withdrawal'), { target: { value: 'Client cancelled before issue' } })
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Withdraw draft' }))

    await waitFor(() => expect(withdrawRecurring).toHaveBeenCalledWith(workspace, 'invoice-1', 'Client cancelled before issue'))
    expect(await screen.findByText('Client cancelled before issue')).toBeInTheDocument()
    expect(screen.getByText('Withdrawn', { selector: '.lifecycle-state' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Review and issue' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit draft' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add item' })).not.toBeInTheDocument()
  })

  it('reauthenticates and safely retries a recurring withdrawal', async () => {
    const recurring = { ...draft, recurring: { starts_on: '2026-08-01', ends_before: '2026-09-01', disposition: 'active' as const, withdrawn_at: null, withdrawal_reason: '' } }
    const withdrawn = { ...recurring, recurring: { ...recurring.recurring, disposition: 'withdrawn' as const, withdrawn_at: '2026-08-30T10:00:00Z', withdrawal_reason: 'Duplicate draft' } }
    const withdrawRecurring = vi.fn().mockRejectedValueOnce(new InvoiceRequestError('Recent authentication required', 403, 'recent_authentication_required')).mockResolvedValueOnce(withdrawn)
    const reauthenticate = vi.fn().mockResolvedValue(undefined)
    renderInvoice(invoiceClient({ get: vi.fn().mockResolvedValue(recurring), withdrawRecurring }), undefined, { reauthenticate })

    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw draft' }))
    fireEvent.change(screen.getByLabelText('Reason for withdrawal'), { target: { value: 'Duplicate draft' } })
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Withdraw draft' }))
    expect(await screen.findByRole('heading', { name: 'Confirm recurring draft withdrawal' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'current-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and withdraw' }))

    await waitFor(() => expect(reauthenticate).toHaveBeenCalledWith('current-password'))
    await waitFor(() => expect(withdrawRecurring).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Duplicate draft')).toBeInTheDocument()
  })

  it('retains the snapshotted tax when an existing line is edited', async () => {
    const updateLine = vi.fn().mockResolvedValue(draft)
    renderInvoice(invoiceClient({ updateLine }))

    await screen.findByRole('heading', { name: 'Draft · Aug 29, 2026' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit item Managed firewall' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save item' }))

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
    renderInvoice(invoiceClient({
      list: vi.fn().mockResolvedValue({ results: [issued], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true, can_issue: true, can_void: true }),
      get: vi.fn().mockResolvedValue(issued),
      deliver,
    }))

    expect(await screen.findByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/invoice.pdf')
    expect(screen.getByRole('link', { name: 'Download CSV' })).toHaveAttribute('href', '/invoice.csv')
    fireEvent.click(screen.getByRole('button', { name: 'Email invoice' }))
    fireEvent.change(screen.getByLabelText('Recipient email'), { target: { value: 'accounts@example.invalid' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send invoice' }))

    await waitFor(() => expect(deliver).toHaveBeenCalledWith(workspace, 'invoice-1', 'accounts@example.invalid'))
    expect(await screen.findByText('Emailed once · sent Aug 29, 2026')).toBeInTheDocument()
  })

  it('records an idempotent accounting handoff and payment projection', async () => {
    const issued = { ...draft, state: 'issued' as const, number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z', lifecycle_state: 'issued' as const, reconciliation_state: 'unsynchronized' as const, paid_amount: '0.00', balance_amount: '137.50', lifecycle_events: [] }
    const synchronized = { ...issued, lifecycle_state: 'externally_synchronized' as const, reconciliation_state: 'synchronized' as const, lifecycle_events: [{ id: 'event-1', event_type: 'accounting_synchronized', occurred_at: '2026-08-29T14:00:00Z', recorded_at: '2026-08-29T14:00:00Z', actor: 'Invoice Owner', provider: 'ledger', external_id: 'evt-1', amount: null, currency: '', related_invoice_id: null, note: 'Invoice 44' }] }
    const recordEvent = vi.fn().mockResolvedValue(synchronized)
    renderInvoice(invoiceClient({
      list: vi.fn().mockResolvedValue({ results: [issued], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true, can_issue: true, can_void: true }),
      get: vi.fn().mockResolvedValue(issued),
      recordEvent,
    }))

    expect(await screen.findByRole('link', { name: 'Download for accounting' })).toHaveAttribute('href', '/invoice-accounting.json')
    fireEvent.click(screen.getAllByRole('button', { name: 'Update status' }).at(-1)!)
    fireEvent.change(screen.getByLabelText('What changed'), { target: { value: 'accounting_synchronized' } })
    fireEvent.change(screen.getByLabelText('Accounting system'), { target: { value: 'ledger' } })
    fireEvent.change(screen.getByLabelText('Invoice ID in accounting system'), { target: { value: 'evt-1' } })
    fireEvent.change(screen.getByLabelText('Unique update ID'), { target: { value: 'ledger:evt-1' } })
    expect(screen.getByText(/prevent the same update from being recorded twice/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Reference or note'), { target: { value: 'Invoice 44' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Update status' }).at(-1)!)

    await waitFor(() => expect(recordEvent).toHaveBeenCalledWith(workspace, 'invoice-1', expect.objectContaining({
      event_type: 'accounting_synchronized', provider: 'ledger', external_id: 'evt-1', idempotency_key: 'ledger:evt-1',
    })))
    expect(await screen.findAllByText('Sent to accounting')).not.toHaveLength(0)
  })

  it('creates a reasoned credit-note draft from an issued invoice', async () => {
    const issued = { ...draft, state: 'issued' as const, number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z', lifecycle_state: 'issued' as const, balance_amount: '137.50', delivery_count: 1 }
    const credit = { ...draft, id: 'credit-1', document_kind: 'credit_note' as const, reference: 'Service adjustment' }
    const createCreditNote = vi.fn().mockResolvedValue(credit)
    renderInvoice(invoiceClient({
      list: vi.fn().mockResolvedValue({ results: [issued], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true, can_issue: true, can_void: true }),
      get: vi.fn().mockImplementation((_workspace, id) => Promise.resolve(id === 'credit-1' ? credit : issued)),
      createCreditNote,
    }))

    fireEvent.click(await screen.findByRole('button', { name: 'Create credit note' }))
    fireEvent.change(screen.getByLabelText('Reason for correction'), { target: { value: 'Service adjustment' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Create credit note' }).at(-1)!)

    await waitFor(() => expect(createCreditNote).toHaveBeenCalledWith(workspace, 'invoice-1', 'Service adjustment'))
    expect(await screen.findByRole('heading', { name: 'Credit note draft · Aug 29, 2026' })).toBeInTheDocument()
  })

  it('voids only an undelivered issued invoice while retaining its record', async () => {
    const issued = { ...draft, state: 'issued' as const, number: 'INV-000001', issued_at: '2026-08-29T13:00:00Z', lifecycle_state: 'issued' as const, balance_amount: '137.50', delivery_count: 0 }
    const voided = { ...issued, lifecycle_state: 'voided' as const, balance_amount: '0.00' }
    const voidInvoice = vi.fn().mockResolvedValue(voided)
    renderInvoice(invoiceClient({
      list: vi.fn().mockResolvedValue({ results: [issued], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true, can_issue: true, can_void: true }),
      get: vi.fn().mockResolvedValue(issued),
      voidInvoice,
    }))

    fireEvent.click(await screen.findByRole('button', { name: 'Void invoice' }))
    fireEvent.change(screen.getByLabelText('Reason for correction'), { target: { value: 'Issued in error' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Void invoice' }).at(-1)!)

    await waitFor(() => expect(voidInvoice).toHaveBeenCalledWith(workspace, 'invoice-1', 'Issued in error'))
    expect(await screen.findAllByText('Voided')).not.toHaveLength(0)
    expect(screen.queryByRole('button', { name: 'Email invoice' })).not.toBeInTheDocument()
  })

  it('shows a bounded error state when the workspace request fails', async () => {
    const client = invoiceClient({ list: vi.fn().mockRejectedValue(new Error('Denied')) })
    renderInvoice(client)
    expect(await screen.findByRole('alert')).toHaveTextContent('Invoices could not be loaded.')
  })
})
