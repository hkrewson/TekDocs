import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const clientId = crypto.randomUUID()
const invoiceId = crypto.randomUUID()
const issuedInvoice = {
  id: invoiceId,
  state: 'issued',
  number: 'INV-2026-000042',
  currency: 'USD',
  invoice_date: '2026-08-29',
  due_date: '2026-09-28',
  reference: 'MSA-44',
  notes: '',
  subtotal: '125.00',
  tax_total: '0.00',
  total: '125.00',
  lines: [{ id: crypto.randomUUID(), position: 1, description: 'Managed service', quantity: '1.000', unit_amount: '125.00', currency: 'USD', tax_rate_name: '', tax_rate_value: '0.000000', tax_inclusive: false, net: '125.00', tax: '0.00', total: '125.00', origin_type: '', origin_id: null }],
  created_at: '2026-08-29T12:00:00Z',
  updated_at: '2026-08-29T12:00:00Z',
  issued_at: '2026-08-29T12:00:00Z',
  content_digest: 'a'.repeat(64),
  signature_algorithm: 'Ed25519',
  key_fingerprint: 'b'.repeat(64),
  delivered_at: null,
  delivery_count: 0,
  lifecycle_state: 'overdue',
  reconciliation_state: 'unsynchronized',
  paid_amount: '0.00',
  balance_amount: '125.00',
  last_event_at: '2026-08-29T12:00:00Z',
  lifecycle_events: [{ id: crypto.randomUUID(), event_type: 'issued', occurred_at: '2026-08-29T12:00:00Z', recorded_at: '2026-08-29T12:00:00Z', actor: 'Primary Owner', provider: '', external_id: '', amount: null, currency: '', related_invoice_id: null, note: '' }],
}

test('invoice lifecycle and accounting handoff remain compact and accessible', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner',
    permissions: ['invoices.view', 'invoices.edit', 'invoices.issue'],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: clientId, name: 'Example Client', classifications: ['client'], capabilities: ['overview', 'invoices'],
    organization: { id: clientId, name: 'Example Client', legal_name: 'Example Client, LLC', website: '', classifications: ['client'], created_at: '2026-08-29T12:00:00Z', updated_at: '2026-08-29T12:00:00Z' },
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices/origin-choices`, (route) => route.fulfill({ json: { origins: [], tax_rates: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices`, (route) => route.fulfill({ json: { results: [issuedInvoice], can_manage: true, can_issue: true } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices/${invoiceId}/events`, async (route) => {
    expect(await route.request().postDataJSON()).toMatchObject({ event_type: 'accounting_synchronized', provider: 'ledger', external_id: 'invoice-44' })
    await route.fulfill({ json: { ...issuedInvoice, lifecycle_state: 'externally_synchronized', reconciliation_state: 'synchronized', lifecycle_events: [...issuedInvoice.lifecycle_events, { id: crypto.randomUUID(), event_type: 'accounting_synchronized', occurred_at: '2026-09-01T12:00:00Z', recorded_at: '2026-09-01T12:00:00Z', actor: 'Primary Owner', provider: 'ledger', external_id: 'invoice-44', amount: null, currency: '', related_invoice_id: null, note: '' }] } })
  })

  await page.goto(`/workspaces/organizations/${clientId}/invoices`)
  await expect(page.getByRole('heading', { name: 'INV-2026-000042' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Accounting export' })).toHaveAttribute('href', new RegExp(`${invoiceId}/accounting-export$`))
  await expect(page.getByText('Not synchronized').first()).toBeVisible()
  await page.getByRole('button', { name: 'Record update' }).click()
  await page.getByLabel('Update type').selectOption('accounting_synchronized')
  await page.getByLabel('Accounting provider').fill('ledger')
  await page.getByLabel('External record ID').fill('invoice-44')
  await page.getByLabel('Provider event ID').fill('ledger:invoice-44')
  await page.getByRole('dialog').getByRole('button', { name: 'Record update' }).click()
  await expect(page.getByText('Synchronized to accounting')).toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})
