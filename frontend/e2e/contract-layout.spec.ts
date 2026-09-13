import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'

const columns = ['name', 'provider', 'kind', 'status', 'renews_on', 'ends_on']
async function fixtures(page: Page, costsAllowed = true) {
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const contracts = Array.from({ length: 131 }, (_, index) => ({
    id: `contract-${index + 1}`, name: `Contract ${String(index + 1).padStart(3, '0')}${index === 0 ? ` ${'LongIdentifier'.repeat(15)}` : ''}`,
    provider_id: 'provider-1', provider_name: 'Synthetic provider', kind: 'support', status: 'active',
    starts_on: '2026-01-01', ends_on: null, renews_on: '2030-01-01', renewal_notice_days: 30,
    auto_renew: true, reference: `REF-${index + 1}`, description: 'Managed support for the synthetic workspace.',
    ...(costsAllowed ? { costs: [
      { id: 'cost-1', label: 'Monthly support', amount: '100.00', currency: 'USD', quantity: '1.0000', billing_interval: 'monthly', starts_on: null, ends_on: null },
      { id: 'cost-2', label: 'Annual coverage', amount: '250.00', currency: 'EUR', quantity: '1.0000', billing_interval: 'annual', starts_on: null, ends_on: null },
    ] } : {}),
  }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['assets.view', 'assets.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route('**/collection-preferences/contracts', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/contracts?*', (route) => {
    const params = new URL(route.request().url()).searchParams
    const size = Number(params.get('page_size') ?? 25), pageNumber = Number(params.get('page') ?? 1)
    let found = contracts.filter((item) => `${item.name} ${item.reference}`.includes(params.get('q') ?? ''))
    if (params.get('status')) found = found.filter((item) => item.status === params.get('status'))
    if (params.get('kind')) found = found.filter((item) => item.kind === params.get('kind'))
    if (params.get('ordering')?.startsWith('-')) found = [...found].reverse()
    expect(params.get('summary')).toBe('true')
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size).map((item) => ({ ...item, costs: undefined })), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: true, can_view_costs: costsAllowed, can_view_relationships: false } })
  })
  await page.route(/\/contracts\/contract-\d+$/, (route) => {
    const record = contracts.find((item) => route.request().url().endsWith(`/${item.id}`))
    if (route.request().method() === 'PATCH') return route.fulfill({ status: 409, json: { detail: 'The contract changed. Your entries have been kept.' } })
    return route.fulfill(record ? { json: record } : { status: 404, json: {} })
  })
  await page.route('**/contracts/providers', (route) => route.fulfill({ json: { results: [{ id: 'provider-1', name: 'Synthetic provider' }] } }))
  return contracts
}

async function section(page: Page, container: Locator, name: string) {
  if (page.viewportSize()!.width < 768) await container.getByRole('combobox', { name: 'Sections', exact: true }).selectOption(name.toLowerCase())
  else await container.getByRole('link', { name, exact: true }).click()
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Contracts list and full drawer fit ${width}px`, async ({ page }) => {
    const records = await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    const details: string[] = []
    page.on('request', (request) => { if (/\/contracts\/contract-\d+$/.test(request.url())) details.push(request.url()) })
    await page.goto('/services')
    await expect(page.getByText('131 contracts', { exact: true })).toBeVisible()
    expect(details).toHaveLength(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: records[0].name, exact: true }).click()
    const drawer = page.getByRole('dialog', { name: records[0].name })
    await expect(drawer.getByRole('heading', { level: 2, name: records[0].name })).toBeFocused()
    expect(details).toHaveLength(1)
    await expect(drawer.getByRole('button', { name: 'Close', exact: true })).toHaveCount(0)
    expect(await page.locator('body').evaluate((element) => element.style.overflow)).toBe('hidden')
    expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
    await section(page, drawer, 'Costs')
    await expect(drawer.getByText(/USD 100.00/)).toBeVisible()
    await expect(drawer.getByText(/EUR 250.00/)).toBeVisible()
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await page.reload()
    await expect(drawer.getByText(/USD 100.00/)).toBeVisible()
    if (process.env.LAYOUT_SCREENSHOT_DIR && test.info().project.name === 'chromium') await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/contracts-${width}.png` })
    if (width < 768) await drawer.getByRole('link', { name: 'Back to contracts' }).click()
    else await page.mouse.click(10, 100)
    await expect(drawer).toHaveCount(0)
    await page.getByRole('button', { name: records[0].name, exact: true }).click()
    await expect(drawer.getByRole('heading', { level: 2, name: records[0].name })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(drawer).toHaveCount(0)
    await expect(page.getByRole('button', { name: records[0].name, exact: true })).toBeFocused()
    await page.getByRole('button', { name: records[0].name, exact: true }).click()
    await section(page, drawer, 'Costs')
    await drawer.getByRole('link', { name: 'Open in full page' }).click()
    await expect(page).toHaveURL(/record=contract-1.*section=costs/)
    await expect(page.getByRole('heading', { level: 1, name: records[0].name })).toBeVisible()
    await section(page, page.locator('main'), 'Overview')
    await page.goBack()
    await expect(page).toHaveURL(/section=costs/)
    await page.goForward()
    await expect(page).not.toHaveURL(/section=costs/)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('link', { name: 'Back to contracts' }).click()
    await expect(page.getByText('131 contracts', { exact: true })).toBeVisible()
  })
}

