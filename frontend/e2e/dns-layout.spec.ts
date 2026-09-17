import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
type Kind = 'dns'
async function fixtures(page: Page, kind: Kind, denied = false, failSave = false) {
  await page.addInitScript(() => { document.cookie = `csrftoken=${crypto.randomUUID().replaceAll('-', '')}; path=/` })
  const field = 'record_count'
  const columns = ['name', field]
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const records = Array.from({ length: 31 }, (_, index) => ({ id: `${kind}-${index + 1}`, name: `zone${String(index + 1).padStart(2, '0')}.invalid`, description: 'Network documentation '.repeat(150), record_count: 31 }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route(`**/collection-preferences/dns-zones`, (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route(`**/api/v1/workspaces/**/networks/dns-zones?*`, (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('summary')).toBe('true')
    expect(query.has('subnet_id')).toBe(false)
    const size = Number(query.get('page_size')), pageNumber = Number(query.get('page'))
    let found = records.filter((item) => item.name.includes(query.get('q') ?? ''))
    if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size).map((item) => ({ ...item, description: undefined })), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: !denied } })
  })
  await page.route(new RegExp(`/api/v1/workspaces/.*/networks/dns-zones/${kind}-\\d+$`), (route) => {
    const record = records.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (!record) return route.fulfill({ status: 403, json: {} })
    if (route.request().method() === 'PATCH') {
      if (denied) return route.fulfill({ status: 403, json: { detail: 'Editing is unavailable.' } })
      if (failSave) return route.fulfill({ status: 409, json: { detail: 'Record changed. Your entries have been kept.' } })
      Object.assign(record, route.request().postDataJSON() as Record<string, unknown>)
    }
    return route.fulfill({ json: record })
  })
  await page.route('**/activity?*', (route) => route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
  const child = { id: 'record-1', zone_id: 'dns-31', zone_name: 'zone31.invalid', owner_name: 'host.zone31.invalid', record_type: 'TXT', value: 'long-value'.repeat(400), ttl: 3600, priority: null, weight: null, port: null, ip_address_id: null, description: 'Record notes' }
  await page.route('**/collection-preferences/dns-records', route => route.fulfill({ json: { columns: ['name', 'record_type', 'value', 'ttl'], available_columns: ['name', 'record_type', 'value', 'ttl'], default_columns: ['name', 'record_type', 'value', 'ttl'], page_size: 25 } }))
  await page.route('**/networks/dns-records?*', route => {
    const zoneId = new URL(route.request().url()).searchParams.get('zone_id')
    const results = child.zone_id === zoneId ? [child] : []
    return route.fulfill({ json: { results, count: results.length, page: 1, page_size: 25, has_more: false, can_manage: !denied } })
  })
  await page.route('**/networks/dns-records/record-1', route => {
    if (route.request().method() === 'PATCH') {
      if (failSave) return route.fulfill({ status: 409, json: { detail: 'Record changed. Your entries have been kept.' } })
      const values = route.request().postDataJSON() as Record<string, unknown>
      Object.assign(child, values)
      if (typeof values.zone_id === 'string') child.zone_name = records.find(item => item.id === values.zone_id)?.name ?? child.zone_name
    }
    return route.fulfill({ json: child })
  })

}
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`DNS zone and child records fit ${width}px`, async ({ page }) => {
    await fixtures(page, 'dns')
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks?view=dns')
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('button', { name: 'zone31.invalid', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'zone31.invalid', exact: true })
    if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('records')
    else await drawer.getByRole('link', { name: 'Records', exact: true }).click()
    await page.getByRole('button', { name: 'host.zone31.invalid', exact: true }).click()
    await expect(drawer).toContainText('Record notes')
    await expect(drawer.getByRole('heading', { name: 'host.zone31.invalid', exact: true })).toBeFocused()
    await drawer.getByRole('link', { name: 'View record history', exact: true }).click()
    await expect(drawer).toContainText('No DNS record history is available.')
    await expect(page.getByRole('dialog')).toHaveCount(1)
    expect(await drawer.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    await page.reload()
    await expect(drawer).toContainText('No DNS record history is available.')
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'zone31.invalid' })).toBeVisible()
    await page.goBack()
    await expect(drawer).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'zone31.invalid', exact: true })).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
