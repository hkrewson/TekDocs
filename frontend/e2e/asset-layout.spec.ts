import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const columns = ['name', 'model', 'status', 'assignment', 'site', 'warranty']
async function fixtures(page: Page) {
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const assets = Array.from({ length: 131 }, (_, index) => ({
    id: `asset-${index + 1}`, name: `Asset ${String(index + 1).padStart(3, '0')}${index === 0 ? ` ${'LongIdentifier'.repeat(15)}` : ''}`,
    kind: 'hardware', model_name: 'Business switch', model_number: 'SW-24', supplier_name: 'Synthetic supplier', product_name: 'Switch',
    model_revision: 1, specification_version: 1, provenance_checksum: 'a'.repeat(64), specifications: { ports: 24 }, documents: [], mac_addresses: [], software_installation: null,
    hardware: { serial_number: `SERIAL-${index + 1}`, asset_tag: '', lifecycle_state: 'in_service', acquired_on: null, acquisition_method: '', acquisition_reference: '', warranty_provider: '', warranty_starts_on: null, warranty_ends_on: '2030-01-01', warranty_reference: '', assignment: { person_name: 'Technician', site_name: 'Main office', location_name: null, person_id: null, site_id: null, location_id: null, assigned_at: null }, disposed_on: null, disposal_method: '', disposal_reason: '' },
  }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['assets.view', 'assets.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route('**/collection-preferences/assets', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/assets/collection?*', (route) => {
    const params = new URL(route.request().url()).searchParams
    const size = Number(params.get('page_size') ?? 25), pageNumber = Number(params.get('page') ?? 1)
    let found = assets.filter((asset) => `${asset.name} ${asset.hardware.serial_number}`.includes(params.get('search') ?? ''))
    if (params.get('kind') === 'software') found = []
    if (params.get('status')) found = found.filter((asset) => asset.hardware.lifecycle_state === params.get('status'))
    if (params.get('ordering')?.startsWith('-')) found = [...found].reverse()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size).map((asset) => ({ id: asset.id, name: asset.name, kind: asset.kind, model_name: asset.model_name, model_number: asset.model_number, status: asset.hardware.lifecycle_state, assignment: 'Technician', site: 'Main office', warranty_ends_on: '2030-01-01' })), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: true, can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false } })
  })
  await page.route(/\/assets\/asset-\d+$/, (route) => {
    const asset = assets.find((item) => route.request().url().endsWith(`/${item.id}`))
    return route.fulfill(asset ? { json: asset } : { status: 404, json: {} })
  })
  await page.route(/\/assets\/asset-\d+\/hardware$/, (route) => {
    const asset = assets.find((item) => route.request().url().includes(`/${item.id}/hardware`))!
    Object.assign(asset.hardware, route.request().postDataJSON() as object)
    return route.fulfill({ json: asset.hardware })
  })
  await page.route('**/assets/*/hardware/assignment-choices', (route) => route.fulfill({ json: {
    people: [{ id: 'person-2', name: 'Morgan' }], sites: [{ id: 'site-2', name: 'Branch' }], locations: [{ id: 'location-2', name: 'Office', site_id: 'site-2' }],
  } }))
  await page.route('**/assets/*/hardware/assignment', (route) => {
    const asset = assets.find((item) => route.request().url().includes(`/${item.id}/hardware`))!
    Object.assign(asset.hardware.assignment, route.request().postDataJSON(), { person_name: 'Morgan', site_name: 'Branch', location_name: 'Office' })
    return route.fulfill({ json: asset.hardware })
  })
  return assets
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Assets list, preview and record fit ${width}px`, async ({ page }) => {
    const assets = await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    const details: string[] = []
    page.on('request', (request) => { if (/\/assets\/asset-\d+$/.test(request.url())) details.push(request.url()) })
    await page.goto('/assets')
    await expect(page.getByText('131 assets', { exact: true })).toBeVisible()
    expect(details).toHaveLength(0)
    if (process.env.LAYOUT_SCREENSHOT_DIR && test.info().project.name === 'chromium') await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/assets-${width}.png`, fullPage: false })
    await page.getByRole('button', { name: 'Columns', exact: true }).click()
    await expect(page.getByRole('checkbox', { name: 'Name', exact: true })).toBeDisabled()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(page.getByRole('button', { name: assets[0].name, exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: assets[0].name, exact: true }).click()
    const drawer = page.getByRole('dialog', { name: assets[0].name })
    await expect(drawer).toBeVisible()
    expect(details).toHaveLength(1)
    await expect(drawer.getByRole('button', { name: 'Close' })).toBeFocused()
    expect(await page.locator('body').evaluate((element) => element.style.overflow)).toBe('hidden')
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    if (process.env.LAYOUT_SCREENSHOT_DIR && test.info().project.name === 'chromium') await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/preview-${width}.png` })
    await page.keyboard.press('Escape')
    await expect(drawer).toHaveCount(0)
    await expect(page.getByRole('button', { name: assets[0].name, exact: true })).toBeFocused()
    await page.getByRole('row').filter({ hasText: assets[0].name }).getByRole('link', { name: 'Open record' }).click()
    await expect(page.getByRole('heading', { name: assets[0].name })).toBeVisible()
    if (width < 768) await page.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('specifications')
    else await page.getByRole('link', { name: 'Specifications', exact: true }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (width < 768) await page.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('network')
    else await page.getByRole('link', { name: 'Network', exact: true }).click()
    await expect(page).toHaveURL(/section=network/)
    await page.reload()
    await expect(page.getByRole('heading', { name: 'MAC addresses' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('link', { name: 'Back to assets' }).click()
    await expect(page.getByText('131 assets', { exact: true })).toBeVisible()
  })
}

test('Assets searches beyond page one, clears page selection, and persists columns', async ({ page }) => {
  await fixtures(page)
  await page.goto('/assets')
  await page.getByLabel('Select this page', { exact: true }).check()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Apply', exact: true })).toHaveCount(0)
  await page.getByRole('searchbox', { name: 'Search assets' }).fill('SERIAL-131')
  await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Asset 131', exact: true })).toBeVisible()
  await expect(page).not.toHaveURL(/page=2/)
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Warranty', exact: true }).uncheck()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Warranty' })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Asset 131', exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Warranty' })).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Rows per page' }).selectOption('50')
  await expect(page).toHaveURL(/page_size=50/)
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  await page.getByRole('button', { name: 'Reset to defaults' }).click()
  await expect(page).not.toHaveURL(/page_size=/)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: 'Warranty' })).toBeVisible()
})

test('preview preserves a dirty status when closing is canceled', async ({ page }) => {
  await fixtures(page)
  await page.goto('/assets')
  await page.getByRole('button', { name: 'Asset 002', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: 'Asset 002' })
  await drawer.getByRole('combobox', { name: 'Change status' }).selectOption('repair')
  await drawer.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('combobox', { name: 'Change status' })).toHaveValue('repair')
  await drawer.getByRole('button', { name: 'Save status' }).click()
  await expect(drawer.getByRole('button', { name: 'Save status' })).toBeDisabled()
  await expect(drawer.getByRole('combobox', { name: 'Change status' })).toBeEnabled()
  await drawer.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(drawer).toHaveCount(0)
  await expect(page.getByRole('row').filter({ hasText: 'Asset 002' })).toContainText('repair')
})

test('a status update explains a record leaving the active filter and restores focus', async ({ page }) => {
  await fixtures(page)
  await page.goto('/assets?status=in_service')
  await page.getByRole('button', { name: 'Asset 002', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: 'Asset 002' })
  await drawer.getByRole('combobox', { name: 'Change status' }).selectOption('repair')
  await drawer.getByRole('button', { name: 'Save status' }).click()
  await expect(drawer.getByRole('button', { name: 'Save status' })).toBeDisabled()
  await expect(drawer.getByRole('combobox', { name: 'Change status' })).toBeEnabled()
  await drawer.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(drawer).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('no longer appears on this page')
  await expect(page.getByRole('heading', { name: 'Assets', exact: true })).toBeFocused()
})

test('closing during a pending status save keeps the preview protected', async ({ page }) => {
  await fixtures(page)
  let release = () => {}
  const pending = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/assets/asset-2/hardware', async (route) => { await pending; await route.fallback() })
  await page.goto('/assets')
  await page.getByRole('button', { name: 'Asset 002', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: 'Asset 002' })
  await drawer.getByRole('combobox', { name: 'Change status' }).selectOption('repair')
  await drawer.getByRole('button', { name: 'Save status' }).click()
  await expect(drawer.getByRole('combobox', { name: 'Change status' })).toBeDisabled()
  await drawer.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Discard changes' })).toBeDisabled()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  release()
  await expect(drawer.getByRole('combobox', { name: 'Change status' })).toBeEnabled()
  await drawer.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(drawer).toHaveCount(0)
})

test('touch preview and 200 percent CSS zoom retain usable actions', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 600 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await fixtures(page)
    await page.goto('/assets')
    await page.getByRole('button', { name: 'Asset 002', exact: true }).tap()
    await expect(page.getByRole('dialog', { name: 'Asset 002' })).toBeVisible()
    await page.getByRole('button', { name: 'Close', exact: true }).tap()
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    await page.getByRole('button', { name: 'Asset 002', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Asset 002' })
    await expect(drawer.getByRole('button', { name: 'Close', exact: true })).toBeVisible()
    expect(await drawer.evaluate((element) => { const bounds = element.getBoundingClientRect(); return element.scrollWidth <= element.clientWidth && bounds.bottom <= innerHeight + 1 && bounds.right <= innerWidth + 1 })).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  } finally { await context.close() }
})


for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`preview assignment fits ${width}px and preserves choices through canceled close`, async ({ page }) => {
    await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/assets')
    await page.getByRole('button', { name: 'Asset 002', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Asset 002' })
    await drawer.getByRole('button', { name: 'Assign hardware' }).click()
    await drawer.getByLabel('Person', { exact: true }).selectOption('person-2')
    await drawer.getByLabel('Location', { exact: true }).selectOption('location-2')
    await expect(drawer.getByLabel('Site', { exact: true })).toHaveValue('site-2')
    await drawer.getByRole('button', { name: 'Close', exact: true }).click()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByLabel('Location', { exact: true })).toHaveValue('location-2')
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    const accessibility = await new AxeBuilder({ page }).include('.collection-drawer').analyze()
    expect(accessibility.violations).toEqual([])
    await drawer.getByRole('button', { name: 'Save assignment' }).click()
    await expect(drawer.getByLabel('Change status')).toBeVisible()
    await expect(drawer.getByRole('definition').filter({ hasText: 'Morgan' })).toBeVisible()
    await drawer.getByRole('button', { name: 'Close', exact: true }).click()
    await expect(drawer).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Asset 002', exact: true })).toBeFocused()
  })
}
