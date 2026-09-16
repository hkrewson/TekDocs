import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
async function fixtures(page: Page, denied = false, failSave = false) {
  await page.addInitScript(() => { document.cookie = `csrftoken=${crypto.randomUUID().replaceAll('-', '')}; path=/` })
  const columns = ['name', 'role', 'status', 'site', 'rack', 'rack_unit']
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  let relationships: Array<Record<string, unknown>> = []
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
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: !denied, can_create: false, can_view_relationships: !denied, can_create_relationships: !denied, can_archive_relationships: !denied } })
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
  await page.route('**/api/v1/entities/search?*', (route) => route.fulfill({ json: { results: [{ id: 'device-2', display_name: 'Device 02', entity_type: 'network_device', visibility: 'msp_private', workspace_label: 'Synthetic MSP', eligible_link_types: ['connected_to', 'related_to'] }], page: 1, page_size: 15, count: 1, has_more: false } }))
  await page.route(/\/api\/v1\/entities\/device-\d+\/links(?:\/link-1)?$/, (route) => {
    if (route.request().method() === 'POST') {
      relationships = [{ id: 'link-1', link_type: 'connected_to', label: 'Connected to', direction: 'outgoing', source_id: 'device-1', target_id: 'device-2', related_entity: { id: 'device-2', display_name: 'Device 02', entity_type: 'network_device', visibility: 'msp_private', workspace_label: 'Synthetic MSP', eligible_link_types: ['connected_to', 'related_to'] }, created_at: '2026-09-16T12:00:00Z' }]
      return route.fulfill({ json: relationships[0] })
    }
    if (route.request().method() === 'DELETE') { relationships = []; return route.fulfill({ status: 204 }) }
    return route.fulfill({ json: { relationships } })
  })
  await page.route('**/activity?*', (route) => route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
}
async function section(page: Page, name: string, id: string, width: number) {
  const drawer = page.getByRole('dialog')
  if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption(id)
  else await drawer.getByRole('link', { name, exact: true }).click()
}
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`device register and full record fit ${width}px`, async ({ page }) => {
    await fixtures(page); await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks?view=devices')
    await expect(page.getByText('31 devices', { exact: true })).toBeVisible()
    if (width < 768) { await expect(page.locator('.collection-table td[data-column="site"]').first()).toBeHidden(); await expect(page.locator('.collection-table td[data-column="status"]').first()).toBeVisible() }
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('button', { name: 'Device 31', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Device 31', exact: true })
    await expect(drawer.getByRole('heading', { name: 'Device 31', exact: true })).toBeFocused()
    await expect(drawer).toContainText('Unassigned or unavailable')
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    await section(page, 'Placement', 'placement', width)
    await expect(drawer).toContainText('Occupied units')
    await section(page, 'Relationships', 'relationships', width)
    await expect(drawer).toContainText('No logical relationships have been added.')
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await section(page, 'History', 'history', width)
    await expect(drawer).toContainText('No device history is available.')
    await page.reload(); await expect(drawer).toContainText('No device history is available.')
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Device 31' })).toBeVisible()
    await page.goBack(); await expect(drawer).toBeVisible(); await page.goForward()
    await page.getByRole('link', { name: 'Back to devices', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Device 31', exact: true })).toBeFocused()
    await expect(page).toHaveURL(/devices_page=2/)
    await page.getByRole('searchbox', { name: 'Search devices' }).fill('Device 01')
    await page.locator('.collection-search').getByRole('button', { name: 'Search' }).click()
    await expect(page.getByText('1 devices', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
test('device fact saves dismiss immediately without changing bindings', async ({ page }) => {
  await fixtures(page); await page.goto('/networks?view=devices&devices=device-1')
  const drawer = page.getByRole('dialog', { name: 'Device 01' })
  await drawer.getByRole('button', { name: 'Edit device details' }).click()
  await drawer.getByRole('combobox', { name: 'Status', exact: true }).selectOption('offline')
  await drawer.getByRole('button', { name: 'Save device', exact: true }).click()
  await expect(drawer.getByRole('button', { name: 'Edit device details' })).toBeVisible()
  await page.mouse.click(10, 100); await expect(page.getByRole('dialog')).toHaveCount(0)
})
test('device relationships create, archive and guard an unfinished search', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 600 }, hasTouch: true })
  try {
    const page = await context.newPage(); await fixtures(page)
    await page.goto('/networks?view=devices&devices=device-1&devices_section=relationships')
    const drawer = page.getByRole('dialog', { name: 'Device 01' })
    await expect(drawer).toContainText('No logical relationships have been added.')
    await drawer.getByRole('button', { name: 'Add relationship' }).tap()
    await drawer.getByRole('searchbox', { name: 'Find a network device' }).fill('Device 02')
    await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('history')
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByRole('searchbox', { name: 'Find a network device' })).toHaveValue('Device 02')
    await drawer.getByRole('combobox', { name: 'Related device' }).selectOption('device-2')
    await drawer.getByRole('button', { name: 'Add relationship' }).tap()
    await expect(drawer).toContainText('Device 02')
    await page.reload(); await expect(drawer).toContainText('Device 02')
    await drawer.getByRole('button', { name: 'Archive relationship with Device 02' }).tap()
    await expect(drawer).toContainText('No logical relationships have been added.')
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
  } finally { await context.close() }
})
test('device denied and unavailable records keep a return path', async ({ page }) => {
  await fixtures(page, true); await page.goto('/networks?view=devices&devices=device-1&devices_full=true')
  await expect(page.getByRole('heading', { level: 1, name: 'Device 01' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit device details' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'New device' })).toHaveCount(0)
  await page.goto('/networks?view=devices&devices=device-999')
  await expect(page.getByRole('dialog')).toContainText('unavailable')
  await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0)
})
test('failed placement survives touch, section changes and zoom', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 500 }, hasTouch: true })
  try {
    const page = await context.newPage(); await fixtures(page, false, true)
    await page.goto('/networks?view=devices&devices=device-1&devices_section=placement')
    const drawer = page.getByRole('dialog', { name: 'Device 01' })
    await drawer.getByRole('button', { name: 'Edit placement' }).tap()
    await drawer.getByRole('combobox', { name: 'Rack results' }).selectOption('rack-2')
    await drawer.getByRole('spinbutton', { name: 'Starting unit' }).fill('10')
    await drawer.getByRole('button', { name: 'Save placement' }).tap()
    await expect(drawer.getByRole('alert')).toContainText('Placement conflict')
    await section(page, 'History', 'history', 390)
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByRole('spinbutton', { name: 'Starting unit' })).toHaveValue('10')
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/device-${test.info().project.name}.png` })
    await page.setViewportSize({ width: 1280, height: 600 }); await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.keyboard.press('Escape'); await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { await context.close() }
})
test('device preferences reset and role filtering use the full collection', async ({ page }) => {
  await fixtures(page); await page.goto('/networks?view=devices')
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  const chooser = page.getByRole('form', { name: 'Columns', exact: true })
  await chooser.getByRole('checkbox', { name: 'Starting unit', exact: true }).uncheck()
  await chooser.getByRole('button', { name: 'Save', exact: true }).click()
  await page.reload(); await expect(page.getByRole('columnheader', { name: 'Starting unit' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  await chooser.getByRole('button', { name: 'Reset to defaults', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Starting unit' })).toBeVisible()
  await page.getByRole('button', { name: 'Filters', exact: true }).click()
  await page.locator('.filter-menu summary').filter({ hasText: 'Role' }).click()
  await page.getByRole('radio', { name: 'Router', exact: true }).click()
  await expect(page.getByText('0 devices', { exact: true })).toBeVisible()
})