test('DNS failed edits survive tab changes and dismissal', async ({ page }) => {
  await fixtures(page, 'dns', false, true)
  await page.goto('/networks?view=dns&dns=dns-31&dns_section=records&dns_record=record-1')
  const drawer = page.getByRole('dialog', { name: 'zone31.invalid', exact: true })
  await drawer.getByRole('button', { name: 'Edit DNS record' }).click()
  await drawer.getByRole('textbox', { name: 'Value', exact: true }).fill('unsaved DNS value')
  await drawer.getByRole('button', { name: 'Save DNS record' }).click()
  await expect(drawer.getByRole('alert')).toContainText('Record changed')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'Value', exact: true })).toHaveValue('unsaved DNS value')
})
test('DNS records move to a searched zone with a compare-checked request', async ({ page }) => {
  await fixtures(page, 'dns')
  await page.goto('/networks?view=dns&dns=dns-31&dns_section=records&dns_record=record-1')
  const drawer = page.getByRole('dialog', { name: 'zone31.invalid', exact: true })
  await drawer.getByRole('button', { name: 'Move to another zone', exact: true }).click()
  await drawer.getByRole('searchbox', { name: 'Search destination DNS zones', exact: true }).fill('zone30')
  await drawer.getByRole('button', { name: 'Search', exact: true }).click()
  await drawer.getByRole('combobox', { name: 'Available DNS zones', exact: true }).selectOption('dns-30')
  await expect(drawer.getByLabel('Owner name in destination zone')).toHaveValue('host.zone30.invalid')
  const request = page.waitForRequest(value => value.url().endsWith('/networks/dns-records/record-1') && value.method() === 'PATCH')
  await drawer.getByRole('button', { name: 'Confirm move', exact: true }).click()
  expect((await request).postDataJSON()).toEqual({ zone_id: 'dns-30', expected_zone_id: 'dns-31', owner_name: 'host.zone30.invalid' })
  await expect(drawer.getByText('No DNS records match this search.', { exact: true })).toBeVisible()
})
test('DNS denied, unavailable, failed and empty states retain navigation', async ({ page }) => {
  await fixtures(page, 'dns', true)
  await page.goto('/networks?view=dns&dns=dns-999')
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('unavailable')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Add zone', exact: true })).toHaveCount(0)
  await page.getByRole('searchbox', { name: 'Search DNS zones' }).fill('missing')
  await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByText('No DNS zones match this search.', { exact: true })).toBeVisible()
  await page.route('**/networks/dns-zones?*', route => route.fulfill({ status: 503, json: {} }))
  await page.reload()
  await expect(page.getByRole('alert')).toContainText('DNS zones could not be loaded.')
  await expect(page.getByRole('button', { name: 'Try again', exact: true })).toBeVisible()
  await page.unroute('**/networks/dns-zones?*')
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByText('No DNS zones match this search.', { exact: true })).toBeVisible()
})
test('DNS touch edits remain readable at short heights and 200% zoom', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 450 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await fixtures(page, 'dns', false, true)
    await page.goto('/networks?view=dns&dns=dns-31&dns_section=records&dns_record=record-1')
    const drawer = page.getByRole('dialog', { name: 'zone31.invalid', exact: true })
    await drawer.getByRole('button', { name: 'Edit DNS record' }).tap()
    await drawer.getByRole('textbox', { name: 'Value', exact: true }).fill('unsaved')
    await drawer.getByRole('button', { name: 'Save DNS record' }).tap()
    await expect(drawer.getByRole('alert')).toContainText('Record changed')
    await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('history')
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(drawer.getByRole('textbox', { name: 'Value', exact: true })).toHaveValue('unsaved')
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    expect(await drawer.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
  } finally { await context.close() }
})

