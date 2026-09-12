import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RecurringInvoices } from './RecurringInvoices'
import type { RecurringClient, RecurringSchedule } from './recurringApi'
import type { WorkspaceContext } from '../workspaces/api'

const workspace: WorkspaceContext = { kind: 'organization', id: 'client', name: 'Client', classifications: ['client'], capabilities: ['invoices'], organization: null }
const schedule: RecurringSchedule = { id: 'schedule', contract_cost_id: 'cost', source_label: 'Provider fee', contract_name: 'Support contract', anchor: '2025-01-01', ends_on: null, interval: 'monthly', enabled: true, terms: [{ id: 'terms', version: 1, description: 'Managed support', quantity: '2.000', unit_amount: '75.0000', currency: 'USD', due_days: 30, tax_rate_id: null, source_digest: 'digest' }] }
function fixture() {
  let retained = schedule
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
  }
  const openInvoice = vi.fn().mockResolvedValue(undefined)
  render(<RecurringInvoices workspace={workspace} client={client} openInvoice={openInvoice} />)
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
    render(<RecurringInvoices workspace={workspace} client={client} openInvoice={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
  })
})
