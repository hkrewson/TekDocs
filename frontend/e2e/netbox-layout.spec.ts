import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const organizationId = '00000000-0000-4000-8000-000000000091'
const columns = ['name', 'type', 'object', 'observation']

async function fixtures(page: Page, organization = false) {
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const requests: string[] = []
  const records = Array.from({ length: 31 }, (_, index) => ({
    id: `00000000-0000-4000-9000-${String(index + 1).padStart(12, '0')}`,
    entity_id: `00000000-0000-4000-a000-${String(index + 1).padStart(12, '0')}`,
    entity_name: `Rack ${String(index + 1).padStart(3, '0')}${index === 0 ? ` ${'LongIdentifier'.repeat(24)}` : ''}`,
    entity_type: 'network_rack', object_type: 'dcim.rack', object_id: index + 1,
    observed_fingerprint: '', last_observed_at: index % 2 ? '2026-09-25T12:00:00Z' : null,
  }))
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'netbox@example.invalid', display_name: 'NetBox owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['networks.view', 'networks.edit'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  if (organization) await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Regional Technology Group', classifications: ['client'], capabilities: ['overview', 'networks'],
    organization: { id: organizationId, name: 'Regional Technology Group', legal_name: '', website: '', classifications: ['client'], access_mode: 'assigned_only', created_at: '2026-09-25T12:00:00Z', updated_at: '2026-09-25T12:00:00Z' },
  } }))
  await page.route('**/collection-preferences/network-netbox', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/networks/netbox/reference-collection?*', (route) => {
    requests.push(route.request().url())
    const query = new URL(route.request().url()).searchParams
    const pageNumber = Number(query.get('page') ?? 1), pageSize = Number(query.get('page_size') ?? 25)
    let found = records.filter((record) => `${record.entity_name} ${record.object_id}`.toLowerCase().includes((query.get('q') ?? '').toLowerCase()))
    if (query.get('object_type')) found = found.filter((record) => record.object_type === query.get('object_type'))
    if (query.get('ordering')?.startsWith('-')) found = [...found].reverse()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * pageSize, pageNumber * pageSize), count: found.length, page: pageNumber, page_size: pageSize, has_more: pageNumber * pageSize < found.length, can_manage: true } })
  })
  return { records, requests }
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`NetBox register fits ${width}px and searches all identities`, async ({ page }) => {
    const { records } = await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/networks?view=netbox')
    await expect(page.getByText('31 NetBox identities', { exact: true })).toBeVisible()
    await expect(page.getByText(records[0].entity_name, { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.netbox-register').analyze()).violations).toEqual([])
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(page.getByText('Rack 026', { exact: true })).toBeVisible()
    await page.getByRole('searchbox', { name: 'Search NetBox identities' }).fill('Rack 031')
    await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
    await expect(page.getByText('Rack 031', { exact: true })).toBeVisible()
    await expect(page).not.toHaveURL(/netbox_page=2/)
    await page.getByRole('button', { name: 'Columns', exact: true }).click()
    await expect(page.getByRole('checkbox', { name: 'TekDocs record', exact: true })).toBeDisabled()
    await page.getByRole('checkbox', { name: 'Observation', exact: true }).uncheck()
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.reload()
    if (width >= 768) await expect(page.getByRole('columnheader', { name: 'Observation' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

for (const width of [390, 1280]) {
  test(`Organization NetBox register uses its exact workspace at ${width}px`, async ({ page }) => {
    const { requests } = await fixtures(page, true)
    await page.setViewportSize({ width, height: 600 })
    await page.goto(`/workspaces/organizations/${organizationId}/networks?view=netbox`)
    await expect(page.getByText('31 NetBox identities', { exact: true })).toBeVisible()
    expect(requests.some((url) => url.includes(`/workspaces/organizations/${organizationId}/networks/netbox/reference-collection?`))).toBe(true)
    expect(requests.some((url) => url.includes('/workspaces/msp/networks/netbox/reference-collection?'))).toBe(false)
    expect((await new AxeBuilder({ page }).include('.netbox-register').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
