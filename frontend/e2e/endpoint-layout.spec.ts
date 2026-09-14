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
async function interfaceFixtures(page: Page, denied = false, failSave = false) {
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
async function fixtures(page: Page, denied = false, failSave = false) {
  await interfaceFixtures(page)
  for (const kind of ['ip', 'mac'] as const) {
    const columns = kind === 'ip' ? ['name', 'status', 'dns_name'] : ['name']
    let prefs = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    const rows = Array.from({ length: 62 }, (_, index) => ({ id: `${kind}-${index + 1}`, address: kind === 'ip' ? `192.0.2.${index + 1}` : `02:00:00:00:00:${(index + 1).toString(16).padStart(2, '0')}`, interface_id: index < 31 ? 'port-1' : null, interface_name: index < 31 ? 'Port 01' : null, hardware_asset_id: null, hardware_asset_name: null, description: `Cable ${String(index + 1).padStart(2, '0')} ` + 'Long destination '.repeat(60), ...(kind === 'ip' ? { subnet_id: 'subnet-1', subnet_cidr: '192.0.2.0/24', status: 'active', dns_name: '' } : {}) }))
    await page.route(`**/collection-preferences/interface-${kind}-addresses`, (route) => {
      if (route.request().method() === 'PUT') prefs = { ...prefs, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
      if (route.request().method() === 'DELETE') prefs = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
      return route.fulfill({ json: prefs })
    })
    await page.route(`**/networks/${kind}-addresses?*`, (route) => {
      const query = new URL(route.request().url()).searchParams
      expect(query.has('subnet_id')).toBe(false)
      expect(query.get('summary')).toBe('true')
      expect(query.get('unassigned') === 'true' || query.get('interface_id') === 'port-1').toBe(true)
      const size = Number(query.get('page_size')), pageNumber = Number(query.get('page'))
      let found = rows.filter((item) => (query.get('unassigned') === 'true' ? item.interface_id === null : item.interface_id === query.get('interface_id')) && (item.address.includes(query.get('q') ?? '') || item.description.includes(query.get('q') ?? '')) && (!query.get('status') || item.status === query.get('status')))
      if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
      return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size).map((row) => { const summary = { ...row }; delete (summary as { description?: string }).description; return summary }), page: pageNumber, page_size: size, count: found.length, has_more: pageNumber * size < found.length, can_manage: !denied } })
    })
    await page.route(new RegExp(`/networks/${kind}-addresses/${kind}-\\d+$`), (route) => {
      const id = route.request().url().split('/').pop()
      if (id === `${kind}-999`) return route.fulfill({ json: { ...rows[0], id, interface_id: 'port-2' } })
      const record = rows.find((row) => row.id === id)
      if (!record) return route.fulfill({ status: 403, json: {} })
      if (route.request().method() === 'PATCH') {
        const values = route.request().postDataJSON() as Record<string, unknown>
        expect(values).not.toHaveProperty('hardware_asset_id'); expect(values).not.toHaveProperty('subnet_id')
        if ('interface_id' in values) {
          expect(Object.keys(values).sort()).toEqual(['expected_interface_id', 'interface_id'])
          expect(values.expected_interface_id).toBe(record.interface_id)
        } else expect(Object.keys(values).sort()).toEqual(kind === 'ip' ? ['address', 'description', 'dns_name', 'status'] : ['address', 'description'])
        if (failSave) return route.fulfill({ status: 409, json: { detail: 'Assignment changed. Your entries have been kept.' } })
        Object.assign(record, values)
      }
      return route.fulfill({ json: record })
    })
  }
}
const url = '/networks?view=devices&devices=device-1&devices_section=interfaces&interface=port-1'
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`interface endpoint records fit ${width}px in one drawer`, async ({ page }) => {
    await fixtures(page); await page.setViewportSize({ width, height: 600 })
    for (const kind of ['ip', 'mac'] as const) {
      await page.goto(`${url}&interface_view=${kind}`)
      const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true }), label = kind === 'ip' ? 'IP addresses' : 'MAC addresses'
      await expect(drawer.getByText(`31 ${label}`, { exact: true })).toBeVisible()
      await drawer.getByRole('button', { name: 'Next', exact: true }).click()
      const address = kind === 'ip' ? '192.0.2.31' : '02:00:00:00:00:1f'
      await drawer.getByRole('button', { name: address, exact: true }).click()
      await expect(drawer.getByRole('heading', { name: address, exact: true })).toBeFocused()
      await expect(page.getByRole('dialog')).toHaveCount(1)
      expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
      expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
      await page.reload(); await expect(drawer.getByRole('heading', { name: address })).toBeVisible()
      await drawer.getByRole('link', { name: 'Open in full page' }).click()
      await expect(page.getByRole('heading', { level: 1, name: 'Device 01' })).toBeVisible()
      await page.goBack(); await expect(drawer).toBeVisible()
      await drawer.getByRole('button', { name: `Back to ${label}` }).click()
      await expect(drawer.getByRole('button', { name: address, exact: true })).toBeFocused()
      await expect(page).toHaveURL(new RegExp(`interface_${kind}_page=2`))
      await drawer.getByRole('searchbox', { name: `Search ${label}` }).fill('Cable 01')
      await drawer.getByRole('button', { name: 'Search', exact: true }).click()
      await expect(drawer.getByText(`1 ${label}`, { exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
  })
}
for (const kind of ['ip', 'mac'] as const) {
  test(`${kind} assignment searches off-page choices, edits, confirms removal and returns`, async ({ page }) => {
    await fixtures(page); await page.goto(`${url}&interface_view=${kind}`)
    const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true }), label = kind === 'ip' ? 'IP address' : 'MAC address'
    await drawer.getByRole('button', { name: `Assign existing ${label}` }).click()
    await expect(drawer.getByRole('heading', { name: `Assign existing ${label}`, exact: true })).toBeFocused()
    await drawer.getByRole('searchbox', { name: 'Search available address records' }).fill('Cable 62')
    await drawer.getByRole('button', { name: 'Search', exact: true }).click()
    await drawer.getByRole('combobox', { name: 'Available address records' }).selectOption(`${kind}-62`)
    await drawer.getByRole('button', { name: 'Confirm assignment' }).click()
    const address = kind === 'ip' ? '192.0.2.62' : '02:00:00:00:00:3e'
    await expect(drawer.getByRole('heading', { name: address })).toBeVisible()
    await drawer.getByRole('button', { name: 'Edit address details' }).click()
    await drawer.getByRole('textbox', { name: 'Description' }).fill('Updated destination')
    await drawer.getByRole('button', { name: 'Save address details' }).click()
    await expect(drawer.getByText('Updated destination', { exact: true })).toBeVisible()
    await drawer.getByRole('button', { name: 'Remove from interface' }).click()
    await expect(drawer).toContainText('record and its history are retained')
    await drawer.getByRole('button', { name: 'Confirm removal' }).click()
    await expect(drawer.getByText(`31 ${label}es`, { exact: true })).toBeVisible()
    await page.mouse.click(10, 100); await expect(page.getByRole('dialog')).toHaveCount(0)
  })
  test(`${kind} failed assignment stays selected on touch and survives guarded navigation`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 500 }, hasTouch: true })
    try {
      const page = await context.newPage(); await fixtures(page, false, true); await page.goto(`${url}&interface_view=${kind}&interface_${kind}=new`)
      const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true })
      await drawer.getByRole('combobox', { name: 'Available address records' }).selectOption(`${kind}-32`)
      await drawer.getByRole('button', { name: 'Confirm assignment' }).tap()
      await expect(drawer.getByRole('alert')).toContainText('Assignment changed')
      await drawer.getByRole('link', { name: 'Interface details', exact: true }).click()
      await page.getByRole('button', { name: 'Keep editing' }).click()
      await expect(drawer.getByRole('combobox', { name: 'Available address records' })).toHaveValue(`${kind}-32`)
      if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/endpoint-${kind}-${test.info().project.name}.png` })
      await page.setViewportSize({ width: 1280, height: 600 }); await page.evaluate(() => { document.documentElement.style.zoom = '2' })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.keyboard.press('Escape'); await page.getByRole('button', { name: 'Discard changes' }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
    } finally { await context.close() }
  })
}
test('endpoint details reject foreign parents and respect read-only access', async ({ page }) => {
  await fixtures(page, true)
  for (const kind of ['ip', 'mac'] as const) {
    await page.goto(`${url}&interface_view=${kind}&interface_${kind}=${kind}-999`)
    const drawer = page.getByRole('dialog', { name: 'Device 01', exact: true }), label = kind === 'ip' ? 'IP addresses' : 'MAC addresses'
    await expect(drawer.getByRole('alert')).toContainText('unavailable')
    await drawer.getByRole('button', { name: `Back to ${label}` }).click()
    await expect(drawer.getByRole('button', { name: /Assign existing/ })).toHaveCount(0)
    await drawer.getByRole('button', { name: kind === 'ip' ? '192.0.2.1' : '02:00:00:00:00:01', exact: true }).click()
    await expect(drawer.getByRole('button', { name: 'Edit address details' })).toHaveCount(0)
    await expect(drawer.getByRole('button', { name: 'Remove from interface' })).toHaveCount(0)
  }
})
