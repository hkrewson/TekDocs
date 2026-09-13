import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function mockAssets(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Layout Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Layout MSP' }, role: 'owner', permissions: ['assets.view', 'assets.edit'],
    surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/api/v1/workspaces/msp/assets/collection?*', (route) => route.fulfill({ json: {
    results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true,
    can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false,
  } }))
  await page.route('**/collection-preferences/assets', (route) => route.fulfill({ json: { columns: ['name', 'model', 'status'], available_columns: ['name', 'model', 'status'], default_columns: ['name', 'model', 'status'], page_size: 25 } }))
  await page.route('**/assets/model-choices?*', (route) => route.fulfill({ json: { results: [] } }))
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`asset edit confirmation fits ${width}px and keeps keyboard focus`, async ({ page }) => {
    await mockAssets(page)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/assets')
    await page.getByRole('button', { name: 'New asset', exact: true }).click()
    await page.getByLabel('Asset name (optional)').fill('Field laptop in progress')
    const cancel = page.getByRole('button', { name: 'Cancel', exact: true })
    await cancel.click()
    const dialog = page.getByRole('dialog', { name: 'Unsaved changes' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Keep editing' })).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(dialog.getByRole('button', { name: 'Discard changes' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(dialog.getByRole('button', { name: 'Keep editing' })).toBeFocused()
    expect(await dialog.evaluate((element) => {
      const bounds = element.getBoundingClientRect()
      return bounds.left >= 0 && bounds.right <= innerWidth && bounds.top >= 0 && bounds.bottom <= innerHeight
        && element.scrollWidth <= element.clientWidth
    })).toBe(true)
    expect(await page.locator('body').evaluate((element) => element.style.overflow)).toBe('hidden')
    expect((await new AxeBuilder({ page }).include('.unsaved-changes-dialog').analyze()).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(cancel).toBeFocused()
    await expect(page.getByLabel('Asset name (optional)')).toHaveValue('Field laptop in progress')
    await cancel.click()
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByLabel('Asset name (optional)')).toHaveCount(0)
  })
}

test('asset edits survive browser Back until discarded and Forward stays usable', async ({ page }) => {
  await mockAssets(page)
  await page.goto('/overview')
  await page.getByRole('link', { name: 'Assets', exact: true }).click()
  await page.getByRole('button', { name: 'New asset', exact: true }).click()
  await page.getByLabel('Asset name (optional)').fill('Unsaved laptop')
  await page.evaluate(() => history.back())
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page).toHaveURL(/\/assets$/)
  await expect(page.getByLabel('Asset name (optional)')).toHaveValue('Unsaved laptop')
  await page.evaluate(() => history.back())
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(page).toHaveURL(/\/overview$/)
  await page.evaluate(() => history.forward())
  await expect(page).toHaveURL(/\/assets$/)
  await expect(page.getByRole('button', { name: 'New asset', exact: true })).toBeVisible()
  await expect(page.getByLabel('Asset name (optional)')).toHaveCount(0)
})

test('refresh uses the native unload guard and dismissing it preserves the draft', async ({ page }) => {
  await mockAssets(page)
  await page.goto('/assets')
  await page.getByRole('button', { name: 'New asset', exact: true }).click()
  await page.getByLabel('Asset name (optional)').pressSequentially('Unsaved laptop')
  const prompt = page.waitForEvent('dialog')
  // A dismissed unload can reject the navigation promise; the dialog and retained
  // draft assertions below distinguish cancellation from an unrelated failure.
  const reload = page.reload({ timeout: 5000 }).catch(() => null)
  const dialog = await prompt
  expect(dialog.type()).toBe('beforeunload')
  await dialog.dismiss()
  await expect(page.getByLabel('Asset name (optional)')).toHaveValue('Unsaved laptop')
  await reload
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await page.reload()
  await expect(page.getByRole('button', { name: 'New asset', exact: true })).toBeVisible()
})

test('hardware save includes fields edited after Keep editing', async ({ page }) => {
  await mockAssets(page)
  const hardware = {
    serial_number: '', asset_tag: '', lifecycle_state: 'in_stock', acquired_on: null, acquisition_method: '',
    acquisition_reference: '', warranty_provider: '', warranty_starts_on: null, warranty_ends_on: null, warranty_reference: '',
    assignment: { person_id: null, person_name: null, site_id: null, site_name: null, location_id: null, location_name: null, assigned_at: null },
    disposed_on: null, disposal_method: '', disposal_reason: '',
  }
  await page.route('**/api/v1/workspaces/msp/assets/collection?*', (route) => route.fulfill({ json: {
    results: [{ id: 'asset-1', name: 'Core switch', kind: 'hardware', supplier_name: 'Supplier', product_name: 'Switch', model_name: '24 ports',
      model_number: 'SW-24', model_revision: 1, specification_version: 1, specifications: {}, provenance_checksum: 'a'.repeat(64),
      documents: [], hardware, mac_addresses: [], software_installation: null }],
    page: 1, page_size: 50, count: 1, has_more: false, can_manage: true,
    can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false,
  } }))
  await page.route('**/assets/asset-1/hardware/lifecycle', (route) => route.fulfill({ json: [] }))
  await page.route('**/assets/asset-1/hardware', (route) => route.fulfill({ json: { ...hardware, ...route.request().postDataJSON() as object } }))
  await page.route('**/assets/asset-1', (route) => route.fulfill({ json: { id: 'asset-1', name: 'Core switch', kind: 'hardware', supplier_name: 'Supplier', product_name: 'Switch', model_name: '24 ports', model_number: 'SW-24', model_revision: 1, specification_version: 1, specifications: {}, provenance_checksum: 'a'.repeat(64), documents: [], hardware, mac_addresses: [], software_installation: null } }))
  await page.goto('/assets?record=asset-1')
  await page.getByRole('button', { name: 'Edit details' }).click()
  await page.getByLabel('Serial number').fill('LIVE-SN-100')
  await page.getByRole('link', { name: 'Vendors', exact: true }).click()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page.getByLabel('Serial number')).toHaveValue('LIVE-SN-100')
  await page.getByLabel('Asset tag').fill('LIVE-SW-100')
  await page.getByLabel('Lifecycle state').selectOption('in_service')
  await page.getByLabel('Acquired on').fill('2026-08-01')
  await page.getByLabel('Acquisition method').selectOption('purchase')
  await page.getByLabel('Warranty provider').fill('Supplier')
  await page.getByLabel('Warranty ends').fill('2029-08-01')
  const submitted = page.waitForRequest((request) => request.method() === 'PATCH' && request.url().endsWith('/hardware'))
  await page.getByRole('button', { name: 'Save details' }).click()
  expect((await submitted).postDataJSON()).toMatchObject({ serial_number: 'LIVE-SN-100', asset_tag: 'LIVE-SW-100', lifecycle_state: 'in_service', warranty_ends_on: '2029-08-01' })
  await expect(page.getByText('LIVE-SW-100', { exact: true })).toBeVisible()
})
