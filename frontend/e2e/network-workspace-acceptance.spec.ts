import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const organizationId = '00000000-0000-4000-8000-000000000092'
const views = [
  { id: 'networks', label: 'Networks', expected: '0 networks' },
  { id: 'wireless', label: 'Wireless', expected: '0 wireless networks' },
  { id: 'vlans', label: 'VLANs', expected: '0 VLANs' },
  { id: 'vrfs', label: 'VRFs', expected: '0 VRFs' },
  { id: 'racks', label: 'Racks', expected: '0 racks' },
  { id: 'devices', label: 'Devices', expected: '0 devices' },
  { id: 'dns', label: 'DNS', expected: '0 DNS zones' },
  { id: 'circuits', label: 'Circuits', expected: '0 circuits' },
  { id: 'netbox', label: 'NetBox', expected: '0 NetBox identities' },
] as const

async function fixtures(page: Page, organization = false) {
  const networkRequests: string[] = []
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'network-acceptance@example.invalid', display_name: 'Network owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'],
    surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  if (organization) await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Regional Technology Group', classifications: ['client'], capabilities: ['overview', 'networks'],
    organization: { id: organizationId, name: 'Regional Technology Group', legal_name: '', website: '', classifications: ['client'], access_mode: 'assigned_only', created_at: '2026-09-25T12:00:00Z', updated_at: '2026-09-25T12:00:00Z' },
  } }))
  await page.route('**/collection-preferences/*', (route) => route.fulfill({ json: {
    columns: [], available_columns: [], default_columns: [], page_size: 25,
  } }))
  await page.route('**/api/v1/workspaces/**/networks**', (route) => {
    if (route.request().url().includes('/collection-preferences/')) return route.fulfill({ json: {
      columns: [], available_columns: [], default_columns: [], page_size: 25,
    } })
    networkRequests.push(route.request().url())
    return route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 25, has_more: false, can_manage: true, can_create: true } })
  })
  return networkRequests
}

async function chooseView(page: Page, id: string, label: string, mobile: boolean) {
  if (mobile) await page.getByRole('combobox', { name: 'Network views', exact: true }).selectOption(id)
  else await page.getByRole('navigation', { name: 'Network views' }).getByRole('link', { name: label, exact: true }).click()
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`all network registers remain usable at ${width}px`, async ({ page }) => {
    await fixtures(page)
    await page.setViewportSize({ width, height: 520 })
    await page.goto('/networks')
    const mobile = width < 768
    if (mobile) {
      await expect(page.getByRole('combobox', { name: 'Network views', exact: true })).toBeVisible()
      await expect(page.getByRole('navigation', { name: 'Network views' })).toBeHidden()
    } else {
      await expect(page.getByRole('navigation', { name: 'Network views' })).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'Network views', exact: true })).toBeHidden()
    }
    for (const view of views) {
      await chooseView(page, view.id, view.label, mobile)
      await expect(page.getByText(view.expected, { exact: true })).toBeVisible()
      if (view.id === 'networks') await expect(page).not.toHaveURL(/view=/)
      else await expect(page).toHaveURL(new RegExp(`view=${view.id}`))
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}

for (const width of [390, 1280]) {
  test(`client workspace keeps every network register in scope at ${width}px`, async ({ page }) => {
    const requests = await fixtures(page, true)
    await page.setViewportSize({ width, height: 520 })
    const path = `/workspaces/organizations/${organizationId}/networks`
    await page.goto(path)
    for (const view of views) {
      await chooseView(page, view.id, view.label, width < 768)
      await expect(page.getByText(view.expected, { exact: true })).toBeVisible()
      await expect(page).toHaveURL(new RegExp(`${path}${view.id === 'networks' ? '(?:\\?|$)' : `\\?view=${view.id}`}`))
    }
    expect(requests.length).toBeGreaterThanOrEqual(views.length)
    expect(requests.filter((url) => !url.includes(`/workspaces/organizations/${organizationId}/networks`))).toEqual([])
    expect(requests.filter((url) => url.includes('/workspaces/msp/networks'))).toEqual([])
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('network register selector remains usable at 200 percent zoom', async ({ page }) => {
  await fixtures(page)
  // A 1280px display exposes 640 CSS pixels at 200% browser zoom.
  await page.setViewportSize({ width: 640, height: 500 })
  await page.goto('/networks')
  const selector = page.getByRole('combobox', { name: 'Network views', exact: true })
  await expect(selector).toBeVisible()
  await selector.selectOption('circuits')
  await expect(page.getByText('0 circuits', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
