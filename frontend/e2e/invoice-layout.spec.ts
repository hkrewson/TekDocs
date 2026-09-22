import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const clientId = 'invoice-layout-client'
const columns = ['name', 'state', 'invoice_date', 'due_date', 'reference', 'total']
const invoiceLines = [
  { id: 'line-1', position: 1, description: 'Managed network service', quantity: '24.000', unit_amount: '70.00', currency: 'USD', tax_rate_name: '', tax_rate_value: '0.000000', tax_inclusive: false, net: '1680.00', tax: '0.00', total: '1680.00', origin_type: '', origin_id: null },
  { id: 'line-2', position: 2, description: 'USW Power Adapter', quantity: '1.000', unit_amount: '97.44', currency: 'USD', tax_rate_name: '', tax_rate_value: '0.000000', tax_inclusive: false, net: '97.44', tax: '0.00', total: '97.44', origin_type: '', origin_id: null },
  { id: 'line-3', position: 3, description: 'TP-Link TL-SG116 16 Port Gigabit Switch', quantity: '1.000', unit_amount: '64.19', currency: 'USD', tax_rate_name: '', tax_rate_value: '0.000000', tax_inclusive: false, net: '64.19', tax: '0.00', total: '64.19', origin_type: '', origin_id: null },
]
const invoices = Array.from({ length: 61 }, (_, index) => ({
  id: `invoice-${index + 1}`,
  state: index % 2 ? 'issued' : 'draft',
  number: index % 2 ? `INV-${String(index + 1).padStart(6, '0')}` : undefined,
  currency: 'USD', invoice_date: '2026-08-29', due_date: '2026-09-28',
  reference: `PO-${String(index + 1).padStart(3, '0')}`, notes: '', subtotal: '1841.63', tax_total: '0.00', total: '1841.63',
  lines: invoiceLines,
  created_at: '2026-08-29T12:00:00Z', updated_at: '2026-08-29T12:00:00Z',
  lifecycle_state: 'issued', reconciliation_state: 'unsynchronized', paid_amount: '0.00', balance_amount: '1841.63', lifecycle_events: [],
}))

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['invoices.view', 'invoices.edit', 'invoices.issue'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: clientId, name: 'Example Client', classifications: ['client'], capabilities: ['overview', 'invoices'],
    organization: { id: clientId, name: 'Example Client', legal_name: 'Example Client, LLC', website: '', classifications: ['client'], created_at: '2026-08-29T12:00:00Z', updated_at: '2026-08-29T12:00:00Z' },
  } }))
  await page.route('**/collection-preferences/invoices', (route) => route.fulfill({ json: { columns, available_columns: columns, default_columns: columns, page_size: 25 } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices/origin-choices`, (route) => route.fulfill({ json: { origins: [], tax_rates: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/invoices?*`, (route) => {
    const params = new URL(route.request().url()).searchParams
    const size = Number(params.get('page_size') ?? 25), pageNumber = Number(params.get('page') ?? 1)
    let found = invoices.filter((invoice) => `${invoice.number ?? ''} ${invoice.reference}`.toLowerCase().includes((params.get('q') ?? '').toLowerCase()))
    if (params.get('state')) found = found.filter((invoice) => invoice.state === params.get('state'))
    expect(params.get('summary')).toBe('true')
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size).map((invoice) => ({ ...invoice, lines: undefined, lifecycle_events: undefined })), page: pageNumber, page_size: size, count: found.length, has_more: pageNumber * size < found.length, can_manage: true, can_issue: true } })
  })
  await page.route(/\/invoices\/invoice-\d+$/, (route) => {
    const invoice = invoices.find((candidate) => route.request().url().endsWith(`/${candidate.id}`))
    return route.fulfill(invoice ? { json: invoice } : { status: 404, json: {} })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`invoice collection and focused record fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 })
    await fixtures(page)
    await page.goto(`/workspaces/organizations/${clientId}/invoices`)
    await expect(page.getByText('61 invoices', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Draft · Aug 29, 2026' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Aug 29, 2026', exact: true }).first().click()
    await expect(page).toHaveURL(/invoice=invoice-1/)
    await expect(page.getByRole('heading', { name: 'Draft · Aug 29, 2026' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Back to invoices' })).toBeVisible()
    const lineRows = page.locator('.invoice-line-list > li')
    await expect(lineRows).toHaveCount(3)
    const firstLine = lineRows.first()
    expect(await firstLine.evaluate((row) => {
      const description = row.querySelector<HTMLElement>('.invoice-line-description')!.getBoundingClientRect()
      const total = row.querySelector<HTMLElement>('.invoice-line-total')!.getBoundingClientRect()
      const actions = row.querySelector<HTMLElement>('.invoice-line-actions')!.getBoundingClientRect()
      const buttons = [...row.querySelectorAll<HTMLElement>('button')]
      return innerWidth >= 768
        ? description.left < total.left && total.left < actions.left && Math.abs((description.top + description.bottom) / 2 - (total.top + total.bottom) / 2) < 4 && buttons.every((button) => button.offsetWidth < 100)
        : total.right <= innerWidth && actions.top >= description.bottom && buttons.every((button) => button.offsetWidth < 100)
    })).toBe(true)
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('link', { name: 'Back to invoices' }).click()
    await expect(page.getByText('61 invoices', { exact: true })).toBeVisible()
  })
}

test('invoice search and paging address the full collection', async ({ page }) => {
  await fixtures(page)
  await page.goto(`/workspaces/organizations/${clientId}/invoices`)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await page.getByRole('searchbox', { name: 'Search invoices' }).fill('PO-061')
  await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByText('1 invoices', { exact: true })).toBeVisible()
  await expect(page).not.toHaveURL(/page=2/)
  await expect(page.getByRole('button', { name: 'Aug 29, 2026', exact: true })).toBeVisible()
})
