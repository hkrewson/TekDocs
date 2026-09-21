import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const settings = {
  configured: true, issue_ready: true, readiness_issues: [], legal_name: 'Example MSP, LLC', address_line_1: '100 Main Street',
  address_line_2: '', city: 'Austin', region: 'TX', postal_code: '78701', country_code: 'US',
  billing_email: 'billing@example.invalid', phone: '', tax_registration: '', default_currency: 'USD',
  payment_terms_days: 30, invoice_prefix: 'INV', invoice_date_component: 'none', invoice_separator: '-',
  invoice_sequence_digits: 6, invoice_reset_period: 'never',
  country_choices: [{ value: 'CA', label: 'Canada' }, { value: 'US', label: 'United States' }],
}

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['invoices.view', 'invoices.edit', 'invoices.issue'],
    surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/api/v1/workspaces/msp/invoice-settings', (route) => route.fulfill({ json: settings }))
}

async function chooseSection(page: Page, section: 'defaults' | 'numbering', mobile: boolean) {
  if (mobile) await page.getByRole('combobox', { name: 'Sections' }).selectOption(section)
  else await page.getByRole('link', { name: section === 'defaults' ? 'Invoice defaults' : 'Invoice numbering' }).click()
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`invoice settings remain focused and fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 })
    await fixtures(page)
    await page.goto('/invoices')
    await expect(page.getByRole('group', { name: 'Your business details' })).toBeVisible()
    await expect(page.getByRole('group', { name: 'Invoice defaults' })).toHaveCount(0)
    await expect(page.getByRole('group', { name: 'Invoice numbering' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)

    await chooseSection(page, 'numbering', width < 720)
    await expect(page).toHaveURL(/section=numbering/)
    await expect(page.getByRole('group', { name: 'Invoice numbering' })).toBeVisible()
    await expect(page.getByLabel('Invoice prefix')).toBeFocused()
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)

    await page.getByLabel('Invoice prefix').fill('MSP')
    await chooseSection(page, 'defaults', width < 720)
    await expect(page.getByRole('heading', { name: 'Unsaved changes' })).toBeVisible()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(page).toHaveURL(/section=numbering/)
    await expect(page.getByLabel('Invoice prefix')).toHaveValue('MSP')
    await chooseSection(page, 'defaults', width < 720)
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page).toHaveURL(/section=defaults/)
    await expect(page.getByRole('group', { name: 'Invoice defaults' })).toBeVisible()
  })
}

test('invoice settings can retry a failed load', async ({ page }) => {
  await fixtures(page)
  let attempts = 0
  await page.route('**/api/v1/workspaces/msp/invoice-settings', (route) => {
    attempts += 1
    return attempts === 1 ? route.fulfill({ status: 503, json: {} }) : route.fulfill({ json: settings })
  })
  await page.goto('/invoices')
  await expect(page.getByRole('heading', { name: "Couldn't load invoice settings." })).toBeVisible()
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('group', { name: 'Your business details' })).toBeVisible()
})
