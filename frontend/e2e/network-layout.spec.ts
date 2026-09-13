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

async function addressFixtures(page: Page) {
  await fixtures(page)
  const columns = ['name', 'status', 'dns_name']
  let preferences = { columns, default_columns: columns, available_columns: columns, page_size: 25 }
  await page.route('**/collection-preferences/network-addresses', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, default_columns: columns, available_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  const addresses = Array.from({ length: 31 }, (_, index) => ({ id: `ip-${index + 1}`, address: `10.55.1.${index + 1}`, subnet_id: 'network-2', status: 'active', dns_name: `host-${index + 1}.example.invalid`, description: 'Operational address', hardware_asset_id: 'asset-1', hardware_asset_name: 'Firewall', interface_id: 'interface-1', interface_name: 'eth0' }))
  await page.route('**/api/v1/workspaces/**/networks/ip-addresses?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('subnet_id')).toBe('network-2')
    expect(query.get('summary')).toBe('true')
    const found = addresses.filter((item) => item.dns_name.includes(query.get('q') ?? ''))
    const pageNumber = Number(query.get('page')), size = Number(query.get('page_size'))
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: true } })
  })
  await page.route(/\/ip-addresses\/ip-\d+$/, (route) => {
    const record = addresses.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (route.request().method() === 'PATCH') {
      const values = route.request().postDataJSON() as Record<string, unknown>
      expect(values).not.toHaveProperty('hardware_asset_id')
      expect(values).not.toHaveProperty('interface_id')
      expect(values).not.toHaveProperty('subnet_id')
      return route.fulfill({ status: 409, json: { detail: 'Address changed. Your entries have been kept.' } })
    }
    return route.fulfill(record ? { json: record } : { status: 404, json: {} })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Network child addresses fit ${width}px and retain direct navigation`, async ({ page }) => {
    await addressFixtures(page)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks?preview=network-2&section=addresses')
    const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
    await expect(drawer.getByText('31 addresses', { exact: true })).toBeVisible()
    await drawer.getByRole('button', { name: 'Next', exact: true }).click()
    await drawer.getByRole('button', { name: '10.55.1.26', exact: true }).click()
    await expect(drawer).toContainText('host-26.example.invalid')
    await expect(page.getByRole('dialog')).toHaveCount(1)
    await page.reload()
    await expect(drawer).toContainText('host-26.example.invalid')
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    await drawer.getByRole('button', { name: 'Back to addresses' }).click()
    await expect(drawer.getByRole('button', { name: '10.55.1.26', exact: true })).toBeFocused()
    await drawer.getByRole('searchbox', { name: 'Search addresses' }).fill('host-31.')
    await drawer.locator('.address-search').getByRole('button', { name: 'Search', exact: true }).click()
    await expect(drawer.getByRole('button', { name: '10.55.1.31', exact: true })).toBeVisible()
    await expect(page).not.toHaveURL(/address_page=2/)
  })
}

test('Address conflicts retain edits and guard drawer dismissal without clearing assignments', async ({ page }) => {
  await addressFixtures(page)
  await page.goto('/networks?preview=network-2&section=addresses&address=ip-1')
  const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
  await drawer.getByRole('button', { name: 'Edit address', exact: true }).click()
  await drawer.getByRole('textbox', { name: 'DNS name', exact: true }).fill('unsaved.example.invalid')
  await drawer.getByRole('button', { name: 'Save address', exact: true }).click()
  await expect(drawer.getByRole('alert')).toContainText('Your entries have been kept')
  await page.mouse.click(10, 100)
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'DNS name', exact: true })).toHaveValue('unsaved.example.invalid')
  await drawer.getByRole('link', { name: 'Overview', exact: true }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(drawer).toContainText('10.55.1.1–10.55.1.254')
})

test('Address columns persist and foreign-parent details stay unavailable', async ({ page }) => {
  await addressFixtures(page)
  await page.goto('/networks?preview=network-2&section=addresses')
  const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
  await drawer.getByRole('button', { name: 'Columns', exact: true }).click()
  await drawer.getByRole('checkbox', { name: 'DNS name', exact: true }).uncheck()
  await drawer.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(drawer.getByRole('columnheader', { name: 'DNS name' })).toHaveCount(0)
  await page.reload()
  await expect(drawer.getByText('31 addresses', { exact: true })).toBeVisible()
  await expect(drawer.getByRole('columnheader', { name: 'DNS name' })).toHaveCount(0)
  await page.route('**/ip-addresses/ip-1', (route) => route.fulfill({ json: { id: 'ip-1', address: '10.0.0.1', subnet_id: 'another-parent', status: 'active', dns_name: 'foreign-parent.invalid', description: '' } }))
  await drawer.getByRole('button', { name: '10.55.1.1', exact: true }).click()
  await expect(drawer.getByRole('alert')).toContainText('unavailable')
  await expect(drawer).not.toContainText('foreign-parent.invalid')
  await drawer.getByRole('button', { name: 'Back to addresses' }).click()
  await expect(drawer.getByText('31 addresses', { exact: true })).toBeVisible()
})

test('Address editor supports touch and 200 percent zoom', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 600 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await addressFixtures(page)
    await page.goto('/networks?preview=network-2&section=addresses&address=ip-1')
    const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
    await drawer.getByRole('button', { name: 'Edit address', exact: true }).tap()
    await expect(drawer.getByRole('textbox', { name: 'IP address', exact: true })).toHaveJSProperty('required', true)
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/address-mobile-${test.info().project.name}.png` })
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    await expect(drawer.getByRole('button', { name: 'Save address', exact: true })).toBeVisible()
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  } finally { await context.close() }
})

