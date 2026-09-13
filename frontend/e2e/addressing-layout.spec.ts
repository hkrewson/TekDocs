import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
type Kind = 'vlans' | 'vrfs'
async function fixtures(page: Page, kind: Kind, denied = false, failSave = false) {
  await page.addInitScript(() => { document.cookie = `csrftoken=${crypto.randomUUID().replaceAll('-', '')}; path=/` })
  const field = kind === 'vlans' ? 'vlan_id' : 'route_distinguisher'
  const columns = ['name', field]
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const records = Array.from({ length: 31 }, (_, index) => ({ id: `${kind}-${index + 1}`, name: `Office ${String(index + 1).padStart(2, '0')}`, description: 'Network documentation '.repeat(150), ...(kind === 'vlans' ? { vlan_id: index + 1 } : { route_distinguisher: `64512:${String(index + 1).padStart(2, '0')}` }) }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  await page.route(`**/collection-preferences/network-${kind}`, (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route(`**/api/v1/workspaces/**/networks/${kind}?*`, (route) => {
    const query = new URL(route.request().url()).searchParams
    expect(query.get('summary')).toBe('true')
    expect(query.has('subnet_id')).toBe(false)
    const size = Number(query.get('page_size')), pageNumber = Number(query.get('page'))
    let found = records.filter((item) => `${item.name} ${'vlan_id' in item ? item.vlan_id : item.route_distinguisher}`.includes(query.get('q') ?? ''))
    if (query.get('ordering')?.startsWith('-')) found = found.toReversed()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * size, pageNumber * size).map((item) => ({ ...item, description: undefined })), count: found.length, page: pageNumber, page_size: size, has_more: pageNumber * size < found.length, can_manage: !denied } })
  })
  await page.route(new RegExp(`/api/v1/workspaces/.*/networks/${kind}/${kind}-\\d+$`), (route) => {
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
}
for (const kind of ['vlans', 'vrfs'] as const) {
  const label = kind === 'vlans' ? 'VLAN' : 'VRF'
  for (const width of [320, 390, 768, 1024, 1280, 1440]) {
    test(`${label} register and record fit ${width}px with retained navigation`, async ({ page }) => {
      await fixtures(page, kind)
      await page.setViewportSize({ width, height: 600 })
      await page.goto(`/networks?view=${kind}`)
      await expect(page.getByText(`31 ${label}s`, { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Filters' })).toHaveCount(0)
      await page.getByRole('button', { name: 'Next', exact: true }).click()
      await page.getByRole('button', { name: 'Office 31', exact: true }).click()
      const drawer = page.getByRole('dialog', { name: 'Office 31', exact: true })
      await expect(drawer.getByRole('heading', { name: 'Office 31', exact: true })).toBeFocused()
      await expect(drawer).toContainText('Network documentation')
      expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
      expect((await new AxeBuilder({ page }).include('.collection-drawer').analyze()).violations).toEqual([])
      if (width < 768) await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('history')
      else await drawer.getByRole('link', { name: 'History', exact: true }).click()
      await expect(drawer).toContainText(`No ${label} history is available.`)
      await page.reload()
      await expect(drawer).toContainText(`No ${label} history is available.`)
      await drawer.getByRole('link', { name: 'Open in full page' }).click()
      await expect(page.getByRole('heading', { level: 1, name: 'Office 31' })).toBeVisible()
      await page.goBack()
      await expect(drawer).toBeVisible()
      await page.goForward()
      await page.getByRole('link', { name: `Back to ${label}s`, exact: true }).click()
      await expect(page.getByRole('button', { name: 'Office 31', exact: true })).toBeFocused()
      await expect(page).toHaveURL(new RegExp(`${kind}_page=2`))
      await page.getByRole('searchbox', { name: `Search ${label}s` }).fill('Office 01')
      await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
      await expect(page.getByText(`1 ${label}s`, { exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    })
  }
  test(`${label} denied and unavailable records retain a return path`, async ({ page }) => {
    await fixtures(page, kind, true)
    await page.goto(`/networks?view=${kind}&${kind}=${kind}-1&${kind}_full=true`)
    await expect(page.getByRole('heading', { level: 1, name: 'Office 01' })).toBeVisible()
    await expect(page.getByRole('button', { name: `Edit ${label}` })).toHaveCount(0)
    await page.goto(`/networks?view=${kind}&${kind}=${kind}-999`)
    await expect(page.getByRole('dialog')).toContainText('unavailable')
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
  test(`${label} failed edits are guarded on touch and zoomed screens`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 500 }, hasTouch: true })
    try {
      const page = await context.newPage()
      await fixtures(page, kind, false, true)
      await page.goto(`/networks?view=${kind}&${kind}=${kind}-1`)
      const drawer = page.getByRole('dialog', { name: 'Office 01', exact: true })
      await drawer.getByRole('button', { name: `Edit ${label}` }).tap()
      await drawer.getByRole('textbox', { name: 'Name', exact: true }).fill('Unsaved record')
      await drawer.getByRole('button', { name: `Save ${label}` }).tap()
      await expect(drawer.getByRole('alert')).toContainText('Record changed')
      await drawer.getByRole('combobox', { name: 'Sections', exact: true }).selectOption('history')
      await page.getByRole('button', { name: 'Keep editing' }).click()
      await expect(drawer.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Unsaved record')
      if (process.env.LAYOUT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.LAYOUT_SCREENSHOT_DIR}/${kind}-${test.info().project.name}.png` })
      await page.setViewportSize({ width: 1280, height: 600 })
      await page.evaluate(() => { document.documentElement.style.zoom = '2' })
      expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
      await page.keyboard.press('Escape')
      await page.getByRole('button', { name: 'Discard changes' }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
    } finally { await context.close() }
  })
}

for (const kind of ['vlans', 'vrfs'] as const) {
  const label = kind === 'vlans' ? 'VLAN' : 'VRF'
  const field = kind === 'vlans' ? 'VLAN ID' : 'Route distinguisher'
  test(`${label} lookup retries, columns persist and reset, and empty searches stay usable`, async ({ page }) => {
    await fixtures(page, kind)
    let fail = true
    await page.route(`**/api/v1/workspaces/**/networks/${kind}?*`, (route) => {
      if (fail) { fail = false; return route.fulfill({ status: 503, json: {} }) }
      return route.fallback()
    })
    await page.goto(`/networks?view=${kind}`)
    await expect(page.getByRole('alert')).toContainText(`${label}s could not be loaded`)
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByText(`31 ${label}s`, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Columns', exact: true }).click()
    await expect(page.getByRole('checkbox', { name: 'Name', exact: true })).toBeDisabled()
    await page.getByRole('checkbox', { name: field, exact: true }).uncheck()
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('columnheader', { name: field })).toHaveCount(0)
    await page.reload()
    await expect(page.getByText(`31 ${label}s`, { exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: field })).toHaveCount(0)
    await page.getByRole('button', { name: 'Columns', exact: true }).click()
    await page.getByRole('button', { name: 'Reset to defaults' }).click()
    await expect(page.getByRole('columnheader', { name: field })).toHaveCount(1)
    await page.getByRole('searchbox', { name: `Search ${label}s` }).fill('Missing record')
    await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
    await expect(page.getByText(`No ${label}s match this workspace and search.`, { exact: true })).toBeVisible()
  })
}