test('DNS record history paging stays separate from the zone and refreshes from its direct link', async ({ page }) => {
  await fixtures(page, 'dns')
  const calls: { entity: string | null; page: number }[] = []
  await page.route('**/activity?*', route => {
    const query = new URL(route.request().url()).searchParams
    const entity = query.get('entity_id'), pageNumber = Number(query.get('page'))
    calls.push({ entity, page: pageNumber })
    expect(query.get('page_size')).toBe('25')
    return route.fulfill({ json: { results: [{ id: `audit-${pageNumber}`, action: entity === 'record-1' ? 'dns_record.updated' : 'dns_zone.created', actor_name: 'Test technician', occurred_at: '2026-09-01T10:00:00Z' }], count: 31, page: pageNumber, page_size: 25, has_more: pageNumber === 1, actions: [] } })
  })
  await page.goto('/networks?view=dns&dns=dns-31&dns_section=records&dns_record=record-1&history_page=3')
  const drawer = page.getByRole('dialog', { name: 'zone31.invalid', exact: true })
  await expect(drawer).toContainText('Record notes')
  expect(calls).toEqual([])
  await drawer.getByRole('link', { name: 'View record history' }).click()
  await expect(drawer.getByText('Record updated', { exact: true })).toBeVisible()
  expect(calls.at(-1)).toEqual({ entity: 'record-1', page: 1 })
  await drawer.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page).toHaveURL(/dns_record_history_page=2/)
  await expect(drawer.getByRole('heading', { name: 'History', exact: true })).toBeFocused()
  expect(calls.at(-1)).toEqual({ entity: 'record-1', page: 2 })
  await page.reload()
  await expect(drawer.getByText('Record updated', { exact: true })).toBeVisible()
  expect(calls.at(-1)).toEqual({ entity: 'record-1', page: 2 })
  await drawer.getByRole('link', { name: 'History', exact: true }).click()
  await expect(drawer.getByText('Zone created', { exact: true })).toBeVisible()
  expect(calls.at(-1)).toEqual({ entity: 'dns-31', page: 3 })
  await drawer.getByRole('link', { name: 'Records', exact: true }).click()
  await expect(drawer.getByText('Record updated', { exact: true })).toBeVisible()
  await drawer.getByRole('button', { name: 'Back to DNS records' }).click()
  await drawer.getByRole('button', { name: 'host.zone31.invalid' }).click()
  await expect(drawer).toContainText('Record notes')
  expect(new URL(page.url()).searchParams.has('dns_record_history_page')).toBe(false)
})
test('DNS record history denial and failed reads preserve details and retry recovery', async ({ page }) => {
  await fixtures(page, 'dns')
  let denied = true, unavailable = false
  await page.route('**/activity?*', route => route.fulfill({ status: denied ? 403 : unavailable ? 503 : 200, json: denied || unavailable ? {} : { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
  await page.goto('/networks?view=dns&dns=dns-31&dns_section=records&dns_record=record-1&dns_record_view=history')
  const drawer = page.getByRole('dialog', { name: 'zone31.invalid', exact: true })
  await expect(drawer.getByRole('alert')).toContainText('You cannot view DNS record history.')
  await drawer.getByRole('link', { name: 'Back to record details' }).click()
  await expect(drawer).toContainText('Record notes')
  denied = false; unavailable = true
  await drawer.getByRole('link', { name: 'View record history' }).click()
  await expect(drawer.getByRole('alert')).toContainText('Lifecycle history could not be loaded.')
  unavailable = false
  await drawer.getByRole('button', { name: 'Retry history' }).click()
  await expect(drawer).toContainText('No DNS record history is available.')
})

test('DNS record type changes preserve the chosen value', async ({ page }) => {
  await fixtures(page, 'dns')
  await page.goto('/networks?view=dns&dns=dns-31&dns_section=records&dns_record=record-1')
  const drawer = page.getByRole('dialog', { name: 'zone31.invalid', exact: true })
  await drawer.getByRole('button', { name: 'Edit DNS record', exact: true }).click()
  await drawer.getByRole('combobox', { name: 'Type', exact: true }).selectOption('CNAME')
  await drawer.getByRole('textbox', { name: 'Value', exact: true }).fill('alias.example.invalid')
  await drawer.getByRole('button', { name: 'Save DNS record', exact: true }).click()
  await expect(drawer.getByText('CNAME', { exact: true })).toBeVisible()
  await expect(drawer.getByText('alias.example.invalid', { exact: true })).toBeVisible()
})