test('Contracts search the full collection and persist and reset columns', async ({ page }) => {
  await fixtures(page)
  await page.goto('/services')
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Contract 026', exact: true })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search contracts' }).fill('REF-131')
  await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Contract 131', exact: true })).toBeVisible()
  await expect(page).not.toHaveURL(/page=2/)
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: 'Contract name', exact: true })).toBeDisabled()
  await page.getByRole('checkbox', { name: 'Ends on', exact: true }).uncheck()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Ends on' })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Contract 131', exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Ends on' })).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Rows per page' }).selectOption('50')
  await page.getByRole('button', { name: 'Columns', exact: true }).click()
  await page.getByRole('button', { name: 'Reset to defaults' }).click()
  await expect(page).not.toHaveURL(/page_size=/)
  await expect(page.getByRole('columnheader', { name: 'Ends on' })).toBeVisible()
})

test('Contract failed edits survive tab and outside dismissal attempts', async ({ page }) => {
  await fixtures(page)
  await page.goto('/services?preview=contract-2')
  const drawer = page.getByRole('dialog', { name: 'Contract 002' })
  await drawer.getByRole('button', { name: 'Edit contract', exact: true }).click()
  await drawer.getByRole('textbox', { name: 'Contract name', exact: true }).fill('Unsaved name')
  await drawer.getByRole('button', { name: 'Save contract', exact: true }).click()
  await expect(drawer.getByRole('alert')).toContainText('Your entries have been kept')
  await section(page, drawer, 'Costs')
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'Contract name', exact: true })).toHaveValue('Unsaved name')
  await page.mouse.click(10, 100)
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByRole('textbox', { name: 'Contract name', exact: true })).toHaveValue('Unsaved name')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(drawer).toHaveCount(0)
})

test('Contract cost permission and unavailable direct records remain explicit', async ({ page }) => {
  await fixtures(page, false)
  await page.goto('/services?preview=contract-2&section=costs')
  const drawer = page.getByRole('dialog', { name: 'Contract 002' })
  await expect(drawer.getByText(/Financial terms are hidden/)).toBeVisible()
  await expect(drawer.getByRole('button', { name: 'Add cost', exact: true })).toHaveCount(0)
  await expect(drawer.getByRole('link', { name: 'Related', exact: true })).toHaveCount(0)
  await page.goto('/services?record=contract-999')
  await expect(page.getByRole('alert')).toContainText('unavailable')
  await page.getByRole('link', { name: 'Back to contracts' }).click()
  await expect(page.getByText('131 contracts', { exact: true })).toBeVisible()
})

test('Contract touch controls and 200 percent CSS zoom remain reachable', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 600 }, hasTouch: true })
  try {
    const page = await context.newPage()
    await fixtures(page)
    await page.goto('/services')
    await page.getByRole('button', { name: 'Contract 002', exact: true }).tap()
    await expect(page.getByRole('dialog', { name: 'Contract 002' })).toBeVisible()
    await page.getByRole('link', { name: 'Back to contracts', exact: true }).tap()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    await page.getByRole('button', { name: 'Contract 002', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Contract 002' })
    await expect(drawer.getByRole('button', { name: 'Edit contract' })).toBeVisible()
    expect(await drawer.evaluate((element) => { const bounds = element.getBoundingClientRect(); return element.scrollWidth <= element.clientWidth && bounds.bottom <= innerHeight + 1 && bounds.right <= innerWidth + 1 })).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  } finally { await context.close() }
})
