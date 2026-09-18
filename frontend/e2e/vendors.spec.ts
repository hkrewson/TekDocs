import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const clientId = crypto.randomUUID()
const supplierId = crypto.randomUUID()
const supplier = {
  id: supplierId,
  name: `Northwind ${'Industrial Systems '.repeat(8)}`.trim(),
  legal_name: `Northwind ${'International Holdings '.repeat(6)}Incorporated`.trim(),
  website: `https://example.invalid/${'supplier-directory/'.repeat(8)}`,
  classifications: ['vendor', 'manufacturer'],
  asset_count: 47,
}

async function mockVendorWorkspace(page: Page, baseURL: string | undefined, list = [supplier]) {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL! }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner', permissions: ['assets.view'],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: clientId, name: 'Example Client', classifications: ['client'], capabilities: ['overview', 'vendors'],
    organization: { id: clientId, name: 'Example Client', legal_name: '', website: '', classifications: ['client'], created_at: '2026-09-05T12:00:00Z', updated_at: '2026-09-05T12:00:00Z' },
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/vendors**`, (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith(`/${supplierId}`)) return route.fulfill({ json: supplier })
    return route.fulfill({ json: { results: list, page: 1, page_size: 25, count: list.length, has_more: false } })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`supplier collection and record fit at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 720 })
    await mockVendorWorkspace(page, baseURL)
    await page.goto(`/workspaces/organizations/${clientId}/vendors`)

    await expect(page.getByRole('heading', { name: 'Vendors and manufacturers' })).toBeVisible()
    await expect(page.getByRole('group', { name: 'Vendors and manufacturers' })).toContainText('47')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.locator('tbody .collection-name').click()
    const drawer = page.getByRole('dialog')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole('heading', { level: 2 })).toBeFocused()
    await expect(drawer.getByText('47 assets')).toBeVisible()
    await expect(drawer.getByRole('link', { name: 'Open vendor workspace' })).toHaveAttribute('href', `/workspaces/organizations/${supplierId}/overview`)
    await expect(drawer.getByRole('link', { name: 'Open product catalog' })).toHaveAttribute('href', `/workspaces/organizations/${supplierId}/products`)
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)

    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}

test('a direct supplier URL retrieves a record outside the current page', async ({ page, baseURL }) => {
  await mockVendorWorkspace(page, baseURL, [])
  await page.goto(`/workspaces/organizations/${clientId}/vendors?vendor_page=2&vendor=${supplierId}`)
  await expect(page.getByRole('dialog').getByRole('heading', { name: supplier.name })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`vendor_page=2.*vendor=${supplierId}`))
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page).toHaveURL(new RegExp('vendor_page=2$'))
})
