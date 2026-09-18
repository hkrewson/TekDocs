import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const organizationId = crypto.randomUUID()
const licenseId = crypto.randomUUID()
const license = {
  id: licenseId,
  name: `Endpoint Protection ${'Distributed Operations Agreement '.repeat(5)}`.trim(),
  supplier_name: 'Northwind Security Systems', product_id: crypto.randomUUID(), product_name: 'Secure Agent Enterprise', model_name: 'Managed Business',
  kind: 'subscription', status: 'active', seat_limit: 125, active_seats: 1, starts_on: '2026-01-01', renews_on: '2027-01-01', ends_on: null,
  renewal_interval: 'annual', auto_renew: true, reference: 'AGR-2026-ENDPOINT-PROTECTION-LONG-REFERENCE',
  installations: [{ id: 'installation-1', name: `Reception workstation ${'east wing '.repeat(6)}`.trim() }],
  seats: [{ id: 'seat-1', seat_number: 1, person_id: 'person-1', person_name: 'Morgan Ellis', installation_id: 'installation-1', installation_name: 'Reception workstation', assigned_at: '2026-09-01T12:00:00Z', revoked_at: null }],
  events: [{ id: 'event-1', event_type: 'seat_assigned', installation_name: 'Reception workstation', person_name: 'Morgan Ellis', seat_number: 1, occurred_at: '2026-09-01T12:00:00Z' }],
}

async function mockLicenseWorkspace(page: Page, baseURL: string | undefined, listed = true) {
  let currentLicense = license
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL! }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['assets.view', 'assets.edit'],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Contoso Operations', classifications: ['client'], capabilities: ['overview', 'licenses'],
    organization: { id: organizationId, name: 'Contoso Operations', legal_name: '', website: '', classifications: ['client'], created_at: '2026-09-05T12:00:00Z', updated_at: '2026-09-18T12:00:00Z' },
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/licenses/choices`, (route) => route.fulfill({ json: {
    installations: [{ id: 'installation-1', asset_id: 'asset-1', asset_name: 'Reception workstation', product_id: license.product_id, product_name: license.product_name, model_name: license.model_name, status: 'installed', installed_version: '8.2', installed_on: '2026-08-01', last_verified_on: null, site_id: null, site_name: null }],
    people: [{ id: 'person-1', name: 'Morgan Ellis' }],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/licenses**`, (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/choices')) return route.fulfill({ json: {
      installations: [{ id: 'installation-1', asset_id: 'asset-1', asset_name: 'Reception workstation', product_id: license.product_id, product_name: license.product_name, model_name: license.model_name, status: 'installed', installed_version: '8.2', installed_on: '2026-08-01', last_verified_on: null, site_id: null, site_name: null }],
      people: [{ id: 'person-1', name: 'Morgan Ellis' }],
    } })
    if (path.endsWith(`/${licenseId}`)) {
      if (request.method() === 'PATCH') { currentLicense = { ...currentLicense, ...request.postDataJSON() as Partial<typeof license> }; return route.fulfill({ json: currentLicense }) }
      return route.fulfill({ json: currentLicense })
    }
    const query = new URL(request.url()).searchParams
    expect(query.get('ordering')).toBe('name')
    expect(query.get('page')).toBe(listed ? '1' : '2')
    expect(query.get('page_size')).toBe('25')
    return route.fulfill({ json: { results: listed ? [currentLicense] : [], page: listed ? 1 : 2, page_size: 25, count: listed ? 1 : 30, has_more: false, can_manage: true } })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`license collection and complete record fit at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 760 })
    await mockLicenseWorkspace(page, baseURL)
    await page.goto(`/workspaces/organizations/${organizationId}/licenses`)

    await expect(page.getByRole('heading', { name: 'Software licenses' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.locator('tbody .collection-name').click()
    const drawer = page.getByRole('dialog', { name: license.name })
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole('heading', { level: 2 })).toBeFocused()
    await expect(drawer.getByText('0 assigned · 125 total')).toHaveCount(0)
    await expect(drawer.getByText('1 assigned · 125 total')).toBeVisible()
    await expect(drawer.getByText('Morgan Ellis').first()).toBeVisible()
    await expect(drawer.getByRole('heading', { name: 'License history' })).toBeVisible()
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)

    if (width === 1024) {
      await drawer.getByRole('button', { name: 'Edit license' }).click()
      await drawer.getByLabel('Reference').fill('AGR-RENEWED-2027')
      await drawer.getByRole('button', { name: 'Save license' }).click()
      await expect(drawer.getByText('AGR-RENEWED-2027')).toBeVisible()
    }
    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}

test('a direct license URL retrieves a record outside the current page', async ({ page, baseURL }) => {
  await mockLicenseWorkspace(page, baseURL, false)
  await page.goto(`/workspaces/organizations/${organizationId}/licenses?license_page=2&license=${licenseId}`)
  const drawer = page.getByRole('dialog', { name: license.name })
  await expect(drawer.getByText('AGR-2026-ENDPOINT-PROTECTION-LONG-REFERENCE')).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`license_page=2.*license=${licenseId}`))
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await expect(page).toHaveURL(new RegExp('license_page=2$'))
})
