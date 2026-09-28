import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function fixtures(page: Page) {
  const columns = ['name', 'netbox_id', 'rack', 'rack_unit', 'rack_units', 'serial_number', 'model_name']
  let preferences = { columns, default_columns: columns, available_columns: columns, page_size: 25 }
  const records = Array.from({ length: 31 }, (_, index) => ({
    id: `device-${index + 1}`, name: `Device ${String(index + 1).padStart(2, '0')}`, role: 'switch', status: 'active',
    hardware_asset_id: `asset-${index + 1}`, hardware_asset_name: `Device ${String(index + 1).padStart(2, '0')}`,
    site_id: null, site_name: null, location_id: null, location_name: null, rack_id: null,
    rack_name: index === 30 ? 'Main rack' : null, rack_unit: index === 30 ? 12 : null, rack_units: index === 30 ? 2 : 1,
    netbox_id: 1000 + index, serial_number: `SERIAL-${index + 1}`, manufacturer_name: 'Arista', product_name: 'Campus switch',
    model_name: '7050SX3', source_observed_at: '2026-09-28T12:00:00Z',
  }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'device@example.invalid', display_name: 'Owner' }, tenant: { id: 'tenant', name: 'MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route('**/collection-preferences/network-devices', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/api/v1/workspaces/**/networks/devices?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    const found = records.filter((record) => `${record.name} ${record.serial_number} ${record.netbox_id}`.includes(query.get('q') ?? ''))
    const pageNumber = Number(query.get('page')), size = Number(query.get('page_size'))
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: true, can_create: true } })
  })
  await page.route(/\/networks\/devices\/device-\d+$/, (route) => {
    const record = records.find((item) => route.request().url().endsWith(`/${item.id}`))
    return route.fulfill(record ? { json: record } : { status: 404, json: {} })
  })
  await page.route('**/activity?*', (route) => route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`asset-backed device projection fits ${width}px`, async ({ page }) => {
    await fixtures(page)
    await page.setViewportSize({ width, height: 560 })
    await page.goto('/networks?view=devices')
    await expect(page.getByText('31 devices', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('button', { name: 'Device 31', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Device 31', exact: true })
    await expect(drawer).toContainText('1030')
    await expect(drawer).toContainText('Main rack')
    await expect(drawer).toContainText('SERIAL-31')
    await expect(drawer).toContainText('Arista')
    await expect(drawer).toContainText('7050SX3')
    await expect(drawer.getByRole('link', { name: 'Placement' })).toHaveCount(0)
    await expect(drawer.getByRole('link', { name: 'Interfaces' })).toHaveCount(0)
    await expect(drawer.getByRole('button', { name: /Edit/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'New device' })).toHaveCount(0)
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
  })
}

test('device projection searches source and asset facts and preserves history URLs', async ({ page }) => {
  await fixtures(page)
  await page.goto('/networks?view=devices')
  await page.getByRole('searchbox', { name: 'Search devices' }).fill('SERIAL-31')
  await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByRole('button', { name: 'Device 31', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: 'Device 31', exact: true })
  await drawer.getByRole('link', { name: 'History', exact: true }).click()
  await expect(page).toHaveURL(/devices_section=history/)
  await page.reload()
  await expect(drawer).toContainText('No device history is available.')
})
