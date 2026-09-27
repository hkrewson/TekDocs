import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { RecurringInvoices } from './RecurringInvoices'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import type { RecurringClient, RecurringSchedule } from './recurringApi'
import type { WorkspaceContext } from '../workspaces/api'

const workspace: WorkspaceContext = { kind: 'organization', id: 'client', name: 'Client', classifications: ['client'], capabilities: ['invoices'], organization: null }
const schedule: RecurringSchedule = { id: 'schedule', contract_cost_id: 'cost', source_label: 'Provider fee', contract_name: 'Support contract', anchor: '2025-01-01', ends_on: null, interval: 'monthly', enabled: true, terms: [{ id: 'terms', version: 1, effective_from: '2025-01-01', description: 'Managed support', quantity: '2.000', unit_amount: '75.0000', currency: 'USD', due_days: 30, tax_rate_id: null, source_digest: 'digest' }] }
function renderRecurring(client: RecurringClient, openInvoice = vi.fn()) {
  const router = createMemoryRouter([{ path: '*', element: <NavigationGuardProvider><RecurringInvoices workspace={workspace} client={client} openInvoice={openInvoice} /></NavigationGuardProvider> }])
  render(<RouterProvider router={router} />)
}
function fixture() {
  let retained = schedule
  const amended = { id: 'terms-2', version: 2, effective_from: '2025-04-01', description: 'Revised support', quantity: '3.000', unit_amount: '90.0000', currency: 'USD', due_days: 14, tax_rate_id: null, source_digest: 'digest' }
  const client: RecurringClient = {
    get: vi.fn().mockImplementation(() => Promise.resolve(retained)),
    stop: vi.fn().mockImplementation(() => { retained = { ...schedule, enabled: false }; return Promise.resolve(retained) }),
    list: vi.fn().mockImplementation(() => Promise.resolve({ results: [retained], page: 1, page_size: 20, count: 1, has_more: false, business_date: '2025-03-01' })),
    due: vi.fn().mockResolvedValue({ due_from: '2025-01-01', as_of: '2025-03-01', periods: [
      { starts_on: '2025-01-01', ends_before: '2025-02-01', invoice_entity_id: 'old-invoice', can_generate: false, blocked_reason: '' },
      { starts_on: '2025-02-01', ends_before: '2025-03-01', invoice_entity_id: null, can_generate: true, blocked_reason: '' },
      { starts_on: '2025-03-01', ends_before: '2025-03-16', invoice_entity_id: null, can_generate: false, blocked_reason: 'partial' },
    ] }),
    preview: vi.fn().mockResolvedValue({ preview_id: 'preview', preview_token: 'opaque-review', expires_in_seconds: 900, schedule_id: 'schedule', terms_id: 'terms', source_digest: 'digest', as_of: '2025-03-01', currency: 'USD', description: 'Managed support', quantity: '2.000', unit_amount: '75.0000', existing_invoices: [], periods: [{ starts_on: '2025-02-01', ends_before: '2025-03-01', due_date: '2025-03-03', net: '150.00', tax: '0.00', total: '150.00' }] }),
    apply: vi.fn().mockResolvedValue([{ id: 'claim', starts_on: '2025-02-01', ends_before: '2025-03-01', invoice_entity_id: 'new-invoice', line_id: 'line' }]),
    reviewSource: vi.fn().mockResolvedValue({ source: { cost_id: 'cost', contract_id: 'contract', label: 'Provider fee', amount: '20.00', quantity: '1.000', currency: 'USD', interval: 'monthly', cost_starts_on: '2025-01-01', cost_ends_on: null, contract_starts_on: '2025-01-01', contract_ends_on: null }, source_digest: 'digest', earliest_anchor: '2025-01-01', latest_end: null, business_date: '2025-03-01' }),
    taxes: vi.fn().mockResolvedValue([]),
    previewTerms: vi.fn().mockResolvedValue({ preview_id: 'terms-preview', preview_token: 'opaque-terms-review', expires_in_seconds: 900, schedule_id: 'schedule', expected_terms_id: 'terms', expected_source_digest: 'digest', reviewed_on: '2025-03-01', source_changed: false, current: { terms_id: 'terms', version: 1, effective_from: '2025-01-01', description: 'Managed support', quantity: '2.000', unit_amount: '75.0000', currency: 'USD', due_days: 30, tax_rate_id: null, net: '150.00', tax: '0.00', total: '150.00' }, proposed: { version: 2, effective_from: '2025-04-01', description: 'Revised support', quantity: '3.000', unit_amount: '90.0000', currency: 'USD', due_days: 14, tax_rate_id: null, net: '270.00', tax: '0.00', total: '270.00' } }),
    applyTerms: vi.fn().mockImplementation(() => { retained = { ...retained, terms: [...retained.terms, amended] }; return Promise.resolve(amended) }),
  }
  const openInvoice = vi.fn().mockResolvedValue(undefined)
  renderRecurring(client, openInvoice)
  return { client, openInvoice }
}
async function select() {
  fireEvent.click(await screen.findByRole('button', { name: /Managed support/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Find due periods' }))
  const checks = await screen.findAllByRole('checkbox')
  expect(checks[0]).toBeDisabled(); expect(checks[2]).toBeDisabled()
  fireEvent.click(checks[1])
  fireEvent.click(screen.getByRole('button', { name: 'Review selected periods' }))
  await screen.findByRole('button', { name: 'Create reviewed drafts' })
}
describe('recurring review', () => {
  it('uses server dates, blocks retained and partial periods, and applies only a reviewed token', async () => {
    const { client, openInvoice } = fixture()
    await select()
    expect(client.due).toHaveBeenCalledWith(workspace, 'schedule', '2025-01-01', '2025-03-01')
    expect(client.preview).toHaveBeenCalledWith(workspace, 'schedule', ['2025-02-01'], '2025-03-01')
    expect(screen.getByText(/USD 150.00/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create reviewed drafts' }))
    const openButton = await screen.findByRole('button', { name: /Open invoice for/ })
    await act(async () => { fireEvent.click(openButton); await Promise.resolve() })
    expect(client.apply).toHaveBeenCalledWith(workspace, 'schedule', 'opaque-review')
    expect(openInvoice).toHaveBeenCalledWith('new-invoice')
  })
  it('invalidates a preview when dates change', async () => {
    fixture(); await select()
    fireEvent.change(screen.getByLabelText('Due as of'), { target: { value: '2025-02-01' } })
    expect(screen.queryByRole('button', { name: 'Create reviewed drafts' })).not.toBeInTheDocument()
  })
  it('retains an uncertain apply token for a safe retry', async () => {
    const { client } = fixture(); await select()
    vi.mocked(client.apply).mockRejectedValueOnce(new Error('Lost response'))
    fireEvent.click(screen.getByRole('button', { name: 'Create reviewed drafts' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Create reviewed drafts' }))
    await screen.findByText('Draft invoices are ready. Nothing has been issued or sent.')
    expect(client.apply).toHaveBeenCalledTimes(2)
    expect(vi.mocked(client.apply).mock.calls[0]).toEqual(vi.mocked(client.apply).mock.calls[1])
  })
  it('requires a new review after expiry', async () => {
    fixture(); await select()
    vi.useFakeTimers()
    try {
      // The apply-time check also covers suspended/background browser timers.
      vi.setSystemTime(Date.now() + 901000)
      fireEvent.click(screen.getByRole('button', { name: 'Create reviewed drafts' }))
      await act(async () => {})
      expect(screen.getByText('This review expired. Review the selected periods again.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Create reviewed drafts' })).toBeDisabled()
    } finally { vi.useRealTimers() }
  })
  it('requires confirmation and a reason, clears preview, and retains invoice links after stop', async () => {
    const { client, openInvoice } = fixture(); await select()
    fireEvent.click(screen.getByRole('button', { name: 'Stop future drafts' }))
    expect(screen.queryByRole('button', { name: 'Create reviewed drafts' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm stop' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Reason for stopping'), { target: { value: '  Service ended  ' } })
    expect(client.stop).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm stop' }))
    await screen.findByText('Future drafts are stopped. Existing invoices and billing history remain available. Restarting is not supported.')
    expect(client.stop).toHaveBeenCalledWith(workspace, 'schedule', 'Service ended')
    expect(screen.queryByRole('button', { name: 'Stop future drafts' })).not.toBeInTheDocument()
    const checks = await screen.findAllByRole('checkbox')
    checks.forEach((check) => expect(check).toBeDisabled())
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open existing invoice' })); await Promise.resolve() })
    expect(openInvoice).toHaveBeenCalledWith('old-invoice')
  })
  it('reviews and applies future terms while retaining version history', async () => {
    const { client } = fixture()
    fireEvent.click(await screen.findByRole('button', { name: /Managed support/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Change future terms' }))
    await screen.findByText(/Current source: Provider fee/)
    fireEvent.change(screen.getByLabelText('Effective billing period'), { target: { value: '2025-04-01' } })
    fireEvent.change(screen.getByLabelText('Client invoice description'), { target: { value: 'Revised support' } })
    fireEvent.change(screen.getByLabelText('Client unit price'), { target: { value: '90.0000' } })
    fireEvent.change(screen.getByLabelText('Client quantity'), { target: { value: '3.000' } })
    fireEvent.change(screen.getByLabelText('Payment due days after period start'), { target: { value: '14' } })
    fireEvent.click(screen.getByRole('button', { name: 'Review future terms' }))
    await screen.findByText('USD 270.00')
    expect(client.previewTerms).toHaveBeenCalledWith(workspace, 'schedule', expect.objectContaining({ effective_from: '2025-04-01', expected_terms_id: 'terms' }))
    fireEvent.click(screen.getByRole('button', { name: 'Apply reviewed terms' }))
    await screen.findByText(/Version 2, effective/)
    expect(client.applyTerms).toHaveBeenCalledWith(workspace, 'schedule', 'opaque-terms-review')
    expect(screen.queryByRole('heading', { name: 'Change future client terms' })).not.toBeInTheDocument()
  })
  it('guards a dirty terms amendment and preserves it when editing continues', async () => {
    fixture()
    fireEvent.click(await screen.findByRole('button', { name: /Managed support/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Change future terms' }))
    await screen.findByText(/Current source: Provider fee/)
    fireEvent.change(screen.getByLabelText('Client invoice description'), { target: { value: 'Unsaved revision' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText('Client invoice description')).toHaveValue('Unsaved revision')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Discard changes' }))
    expect(screen.queryByRole('heading', { name: 'Change future client terms' })).not.toBeInTheDocument()
  })
  it('cancels confirmation without sending a stop or retaining the old preview', async () => {
    const { client } = fixture(); await select()
    fireEvent.click(screen.getByRole('button', { name: 'Stop future drafts' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(client.stop).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Create reviewed drafts' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Find due periods' })).toBeEnabled()
  })
  it('keeps generation blocked after denial until a successful status check', async () => {
    const { client } = fixture(); await select()
    vi.mocked(client.stop).mockRejectedValueOnce(new Error('Denied'))
    vi.mocked(client.get).mockRejectedValueOnce(new Error('Still denied')).mockResolvedValueOnce(schedule)
    fireEvent.click(screen.getByRole('button', { name: 'Stop future drafts' }))
    fireEvent.change(screen.getByLabelText('Reason for stopping'), { target: { value: 'End service' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm stop' }))
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Find due periods' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Check schedule status' }))
    await waitFor(() => expect(client.get).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Check schedule status' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Check schedule status' }))
    await screen.findByRole('button', { name: 'Stop future drafts' })
    expect(screen.queryByRole('button', { name: 'Create reviewed drafts' })).not.toBeInTheDocument()
    expect(client.apply).not.toHaveBeenCalled()
  })
  it('retries an uncertain stop with the same reason', async () => {
    const { client } = fixture(); await select()
    vi.mocked(client.stop).mockRejectedValueOnce(new Error('Lost response'))
    fireEvent.click(screen.getByRole('button', { name: 'Stop future drafts' }))
    fireEvent.change(screen.getByLabelText('Reason for stopping'), { target: { value: 'End service' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm stop' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Reason for stopping')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry stop' }))
    await screen.findByText('Future drafts are stopped. Existing invoices and billing history remain available. Restarting is not supported.')
    expect(vi.mocked(client.stop).mock.calls[0]).toEqual(vi.mocked(client.stop).mock.calls[1])
  })
  it('shows a denied discovery request without exposing schedules', async () => {
    const client = { list: vi.fn().mockRejectedValue(new Error('Denied')) } as unknown as RecurringClient
    renderRecurring(client)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
  })
})
