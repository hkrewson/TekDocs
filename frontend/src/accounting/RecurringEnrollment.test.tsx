import { fireEvent, render, screen, waitFor, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RecurringEnrollment } from './RecurringEnrollment'
import type { EnrollmentClient, EnrollmentReview } from './enrollmentApi'
import type { WorkspaceContext } from '../workspaces/api'
const workspace: WorkspaceContext = { kind: 'organization', id: 'client', name: 'Client', classifications: ['client'], capabilities: ['invoices'], organization: null }
const review: EnrollmentReview = { source: { cost_id: 'cost', contract_id: 'contract', label: 'Provider fee', amount: '20.00', quantity: '1.000', currency: 'USD', interval: 'monthly', cost_starts_on: '2025-02-01', cost_ends_on: null, contract_starts_on: '2025-01-01', contract_ends_on: '2025-12-31' }, source_digest: 'reviewed-digest', earliest_anchor: '2025-02-01', latest_end: '2025-12-31', business_date: '2025-03-01' }
function fixture() {
  const client: EnrollmentClient = {
    sources: vi.fn().mockResolvedValue({ results: [{ id: 'cost', label: 'Provider fee', contract_name: 'Support', currency: 'USD', billing_interval: 'monthly' }], count: 1, page: 1, page_size: 20, has_more: false }),
    review: vi.fn().mockResolvedValue(review), taxes: vi.fn().mockResolvedValue([{ id: 'tax', name: 'Service tax', rate: '0.07', inclusive: false }]),
    enroll: vi.fn().mockResolvedValue({ id: 'schedule' }),
  }
  const enrolled = vi.fn()
  render(<RecurringEnrollment workspace={workspace} client={client} enrolled={enrolled} cancel={vi.fn()} />)
  return { client, enrolled }
}
async function fill() {
  fireEvent.click(await screen.findByRole('button', { name: /Provider fee/ }))
  await screen.findByLabelText('Client unit price')
  expect(screen.getByLabelText('Client unit price')).toHaveValue('')
  expect(screen.getByLabelText('Client quantity')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Client invoice description'), { target: { value: 'Client support' } })
  fireEvent.change(screen.getByLabelText('Client unit price'), { target: { value: '75.00' } })
  fireEvent.change(screen.getByLabelText('Client quantity'), { target: { value: '2.000' } })
  fireEvent.change(screen.getByLabelText('First billing date'), { target: { value: '2025-02-01' } })
  fireEvent.change(screen.getByLabelText('Billing end date (inclusive)'), { target: { value: '2025-12-31' } })
  fireEvent.change(screen.getByLabelText('Payment due days after period start'), { target: { value: '30' } })
  fireEvent.change(screen.getByLabelText('Approved tax treatment'), { target: { value: 'tax' } })
  fireEvent.click(screen.getByRole('checkbox'))
}
describe('recurring enrollment', () => {
  it('requires explicit sell terms and submits the reviewed source digest and selected tax', async () => {
    const { client, enrolled } = fixture(); await fill()
    expect(screen.getByLabelText('First billing date')).toHaveAttribute('min', '2025-02-01')
    expect(screen.getByLabelText('Billing end date (inclusive)')).toHaveAttribute('max', '2025-12-31')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save approved schedule' })); await Promise.resolve() })
    expect(client.enroll).toHaveBeenCalledWith(workspace, { cost_id: 'cost', expected_source_digest: 'reviewed-digest', description: 'Client support', quantity: '2.000', unit_amount: '75.00', currency: 'USD', anchor: '2025-02-01', ends_on: '2025-12-31', due_days: 30, tax_rate_id: 'tax' })
    expect(enrolled).toHaveBeenCalledWith({ id: 'schedule' })
  })
  it('requires a refreshed source and renewed approval after a failed save while retaining entered prices', async () => {
    const { client } = fixture(); await fill()
    vi.mocked(client.enroll).mockRejectedValueOnce(new Error('Stale source'))
    fireEvent.click(screen.getByRole('button', { name: 'Save approved schedule' }))
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Save approved schedule' })).toBeDisabled()
    expect(screen.getByRole('checkbox')).toBeDisabled()
    vi.mocked(client.review).mockResolvedValue({ ...review, source_digest: 'new-digest' })
    fireEvent.click(screen.getByRole('button', { name: 'Refresh source review' }))
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeEnabled())
    expect(screen.getByLabelText('Client unit price')).toHaveValue('75.00')
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    fireEvent.click(screen.getByRole('checkbox'))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save approved schedule' })); await Promise.resolve() })
    expect(vi.mocked(client.enroll).mock.calls[1][1].expected_source_digest).toBe('new-digest')
  })
  it('clears approval when client terms change', async () => {
    fixture(); await fill()
    fireEvent.change(screen.getByLabelText('Client unit price'), { target: { value: '80.00' } })
    expect(screen.getByRole('button', { name: 'Save approved schedule' })).toBeDisabled()
  })
  it('does not offer a form if source review is denied', async () => {
    const { client } = fixture()
    vi.mocked(client.review).mockRejectedValue(new Error('Denied'))
    fireEvent.click(await screen.findByRole('button', { name: /Provider fee/ }))
    await screen.findByRole('alert')
    expect(screen.queryByLabelText('Client unit price')).not.toBeInTheDocument()
  })
})
