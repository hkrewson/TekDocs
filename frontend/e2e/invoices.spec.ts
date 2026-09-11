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

test('invoice status and accounting updates remain compact and accessible', async ({ page, baseURL }) => {
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
  await expect(page.getByRole('link', { name: 'Download for accounting' })).toHaveAttribute('href', new RegExp(`${invoiceId}/accounting-export$`))
  await expect(page.getByText('Not sent to accounting').first()).toBeVisible()
  await page.getByRole('button', { name: 'Update status' }).click()
  await page.getByLabel('What changed').selectOption('accounting_synchronized')
  await page.getByLabel('Accounting system', { exact: true }).fill('ledger')
  await page.getByLabel('Invoice ID in accounting system', { exact: true }).fill('invoice-44')
  await page.getByLabel('Unique update ID', { exact: true }).fill('ledger:invoice-44')
  await expect(page.getByText(/prevent the same update from being recorded twice/)).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Update status' }).click()
  await expect(page.getByText('Sent to accounting').last()).toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})

test('a stock line records its quantity for the client in one save', async ({ page, baseURL }) => {
  const draftId = crypto.randomUUID()
  const stockId = crypto.randomUUID()
  const draft = {
    ...issuedInvoice,
    id: draftId,
    state: 'draft',
    number: undefined,
    lines: [],
    subtotal: '0.00',
    total: '0.00',
    issued_at: undefined,
    lifecycle_events: [],
  }
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner',
    permissions: ['invoices.view', 'invoices.edit'],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: clientId, name: 'Example Client', classifications: ['client'], capabilities: ['overview', 'invoices'],
    organization: { id: clientId, name: 'Example Client', legal_name: 'Example Client, LLC', website: '', classifications: ['client'], created_at: '2026-08-29T12:00:00Z', updated_at: '2026-08-29T12:00:00Z' },
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices/origin-choices`, (route) => route.fulfill({ json: {
    origins: [{ id: stockId, origin_type: 'stock_item', name: 'Cat6 bulk cable', description: '', unit_amount: '0.30', currency: 'USD', quantity: '1.000', available_quantity: '1000.000', unit: 'foot' }],
    tax_rates: [],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices/${draftId}/lines`, async (route) => {
    expect(await route.request().postDataJSON()).toEqual({ origin_type: 'stock_item', origin_id: stockId, quantity: '125.500', tax_rate_id: null })
    await route.fulfill({ json: { ...draft, subtotal: '37.65', total: '37.65', lines: [{ id: crypto.randomUUID(), position: 1, description: 'Cat6 bulk cable', quantity: '125.500', unit_amount: '0.30', currency: 'USD', tax_rate_name: '', tax_rate_value: '0.000000', tax_inclusive: false, net: '37.65', tax: '0.00', total: '37.65', origin_type: 'stock_item', origin_id: stockId }] } })
  })
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices`, (route) => route.fulfill({ json: { results: [draft], can_manage: true, can_issue: false } }))

  await page.goto(`/workspaces/organizations/${clientId}/invoices`)
  await page.getByRole('button', { name: 'Add item' }).click()
  await page.getByLabel('Source').selectOption(`stock_item:${stockId}`)
  await expect(page.getByText('Saving this item uses the quantity from stock for this client. 1000.000 foot are currently available.')).toBeVisible()
  await page.getByLabel('Quantity').fill('125.500')
  await page.getByRole('dialog').getByRole('button', { name: 'Save item' }).click()
  await expect(page.getByText('125.500 × USD 0.30')).toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})

for (const width of [1280, 390]) {
  test(`recurring invoices review and apply at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 900 })
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


    const recurringPath = `**/api/v1/workspaces/organizations/${clientId}/recurring-invoices`
    const schedule = { id: 'schedule', contract_cost_id: 'cost', source_label: 'Provider fee', contract_name: 'Support contract', anchor: '2025-01-01', ends_on: null, interval: 'monthly', enabled: true, terms: [{ id: 'terms', version: 1, description: 'Managed support', quantity: '2.000', unit_amount: '75.0000', currency: 'USD', due_days: 30, tax_rate_id: null, source_digest: 'digest' }] }
    await page.route(`${recurringPath}?*`, (route) => route.fulfill({ json: { results: [schedule], page: 1, page_size: 20, count: 1, has_more: false, business_date: '2025-03-01' } }))
    await page.route(`${recurringPath}/schedule/due?*`, (route) => route.fulfill({ json: { due_from: '2025-01-01', as_of: '2025-03-01', periods: [
      { starts_on: '2025-01-01', ends_before: '2025-02-01', invoice_entity_id: invoiceId, can_generate: false, blocked_reason: '' },
      { starts_on: '2025-02-01', ends_before: '2025-03-01', invoice_entity_id: null, can_generate: true, blocked_reason: '' },
      { starts_on: '2025-03-01', ends_before: '2025-03-16', invoice_entity_id: null, can_generate: false, blocked_reason: 'partial' },
    ] } }))
    await page.route(`${recurringPath}/schedule/preview`, async (route) => {
      expect(route.request().postDataJSON()).toEqual({ starts_on: ['2025-02-01'], as_of: '2025-03-01' })
      await route.fulfill({ json: { preview_id: 'preview', preview_token: 'synthetic-review', expires_in_seconds: 900, schedule_id: 'schedule', terms_id: 'terms', source_digest: 'digest', as_of: '2025-03-01', currency: 'USD', description: 'Managed support', quantity: '2.000', unit_amount: '75.0000', existing_invoices: [], periods: [{ starts_on: '2025-02-01', ends_before: '2025-03-01', due_date: '2025-03-03', net: '150.00', tax: '0.00', total: '150.00' }] } })
    })
    await page.route(`${recurringPath}/schedule/apply`, async (route) => {
      expect(route.request().postDataJSON()).toEqual({ preview_token: 'synthetic-review' })
      await route.fulfill({ json: [{ id: 'claim', starts_on: '2025-02-01', ends_before: '2025-03-01', invoice_entity_id: invoiceId, line_id: 'line' }] })
    })
    await page.goto(`/workspaces/organizations/${clientId}/invoices`)
    await page.getByRole('button', { name: 'Recurring invoices', exact: true }).click()
    await page.getByRole('button', { name: /Managed support/ }).click()
    await page.getByRole('button', { name: 'Find due periods' }).click()
    await expect(page.getByRole('checkbox').nth(0)).toBeDisabled()
    await expect(page.getByRole('checkbox').nth(2)).toBeDisabled()
    await page.getByRole('checkbox').nth(1).focus()
    await page.keyboard.press('Space')
    await page.getByRole('button', { name: 'Review selected periods' }).click()
    await expect(page.getByText(/USD 150.00/)).toBeVisible()
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Create reviewed drafts' }).click()
    await expect(page.getByText('Draft invoices are ready. Nothing has been issued or sent.')).toBeVisible()
    await page.getByRole('button', { name: /Open invoice for/ }).click()
    await expect(page.getByRole('heading', { name: 'Recurring invoices' })).toHaveCount(0)
  })
}