async function wirelessFixtures(page: Page, failSave = false, standalone = false, allowParent = false) {
  const parents = await fixtures(page)
  const columns = standalone ? ['name', 'network', 'status', 'security'] : ['name', 'status', 'purpose', 'security']
  let preferences = { columns, default_columns: columns, available_columns: columns, page_size: 25 }
  await page.route(`**/collection-preferences/${standalone ? 'wireless-register' : 'network-wireless'}`, (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, default_columns: columns, available_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  const records = Array.from({ length: 31 }, (_, index) => ({ id: `wifi-${index + 1}`, ssid: `Office ${String(index + 1).padStart(2, '0')}`, subnet_id: standalone && index === 30 ? null : 'network-2', subnet_cidr: standalone && index === 30 ? null : '10.55.1.0/24', status: index === 30 ? 'disabled' : 'active', purpose: 'corporate', security: 'wpa3_enterprise', hidden: false, client_isolation: true, description: 'Wireless documentation '.repeat(50), site_id: 'site-1', site_name: 'Headquarters', vlan_id: 'vlan-1', vlan_name: 'Office VLAN', vlan_number: 20 }))
  await page.route('**/api/v1/workspaces/**/networks/wireless?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('subnet_id')).toBe(standalone ? null : 'network-2')
    expect(query.get('summary')).toBe('true')
    let found = records.filter((item) => (!query.get('subnet_id') || item.subnet_id === query.get('subnet_id')) && `${item.ssid} ${item.subnet_cidr ?? ''}`.includes(query.get('q') ?? '') && (!query.get('status') || query.get('status') === item.status) && (!query.get('association') || (query.get('association') === 'unassigned' ? !item.subnet_id : Boolean(item.subnet_id))))
    if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
    const size = Number(query.get('page_size')), number = Number(query.get('page'))
    return route.fulfill({ json: { results: found.slice((number - 1) * size, number * size).map((item) => ({ ...item, description: undefined })), count: found.length, page: number, page_size: size, has_more: number * size < found.length, can_manage: true } })
  })
  await page.route(/\/wireless\/wifi-\d+$/, (route) => {
    const record = records.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (!record) return route.fulfill({ status: 404, json: {} })
    if (route.request().method() === 'PATCH') {
      const values = route.request().postDataJSON() as Record<string, unknown>
      for (const key of ['site_id', 'vlan_id', ...(!allowParent ? ['subnet_id'] : [])]) expect(values).not.toHaveProperty(key)
      if (failSave) return route.fulfill({ status: 409, json: { detail: 'Wireless record changed. Your entries have been kept.' } })
      Object.assign(record, values)
      if ('subnet_id' in values) record.subnet_cidr = parents.find((item) => item.id === values.subnet_id)?.cidr ?? null
    }
    return route.fulfill({ json: record })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Wireless child records fit ${width}px and preserve full-page links`, async ({ page }) => {
    await wirelessFixtures(page)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks?preview=network-2')
    const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
    if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('wireless')
    else await drawer.getByRole('link', { name: 'Wireless', exact: true }).click()
    await expect(drawer.getByText('31 wireless networks', { exact: true })).toBeVisible()
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await drawer.getByRole('button', { name: 'Next', exact: true }).click()
    await drawer.getByRole('button', { name: 'Office 26', exact: true }).click()
    await expect(drawer).toContainText('Headquarters')
    await expect(page.getByRole('dialog')).toHaveCount(1)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.reload()
    await expect(drawer.getByRole('heading', { name: 'Office 26', exact: true })).toBeVisible()
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page).toHaveURL(/record=network-2/)
    await expect(page).toHaveURL(/wireless=wifi-26/)
    await expect(page.getByRole('heading', { name: 'Office 26', exact: true })).toBeVisible()
    await page.goBack()
    await expect(drawer).toBeVisible()
    await drawer.getByRole('button', { name: 'Back to wireless networks' }).click()
    await expect(drawer.getByRole('button', { name: 'Office 26', exact: true })).toBeFocused()
    await drawer.getByRole('searchbox', { name: 'Search wireless networks' }).fill('Office 31')
    await drawer.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
    await expect(drawer.getByRole('button', { name: 'Office 31', exact: true })).toBeVisible()
    await expect(page).not.toHaveURL(/wireless_page=2/)
  })
}

test('Wireless columns persist, filters clear, and failed edits retain values', async ({ page }) => {
  await wirelessFixtures(page, true)
  await page.goto('/networks?preview=network-2&section=wireless&wireless_status=disabled')
  const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
  await expect(drawer.getByText('1 wireless networks', { exact: true })).toBeVisible()
  await drawer.getByRole('button', { name: 'Status: Disabled ×', exact: true }).click()
  await expect(drawer.getByText('31 wireless networks', { exact: true })).toBeVisible()
  await drawer.getByRole('button', { name: 'Columns', exact: true }).click()
  await drawer.getByRole('checkbox', { name: 'Purpose', exact: true }).uncheck()
  await drawer.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(drawer.getByRole('columnheader', { name: 'Purpose' })).toHaveCount(0)
  await page.reload()
  await expect(drawer.getByText('31 wireless networks', { exact: true })).toBeVisible()
  await expect(drawer.getByRole('columnheader', { name: 'Purpose' })).toHaveCount(0)
  await drawer.getByRole('button', { name: 'Office 01', exact: true }).click()
  await drawer.getByRole('button', { name: 'Edit wireless network', exact: true }).click()
  await drawer.getByRole('textbox', { name: 'SSID', exact: true }).fill('Unsaved SSID')
  await drawer.getByRole('button', { name: 'Save wireless network', exact: true }).click()
  await expect(drawer.getByRole('alert')).toContainText('Your entries have been kept')
  await page.mouse.click(10, 100)
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'SSID', exact: true })).toHaveValue('Unsaved SSID')
  await drawer.getByRole('link', { name: 'Overview', exact: true }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(drawer).toContainText('10.55.1.1–10.55.1.254')
})

test('Wireless editing supports touch, short screens and zoom', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 600 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await wirelessFixtures(page)
    await page.goto('/networks?preview=network-2&section=wireless&wireless=wifi-1')
    const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
    await drawer.getByRole('button', { name: 'Edit wireless network', exact: true }).tap()
    await drawer.getByRole('combobox', { name: 'Status', exact: true }).selectOption('disabled')
    await drawer.getByRole('button', { name: 'Save wireless network', exact: true }).tap()
    await expect(drawer.getByRole('button', { name: 'Edit wireless network', exact: true })).toBeVisible()
    await page.reload()
    await expect(drawer.locator('dd').filter({ hasText: /^Disabled$/ })).toBeVisible()
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/wireless-mobile-${test.info().project.name}.png` })
    await page.setViewportSize({ width: 1280, height: 500 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    await drawer.getByRole('button', { name: 'Edit wireless network', exact: true }).click()
    await expect(drawer.getByRole('button', { name: 'Save wireless network', exact: true })).toBeVisible()
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  } finally { await context.close() }
})

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Workspace Wireless register fits ${width}px and restores list context`, async ({ page }) => {
    await wirelessFixtures(page, false, true)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks')
    await page.getByRole('navigation', { name: 'Network views' }).getByRole('link', { name: 'Wireless', exact: true }).click()
    await expect(page.getByText('31 wireless networks', { exact: true })).toBeVisible()
    await page.getByRole('searchbox', { name: 'Search wireless networks' }).fill('Office 31')
    await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
    await page.getByRole('button', { name: 'Office 31', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Office 31', exact: true })
    await expect(drawer).toContainText('No parent network')
    await expect(page.getByRole('dialog')).toHaveCount(1)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('history')
    else await drawer.getByRole('link', { name: 'History', exact: true }).click()
    await expect(drawer).toContainText('No wireless network history is available.')
    await page.reload()
    await expect(drawer).toContainText('No wireless network history is available.')
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Office 31' })).toBeVisible()
    await page.goBack()
    await expect(drawer).toBeVisible()
    await page.goForward()
    await expect(page.getByRole('heading', { level: 1, name: 'Office 31' })).toBeVisible()
    await page.getByRole('link', { name: 'Back to wireless networks', exact: true }).click()
    await expect(page.getByRole('searchbox', { name: 'Search wireless networks' })).toHaveValue('Office 31')
    await expect(page.getByRole('button', { name: 'Office 31', exact: true })).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('Workspace Wireless association filters and unavailable direct records', async ({ page }) => {
  await wirelessFixtures(page, false, true)
  await page.goto('/networks?view=wireless&ssid_association=unassigned')
  await expect(page.getByText('1 wireless networks', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Network association: No parent network ×' }).click()
  await expect(page.getByText('31 wireless networks', { exact: true })).toBeVisible()
  await page.goto('/networks?view=wireless&ssid=wifi-999')
  await expect(page.getByRole('dialog')).toContainText('unavailable')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('Workspace Wireless guards failed edits on touch and zoomed screens', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 500 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await wirelessFixtures(page, true, true)
    await page.goto('/networks?view=wireless&ssid=wifi-31')
    const drawer = page.getByRole('dialog', { name: 'Office 31', exact: true })
    await drawer.getByRole('button', { name: 'Edit wireless network', exact: true }).tap()
    await drawer.getByLabel('SSID', { exact: true }).fill('Unsaved wireless')
    await drawer.getByRole('button', { name: 'Save wireless network', exact: true }).tap()
    await expect(drawer.getByRole('alert')).toContainText('Wireless record changed')
    await drawer.getByRole('link', { name: 'Back to wireless networks', exact: true }).tap()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByLabel('SSID', { exact: true })).toHaveValue('Unsaved wireless')
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/wireless-register-${test.info().project.name}.png` })
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    await expect(drawer.getByRole('button', { name: 'Save wireless network' })).toBeVisible()
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { await context.close() }
})

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Wireless parent assignment fits ${width}px and explains leaving the active filter`, async ({ page }) => {
    await wirelessFixtures(page, false, true, true)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks?view=wireless&ssid_association=unassigned&ssid=wifi-31')
    const drawer = page.getByRole('dialog', { name: 'Office 31', exact: true })
    await drawer.getByRole('button', { name: 'Change parent network' }).click()
    await expect(drawer.getByRole('heading', { name: 'Change parent network' })).toBeFocused()
    await drawer.getByRole('searchbox', { name: 'Search parent networks' }).fill('LAN 131')
    await drawer.getByRole('button', { name: 'Search', exact: true }).click()
    await drawer.getByRole('combobox', { name: 'Matching parent networks', exact: true }).selectOption('network-131')
    await expect(drawer.getByRole('button', { name: 'Edit wireless network' })).toHaveCount(0)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await drawer.getByRole('button', { name: 'Save parent network' }).click()
    await expect(drawer.getByRole('button', { name: 'Change parent network' })).toBeVisible()
    await expect(drawer).toContainText('10.55.130.0/24')
    await expect(drawer.getByRole('status')).toContainText('no longer appears on this page')
    await page.reload()
    await expect(drawer).toContainText('10.55.130.0/24')
    await drawer.getByRole('button', { name: 'Change parent network' }).click()
    await drawer.getByRole('button', { name: 'Use no parent network' }).click()
    await drawer.getByRole('button', { name: 'Save parent network' }).click()
    await expect(drawer.getByRole('button', { name: 'Change parent network' })).toBeVisible()
    await expect(drawer).toContainText('No parent network')
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByText('1 wireless networks', { exact: true })).toBeVisible()
  })
}

test('Parent-scoped wireless reassignment returns to its owning collection', async ({ page }) => {
  await wirelessFixtures(page, false, false, true)
  await page.goto('/networks?preview=network-2&section=wireless&wireless=wifi-1')
  const drawer = page.getByRole('dialog', { name: 'LAN 002', exact: true })
  await drawer.getByRole('button', { name: 'Change parent network' }).click()
  await drawer.getByRole('button', { name: 'Use no parent network' }).click()
  await drawer.getByRole('button', { name: 'Save parent network' }).click()
  await expect(drawer.getByText('30 wireless networks', { exact: true })).toBeVisible()
  await expect(drawer).toContainText('no longer appears on this page')
  await expect(drawer.getByRole('button', { name: 'Office 01', exact: true })).toHaveCount(0)
  await expect(page).not.toHaveURL(/wireless=wifi-1/)
})

test('Wireless parent failures preserve selection and guard touch navigation', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 500 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await wirelessFixtures(page, true, true, true)
    await page.goto('/networks?view=wireless&ssid=wifi-31')
    const drawer = page.getByRole('dialog', { name: 'Office 31', exact: true })
    await drawer.getByRole('button', { name: 'Change parent network' }).tap()
    await drawer.getByRole('combobox', { name: 'Matching parent networks', exact: true }).selectOption('network-2')
    await drawer.getByRole('button', { name: 'Save parent network' }).tap()
    await expect(drawer.getByRole('alert')).toContainText('Wireless record changed')
    await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('history')
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByRole('combobox', { name: 'Matching parent networks', exact: true })).toHaveValue('network-2')
    if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/wireless-parent-${test.info().project.name}.png` })
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { await context.close() }
})
