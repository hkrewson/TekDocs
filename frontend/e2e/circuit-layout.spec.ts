import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
async function fixtures(page: Page, { denied = false, fail = false, unavailable = false } = {}) {
  await page.addInitScript(() => { document.cookie = `csrftoken=${crypto.randomUUID().replaceAll('-', '')}; path=/` })
  await page.route('**/api/v1/bootstrap/status', route => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', route => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', route => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  const rows = Array.from({ length: 31 }, (_, index) => ({ id: `circuit-${index}`, name: `Circuit ${index.toString().padStart(2, '0')}`, provider_id: 'carrier', provider_name: 'Carrier', service_identifier: `SERVICE-${index}`, kind: 'internet', status: 'active', bandwidth_down_mbps: '1000.000', bandwidth_up_mbps: null, installed_on: null, service_starts_on: null, review_on: null, planned_disconnect_on: null, description: 'Service notes '.repeat(150), lifecycle_events: [{ kind: 'review', date: '2026-01-01', label: 'Review circuit', state: 'overdue' }] }))
  const handoff = { id: 'handoff-1', circuit_id: 'circuit-30', name: 'Carrier demarc', side: 'a', media: 'fiber', connector: 'LC', provider_reference: 'REFERENCE'.repeat(30), site_name: null, location_name: null, device_name: null, interface_name: null, description: 'Handoff notes '.repeat(80) }
  const circuitColumns = ['name', 'provider_name', 'service_identifier', 'kind', 'status', 'bandwidth_down_mbps']
  const saved: Record<string, { columns: string[]; page_size: number }> = {}
  await page.route('**/collection-preferences/*', route => {
    const feature = route.request().url().split('/').at(-1)!
    const columns = feature === 'network-circuits' ? circuitColumns : ['name', 'side', 'media', 'site_name']
    if (route.request().method() === 'PUT') saved[feature] = route.request().postDataJSON() as { columns: string[]; page_size: number }
    if (route.request().method() === 'DELETE') delete saved[feature]
    return route.fulfill({ json: { ...(saved[feature] ?? { columns, page_size: 25 }), available_columns: columns, default_columns: columns } })
  })
  await page.route('**/networks/circuits?*', route => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('summary')).toBe('true')
    let found = rows.filter(row => `${row.name} ${row.service_identifier}`.includes(query.get('q') ?? ''))
    if (query.get('status')) found = found.filter(row => row.status === query.get('status'))
    if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
    const size = Number(query.get('page_size')), page = Number(query.get('page'))
    return route.fulfill({ json: { results: found.slice((page - 1) * size, page * size).map(row => ({ ...row, description: undefined, lifecycle_events: undefined })), count: found.length, page, page_size: size, has_more: page * size < found.length, can_manage: !denied } })
  })
  await page.route(/\/networks\/circuits\/circuit-\d+(\?include_handoffs=false)?$/, route => {
    if (unavailable) return route.fulfill({ status: 403, json: {} })
    const row = rows.find(row => new URL(route.request().url()).pathname.endsWith(`/${row.id}`))!
    if (route.request().method() === 'PATCH') {
      if (fail) return route.fulfill({ status: 409, json: { detail: 'Record changed. Your entries have been kept.' } })
      const change = route.request().postDataJSON() as Record<string, unknown>
      expect(change).not.toHaveProperty('provider_id')
      expect(change).not.toHaveProperty('contract_id')
      expect(change).not.toHaveProperty('status')
      Object.assign(row, change)
    } else expect(new URL(route.request().url()).searchParams.get('include_handoffs')).toBe('false')
    return route.fulfill({ json: row })
  })
  await page.route('**/circuits/circuit-30/handoffs?*', route => {
    expect(new URL(route.request().url()).searchParams.get('paginated')).toBe('true')
    return route.fulfill({ json: { results: [handoff], count: 1, page: 1, page_size: 25, has_more: false, can_manage: !denied } })
  })
  await page.route('**/circuits/circuit-30/handoffs/handoff-1', route => route.fulfill({ json: handoff }))
  await page.route('**/activity?*', route => route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, actions: [] } }))
}
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Circuit and handoff drawers fit ${width}px`, async ({ page }) => {
    await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks?view=circuits')
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('button', { name: 'Circuit 30', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Circuit 30', exact: true })
    await expect(drawer.getByText(/Overdue/)).toBeVisible()
    if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('handoffs')
    else await drawer.getByRole('link', { name: 'Handoffs', exact: true }).click()
    await drawer.getByRole('button', { name: 'Carrier demarc', exact: true }).click()
    await expect(drawer.getByRole('heading', { name: 'Carrier demarc' })).toBeFocused()
    expect(await drawer.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    await page.reload()
    await expect(drawer.getByRole('heading', { name: 'Carrier demarc' })).toBeVisible()
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Circuit 30' })).toBeVisible()
    await page.goBack()
    await drawer.getByRole('button', { name: 'Back to handoffs' }).click()
    await expect(drawer.getByRole('button', { name: 'Carrier demarc', exact: true })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Circuit 30', exact: true })).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
test('Circuit edits preserve failed values and guard sections and backdrop dismissal', async ({ page }) => {
  await fixtures(page, { fail: true })
  await page.goto('/networks?view=circuits&circuits=circuit-30')
  const drawer = page.getByRole('dialog', { name: 'Circuit 30', exact: true })
  await drawer.getByRole('button', { name: 'Edit service details' }).click()
  await drawer.getByRole('textbox', { name: 'Description' }).fill('Retained draft')
  await drawer.getByRole('button', { name: 'Save circuit details' }).click()
  await expect(drawer.getByRole('alert')).toContainText('Record changed')
  await drawer.getByRole('link', { name: 'Handoffs', exact: true }).click()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await page.mouse.click(10, 100)
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'Description' })).toHaveValue('Retained draft')
  await page.setViewportSize({ width: 1280, height: 500 })
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  expect(await drawer.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
})
test('Circuit search finds off-page identifiers, saves details and keeps list context', async ({ page }) => {
  await fixtures(page)
  await page.goto('/networks?view=circuits')
  await page.getByRole('searchbox', { name: 'Search circuits' }).fill('SERVICE-30')
  await page.getByRole('main').getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByRole('button', { name: 'Circuit 30', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: 'Circuit 30', exact: true })
  await drawer.getByRole('button', { name: 'Edit service details' }).click()
  await drawer.getByRole('textbox', { name: 'Description' }).fill('Verified service')
  await drawer.getByRole('button', { name: 'Save circuit details' }).click()
  await expect(drawer.getByText('Verified service', { exact: true })).toBeVisible()
  await page.reload()
  await expect(drawer.getByText('Verified service', { exact: true })).toBeVisible()
  await page.mouse.click(10, 100)
  await expect(page.getByRole('searchbox', { name: 'Search circuits' })).toHaveValue('SERVICE-30')
})
test('Circuit read-only and unavailable records retain navigation', async ({ page }) => {
  await fixtures(page, { denied: true })
  await page.goto('/networks?view=circuits&circuits=circuit-30&circuits_page=2')
  const drawer = page.getByRole('dialog', { name: 'Circuit 30', exact: true })
  await expect(drawer.getByRole('button', { name: 'Edit service details' })).toHaveCount(0)
  await drawer.getByRole('link', { name: 'History', exact: true }).click()
  await expect(drawer.getByText('No circuit history is available.')).toBeVisible()
  await page.unrouteAll({ behavior: 'wait' })
  await fixtures(page, { unavailable: true })
  await page.reload()
  await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Circuit 30', exact: true })).toBeVisible()
})

test('Circuit touch editing preserves readable controls in a short viewport', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL, viewport: { width: 390, height: 500 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await fixtures(page)
    await page.goto('/networks?view=circuits&circuits=circuit-30')
    const drawer = page.getByRole('dialog', { name: 'Circuit 30', exact: true })
    await drawer.getByRole('button', { name: 'Edit service details' }).tap()
    await drawer.getByRole('textbox', { name: 'Description' }).fill('Touch service edit')
    await drawer.getByRole('button', { name: 'Save circuit details' }).tap()
    await expect(drawer.getByText('Touch service edit', { exact: true })).toBeVisible()
    expect(await drawer.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    await drawer.getByRole('link', { name: 'Back to circuits', exact: true }).tap()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { await context.close() }
})

test('Circuit collection failure can be retried into an empty workspace', async ({ page }) => {
  await fixtures(page)
  let failed = true
  await page.route('**/networks/circuits?*', route => failed
    ? route.fulfill({ status: 503, json: {} })
    : route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, can_manage: false } }))
  await page.goto('/networks?view=circuits')
  await expect(page.getByRole('alert')).toContainText('Circuits could not be loaded.')
  failed = false
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByText('No circuits match this workspace and search.')).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
