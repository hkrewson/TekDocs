import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
async function deviceFixtures(page: Page, denied = false, failSave = false) {
  await page.addInitScript(() => { document.cookie = `csrftoken=${crypto.randomUUID().replaceAll('-', '')}; path=/` })
  const columns = ['name', 'role', 'status', 'site', 'rack', 'rack_unit']
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const records = Array.from({ length: 31 }, (_, index) => ({ id: `device-${index + 1}`, name: `Device ${String(index + 1).padStart(2, '0')}`, role: 'switch', status: 'active', hardware_asset_id: null, hardware_asset_name: null, site_id: 'site-1', site_name: 'Campus'.repeat(40), location_id: 'room-1', location_name: 'Room'.repeat(50), rack_id: 'rack-1', rack_name: 'Equipment rack'.repeat(30), rack_unit: index + 1, rack_units: 1 }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route('**/collection-preferences/network-devices', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/networks/devices?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.has('subnet_id')).toBe(false); expect(query.has('association')).toBe(false)
    const size = Number(query.get('page_size')), pageNumber = Number(query.get('page'))
    let found = records.filter((item) => item.name.includes(query.get('q') ?? '') && (!query.get('status') || item.status === query.get('status')) && (!query.get('role') || item.role === query.get('role')))
    if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: !denied, can_create: false } })
  })
  await page.route(/\/networks\/devices\/device-\d+$/, (route) => {
    const record = records.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (!record) return route.fulfill({ status: 403, json: {} })
    if (route.request().method() === 'PATCH') {
      const values = route.request().postDataJSON() as Record<string, unknown>
      expect(values).not.toHaveProperty('hardware_asset_id')
      if ('name' in values) expect(Object.keys(values).sort()).toEqual(['name', 'role', 'status'])
      else expect(Object.keys(values).sort()).toEqual(['location_id', 'rack_id', 'rack_unit', 'rack_units', 'site_id'])
      if (failSave) return route.fulfill({ status: 409, json: { detail: 'Placement conflict. Your entries have been kept.' } })
      Object.assign(record, values)
    }
    return route.fulfill({ json: record })
  })
  await page.route('**/networks/racks?*', (route) => route.fulfill({ json: { results: [{ id: 'rack-2', name: 'New rack' }], page: 1, page_size: 25, count: 1, has_more: false } }))
  await page.route('**/networks/assignment-choices?*', (route) => route.fulfill({ json: { results: [], page: 1, page_size: 25, count: 0, has_more: false } }))
  await page.route('**/activity?*', (route) => route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
}
async function fixtures(page: Page, denied = false, failSave = false) {
  await deviceFixtures(page)
  const columns = ['name', 'kind', 'status']
  let prefs = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const records = Array.from({ length: 31 }, (_, index) => ({ id: `port-${index + 1}`, name: `Port ${String(index + 1).padStart(2, '0')}`, device_id: 'device-1', device_name: 'Device 01', kind: 'physical', status: 'active', description: 'Long cable destination '.repeat(60) }))
  await page.route('**/collection-preferences/network-interfaces', (route) => {
    if (route.request().method() === 'PUT') prefs = { ...prefs, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') prefs = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: prefs })
  })
  await page.route('**/networks/interfaces?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('device_id')).toBe('device-1'); expect(query.has('subnet_id')).toBe(false); expect(query.has('association')).toBe(false)
    const pageNumber = Number(query.get('page')), size = Number(query.get('page_size'))
    let found = records.filter((item) => item.name.includes(query.get('q') ?? '') && (!query.get('status') || item.status === query.get('status')) && (!query.get('kind') || item.kind === query.get('kind')))
    if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size).map(({ id, name, device_id, device_name, kind, status }) => ({ id, name, device_id, device_name, kind, status })), page: pageNumber, page_size: size, count: found.length, has_more: size * pageNumber < found.length, can_manage: !denied } })
  })
  await page.route('**/networks/interfaces', (route) => {
    const values = route.request().postDataJSON() as Record<string, unknown>
    expect(values.device_id).toBe('device-1')
    const record = { ...records[0], ...values, id: 'port-32' }; records.push(record)
    return route.fulfill({ status: 201, json: record })
  })
  await page.route(/\/networks\/interfaces\/port-\d+$/, (route) => {
    if (route.request().url().endsWith('port-999')) return route.fulfill({ json: { ...records[0], id: 'port-999', device_id: 'other-device' } })
    const record = records.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (!record) return route.fulfill({ status: 403, json: {} })
    if (route.request().method() === 'PATCH') {
      const values = route.request().postDataJSON() as Record<string, unknown>
      expect(Object.keys(values).sort()).toEqual(['description', 'kind', 'name', 'status'])
      if (failSave) return route.fulfill({ status: 409, json: { detail: 'Interface conflict. Your entries have been kept.' } })
      Object.assign(record, values)
    }
    return route.fulfill({ json: record })
  })
}
const url = '/networks?view=devices&devices=device-1&devices_section=interfaces'
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`interfaces stay inside the device drawer at ${width}px`, async ({ page }) => {
    await fixtures(page); await page.setViewportSize({ width, height: 600 }); await page.goto(url)
    const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true })
    await expect(drawer.getByText('31 interfaces', { exact: true })).toBeVisible()
    await drawer.getByRole('button', { name: 'Next', exact: true }).click()
    await drawer.getByRole('button', { name: 'Port 31', exact: true }).click()
    await expect(drawer.getByRole('heading', { name: 'Port 31', exact: true })).toBeFocused()
    await expect(page.getByRole('dialog')).toHaveCount(1)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.reload(); await expect(drawer.getByRole('heading', { name: 'Port 31' })).toBeVisible()
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Device 01' })).toBeVisible()
    await page.goBack(); await expect(drawer).toBeVisible()
    await drawer.getByRole('button', { name: 'Back to interfaces' }).click()
    await expect(drawer.getByRole('button', { name: 'Port 31', exact: true })).toBeFocused()
    await expect(page).toHaveURL(/interface_page=2/)
    await drawer.getByRole('searchbox', { name: 'Search interfaces' }).fill('Port 01')
    await drawer.getByRole('button', { name: 'Search', exact: true }).click()
    await expect(drawer.getByText('1 interfaces', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
test('interface creation and immediate saved dismissal retain the device binding', async ({ page }) => {
  await fixtures(page); await page.goto(url)
  const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true })
  await drawer.getByRole('button', { name: 'New interface' }).click()
  await drawer.getByRole('textbox', { name: 'Name', exact: true }).fill('New uplink')
  await drawer.getByRole('button', { name: 'Back to interfaces' }).click()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('New uplink')
  await drawer.getByRole('button', { name: 'Save interface' }).click()
  await expect(drawer.getByRole('heading', { name: 'New uplink' })).toBeVisible()
  await drawer.getByRole('button', { name: 'Edit interface' }).click()
  await drawer.getByRole('combobox', { name: 'Status', exact: true }).selectOption('disabled')
  await drawer.getByRole('button', { name: 'Save interface' }).click()
  await expect(drawer.getByRole('button', { name: 'Edit interface' })).toBeVisible()
  await page.mouse.click(10, 100); await expect(page.getByRole('dialog')).toHaveCount(0)
})
test('failed interface drafts survive touch, parent-section navigation and zoom', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 500 }, hasTouch: true })
  try {
    const page = await context.newPage(); await fixtures(page, false, true); await page.goto(`${url}&interface=port-1`)
    const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true })
    await drawer.getByRole('button', { name: 'Edit interface' }).tap()
    await drawer.getByRole('textbox', { name: 'Description' }).fill('Updated cable destination')
    await drawer.getByRole('button', { name: 'Save interface' }).tap()
    await expect(drawer.getByRole('alert')).toContainText('Interface conflict')
    await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('overview')
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByRole('textbox', { name: 'Description' })).toHaveValue('Updated cable destination')
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/interface-${test.info().project.name}.png` })
    await page.setViewportSize({ width: 1280, height: 600 }); await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.keyboard.press('Escape'); await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { await context.close() }
})
test('interfaces reject mismatched parents and respect read-only access', async ({ page }) => {
  await fixtures(page, true); await page.goto(`${url}&interface=port-999`)
  const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true })
  await expect(drawer.getByRole('alert')).toContainText('unavailable')
  await drawer.getByRole('button', { name: 'Back to interfaces' }).click()
  await expect(drawer.getByRole('button', { name: 'New interface' })).toHaveCount(0)
  await drawer.getByRole('button', { name: 'Port 01', exact: true }).click()
  await expect(drawer.getByRole('heading', { name: 'Port 01' })).toBeVisible()
  await expect(drawer.getByRole('button', { name: 'Edit interface' })).toHaveCount(0)
})
test('interface columns persist and reset; kind filters apply to the collection', async ({ page }) => {
  await fixtures(page); await page.goto(url)
  const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true })
  await drawer.getByRole('button', { name: 'Columns', exact: true }).click()
  const chooser = drawer.getByRole('form', { name: 'Columns', exact: true })
  await chooser.getByRole('checkbox', { name: 'Kind', exact: true }).uncheck()
  await chooser.getByRole('button', { name: 'Save', exact: true }).click()
  await page.reload(); await expect(drawer.getByRole('columnheader', { name: 'Kind' })).toHaveCount(0)
  await drawer.getByRole('button', { name: 'Columns', exact: true }).click()
  await chooser.getByRole('button', { name: 'Reset to defaults' }).click()
  await expect(drawer.getByRole('columnheader', { name: 'Kind' })).toBeVisible()
  await drawer.getByRole('button', { name: 'Filters', exact: true }).click()
  await drawer.locator('.filter-menu summary').filter({ hasText: 'Kind' }).click()
  await drawer.getByRole('radio', { name: 'Virtual', exact: true }).click()
  await expect(drawer.getByText('0 interfaces', { exact: true })).toBeVisible()
})
