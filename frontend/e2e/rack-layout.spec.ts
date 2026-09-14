import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
async function fixtures(page: Page, denied = false, failSave = false) {
  await page.addInitScript(() => { document.cookie = `csrftoken=${crypto.randomUUID().replaceAll('-', '')}; path=/` })
  const columns = ['name', 'site', 'location', 'status', 'unit_count', 'device_count']
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const records = Array.from({ length: 31 }, (_, index) => ({ id: `rack-${index + 1}`, name: `Rack ${String(index + 1).padStart(2, '0')}`, site_id: 'site-1', site_name: 'Campus'.repeat(40), location_id: 'room-1', location_name: 'Communications room'.repeat(20), unit_count: 42, status: 'active', device_count: 31 }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route('**/collection-preferences/network-racks', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/networks/racks?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.has('subnet_id')).toBe(false)
    const size = Number(query.get('page_size')), pageNumber = Number(query.get('page'))
    let found = records.filter((item) => item.name.includes(query.get('q') ?? '') && (!query.get('status') || query.get('status') === item.status))
    if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: !denied } })
  })
  await page.route(/\/networks\/racks\/rack-\d+$/, (route) => {
    const record = records.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (!record) return route.fulfill({ status: 403, json: {} })
    if (route.request().method() === 'PATCH') {
      if (failSave) return route.fulfill({ status: 409, json: { detail: 'Record changed. Your entries have been kept.' } })
      const values = route.request().postDataJSON() as Record<string, unknown>
      expect(values.site_id).toBe('site-1'); expect(values.location_id).toBe('room-1')
      Object.assign(record, values)
    }
    return route.fulfill({ json: record })
  })
  await page.route('**/networks/devices?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('rack_id')).toBeTruthy()
    const rows = Array.from({ length: 31 }, (_, index) => ({ id: `device-${index + 1}`, name: `Switch ${index + 1}`, rack_unit: index + 1, rack_units: 1, status: 'active' })).filter((row) => row.name.includes(query.get('q') ?? ''))
    const pageNumber = Number(query.get('page')), size = Number(query.get('page_size'))
    return route.fulfill({ json: { results: rows.slice((pageNumber - 1) * size, pageNumber * size), count: rows.length, page: pageNumber, page_size: size, has_more: pageNumber * size < rows.length, can_manage: !denied } })
  })
  await page.route('**/networks/devices/device-31', (route) => route.fulfill({ json: { id: 'device-31', name: 'Switch 31', rack_id: 'rack-31', rack_unit: 31, rack_units: 1, status: 'active', role: 'switch', hardware_asset_name: null } }))
  await page.route('**/networks/assignment-choices?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('page_size')).toBe('25')
    if (query.get('kind') === 'location') expect(query.get('site_id')).toBe('site-1')
    return route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, can_manage: true } })
  })
  await page.route('**/activity?*', (route) => route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
}
async function section(page: Page, name: string, id: string, width: number) {
  const drawer = page.getByRole('dialog')
  if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption(id)
  else await drawer.getByRole('link', { name, exact: true }).click()
}
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`rack register and complete drawer fit ${width}px`, async ({ page }) => {
    await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    let deviceRequests = 0
    page.on('request', (request) => { if (request.url().includes('/networks/devices?')) deviceRequests++ })
    await page.goto('/networks?view=racks')
    await expect(page.getByText('31 racks', { exact: true })).toBeVisible()
    if (width < 768) {
      await expect(page.locator('.collection-table td[data-column="location"]').first()).toBeHidden()
      await expect(page.locator('.collection-table td[data-column="unit_count"]').first()).toBeHidden()
      await expect(page.locator('.collection-table td[data-column="status"]').first()).toBeVisible()
    }
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('button', { name: 'Rack 31', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Rack 31', exact: true })
    await expect(drawer.getByRole('heading', { name: 'Rack 31', exact: true })).toBeFocused()
    expect(deviceRequests).toBe(0)
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    await section(page, 'Devices', 'devices', width)
    await drawer.getByRole('button', { name: 'Next', exact: true }).click()
    await drawer.getByRole('button', { name: 'Switch 31', exact: true }).click()
    await expect(drawer).toContainText('Unassigned or unavailable')
    await expect(page.getByRole('dialog')).toHaveCount(1)
    await drawer.getByRole('button', { name: 'Back to installed devices' }).click()
    await expect(drawer.getByRole('button', { name: 'Switch 31', exact: true })).toBeFocused()
    await section(page, 'History', 'history', width)
    await expect(drawer).toContainText('No rack history is available.')
    await page.reload()
    await expect(drawer).toContainText('No rack history is available.')
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Rack 31' })).toBeVisible()
    await page.goBack(); await expect(drawer).toBeVisible()
    await page.goForward()
    await page.getByRole('link', { name: 'Back to racks', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Rack 31', exact: true })).toBeFocused()
    await expect(page).toHaveURL(/racks_page=2/)
    await page.getByRole('searchbox', { name: 'Search racks' }).fill('Rack 01')
    await page.locator('.collection-search').getByRole('button', { name: 'Search' }).click()
    await expect(page.getByText('1 racks', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
test('rack edits save and outside-click closes without a redundant close control', async ({ page }) => {
  await fixtures(page)
  await page.goto('/networks?view=racks&racks=rack-1')
  const drawer = page.getByRole('dialog', { name: 'Rack 01' })
  await drawer.getByRole('button', { name: 'Edit rack' }).click()
  await drawer.getByRole('combobox', { name: 'Status', exact: true }).selectOption('retired')
  await drawer.getByRole('button', { name: 'Save rack' }).click()
  await expect(drawer.getByRole('button', { name: 'Edit rack' })).toBeVisible()
  await page.mouse.click(10, 100)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
test('rack denied and unavailable records keep a return path', async ({ page }) => {
  await fixtures(page, true)
  await page.goto('/networks?view=racks&racks=rack-1&racks_full=true')
  await expect(page.getByRole('heading', { level: 1, name: 'Rack 01' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit rack' })).toHaveCount(0)
  await page.goto('/networks?view=racks&racks=rack-999')
  await expect(page.getByRole('dialog')).toContainText('unavailable')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
test('failed rack edits retain drafts through touch, tab changes and zoom', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 500 }, hasTouch: true })
  try {
    const page = await context.newPage(); await fixtures(page, false, true)
    await page.goto('/networks?view=racks&racks=rack-1')
    const drawer = page.getByRole('dialog', { name: 'Rack 01' })
    await drawer.getByRole('button', { name: 'Edit rack' }).tap()
    await drawer.getByRole('textbox', { name: 'Name', exact: true }).fill('Unsaved rack')
    await drawer.getByRole('button', { name: 'Save rack' }).tap()
    await expect(drawer.getByRole('alert')).toContainText('Record changed')
    await section(page, 'History', 'history', 390)
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Unsaved rack')
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/rack-${test.info().project.name}.png` })
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { await context.close() }
})

test('rack columns persist, reset and filters update the complete collection', async ({ page }) => {
  await fixtures(page)
  await page.goto('/networks?view=racks')
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  const chooser = page.getByRole('form', { name: 'Columns', exact: true })
  await chooser.getByRole('checkbox', { name: 'Location', exact: true }).uncheck()
  await chooser.getByRole('button', { name: 'Save', exact: true }).click()
  await page.reload()
  await expect(page.getByRole('columnheader', { name: 'Location' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  await chooser.getByRole('button', { name: 'Reset to defaults', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Location' })).toBeVisible()
  await page.getByRole('button', { name: 'Filters', exact: true }).click()
  await page.locator('.filter-menu summary').filter({ hasText: 'Status' }).click()
  await page.getByRole('radio', { name: 'Retired', exact: true }).click()
  await expect(page.getByText('0 racks', { exact: true })).toBeVisible()
})
