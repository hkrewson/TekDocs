import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function fixtures(page: Page, denied = false) {
  await page.addInitScript(() => { document.cookie = `csrftoken=${crypto.randomUUID().replaceAll('-', '')}; path=/` })
  const columns = ['name', 'location', 'vlan', 'cidr']
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const records = Array.from({ length: 131 }, (_, index) => ({ id: `network-${index + 1}`, name: `LAN ${String(index + 1).padStart(3, '0')}${index === 0 ? ' LongIdentifier'.repeat(25) : ''}`, location_id: 'location-1', location_name: 'Server room', site_name: 'Headquarters', description: 'Managed network', cidr: `10.55.${index}.0/24`, vlan: index === 130 ? 30 : 20, gateway: `10.55.${index}.1`, use_full_range: true, range_start: `10.55.${index}.1`, range_end: `10.55.${index}.254`, primary_dns: '9.9.9.9', secondary_dns: '1.1.1.1', notes: 'Details stay with the selected record.' }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route('**/collection-preferences/networks', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/api/v1/workspaces/**/networks?*', (route) => {
    const q = new URL(route.request().url()).searchParams
    expect(q.get('summary')).toBe('true')
    const size = Number(q.get('page_size')), number = Number(q.get('page'))
    let found = records.filter((item) => `${item.name} ${item.cidr}`.includes(q.get('q') ?? '') && (!q.get('vlan') || String(item.vlan) === q.get('vlan')))
    if (q.get('ordering')?.startsWith('-')) found = [...found].reverse()
    return route.fulfill({ json: { results: found.slice((number - 1) * size, number * size).map((item) => ({ ...item, notes: undefined, description: undefined })), count: found.length, page: number, page_size: size, has_more: number * size < found.length, can_manage: !denied } })
  })
  await page.route(/\/networks\/network-\d+$/, (route) => {
    const record = records.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (route.request().method() === 'PATCH') return route.fulfill({ status: 409, json: { detail: 'Network changed. Your entries have been kept.' } })
    return route.fulfill(record ? { json: record } : { status: 403, json: {} })
  })
  await page.route('**/networks/choices', (route) => route.fulfill({ json: { sites: [{ id: 'site-1', name: 'Headquarters' }], locations: [{ id: 'location-1', name: 'Server room', site_id: 'site-1' }], racks: [], hardware_assets: [] } }))
  await page.route('**/activity?*', (route) => route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
  return records
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Networks collection and full record fit ${width}px`, async ({ page }) => {
    const records = await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    const details: string[] = []
    page.on('request', (request) => { if (/\/networks\/network-\d+$/.test(request.url())) details.push(request.url()) })
    await page.goto('/networks')
    await expect(page.getByText('131 networks', { exact: true })).toBeVisible()
    expect(details).toHaveLength(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: records[0].name, exact: true }).click()
    const drawer = page.getByRole('dialog', { name: records[0].name, exact: true })
    await expect(drawer.getByRole('heading', { level: 2, name: records[0].name })).toBeFocused()
    await expect(drawer).toContainText('10.55.0.1–10.55.0.254')
    expect(details).toHaveLength(1)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('history')
    else await drawer.getByRole('link', { name: 'History', exact: true }).click()
    await expect(drawer).toContainText('No network history is available.')
    await page.reload()
    await expect(drawer).toContainText('No network history is available.')
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page).toHaveURL(/record=network-1.*section=history/)
    await expect(page.getByRole('heading', { level: 1, name: records[0].name })).toBeFocused()
    await page.getByRole('link', { name: 'Back to networks', exact: true }).click()
    await page.getByRole('button', { name: 'LAN 002', exact: true }).click()
    const second = page.getByRole('dialog', { name: 'LAN 002', exact: true })
    await expect(second).toBeVisible()
    if (width < 768) await second.getByRole('link', { name: 'Back to networks' }).click()
    else await page.mouse.click(10, 100)
    await expect(second).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'LAN 002', exact: true })).toBeFocused()
  })
}

test('Networks search beyond page one, persist columns and guard a failed edit', async ({ page }) => {
  await fixtures(page)
  await page.goto('/networks')
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('button', { name: 'LAN 026', exact: true })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search networks' }).fill('10.55.130.')
  await page.locator('.collection-search').getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('button', { name: 'LAN 131', exact: true })).toBeVisible()
  await expect(page).not.toHaveURL(/page=2/)
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Location', exact: true }).uncheck()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Location' })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('button', { name: 'LAN 131', exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Location' })).toHaveCount(0)
  await page.getByRole('button', { name: 'LAN 131', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: 'LAN 131', exact: true })
  await drawer.getByRole('button', { name: 'Edit network', exact: true }).click()
  await drawer.getByRole('textbox', { name: 'Name', exact: true }).fill('Unsaved LAN')
  await drawer.getByRole('button', { name: 'Save network' }).click()
  await expect(drawer.getByRole('alert')).toContainText('Your entries have been kept')
  await drawer.getByRole('link', { name: 'History' }).click()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Unsaved LAN')
  await page.mouse.click(10, 100)
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(drawer).toHaveCount(0)
})

test('Networks deny edits and retain a return path for unavailable records', async ({ page }) => {
  await fixtures(page, true)
  await page.goto('/networks?preview=network-2')
  const drawer = page.getByRole('dialog', { name: 'LAN 002' })
  await expect(drawer).toContainText('10.55.1.1')
  await expect(drawer.getByRole('button', { name: 'Edit network' })).toHaveCount(0)
  await page.goto('/networks?record=network-999')
  await expect(page.getByRole('alert')).toContainText('unavailable')
  await page.getByRole('link', { name: 'Back to networks' }).click()
  await expect(page.getByText('131 networks', { exact: true })).toBeVisible()
})

test('Network editing fits touch screens and 200 percent CSS zoom', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 600 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await fixtures(page)
    await page.goto('/networks')
    await page.getByRole('button', { name: 'LAN 002', exact: true }).tap()
    const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
    await drawer.getByRole('button', { name: 'Edit network' }).tap()
    await drawer.getByLabel('Use the full usable address range').uncheck()
    await expect(drawer.getByLabel('Assignable range start')).toHaveJSProperty('required', true)
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/network-mobile-${test.info().project.name}.png` })
    await drawer.getByRole('link', { name: 'Back to networks' }).tap()
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(drawer).toHaveCount(0)
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    await page.getByRole('button', { name: 'LAN 002', exact: true }).click()
    await expect(drawer).toBeVisible()
    expect(await drawer.evaluate((element) => { const bounds = element.getBoundingClientRect(); return element.scrollWidth <= element.clientWidth && bounds.right <= innerWidth + 1 && bounds.bottom <= innerHeight + 1 })).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  } finally { await context.close() }
})
