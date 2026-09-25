import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const organizationId = '00000000-0000-4000-8000-000000000094'
const references = Array.from({ length: 31 }, (_, index) => ({
  id: `94000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  title: index === 30 ? 'Regional emergency firewall administrator with delegated recovery access' : `Infrastructure credential ${String(index + 1).padStart(2, '0')}`,
  provider: 'onepassword', provider_label: '1Password', updated_at: '2026-09-24T12:00:00Z', can_manage: true, can_open: true,
}))

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: [], surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Regional Clinical Technology Group', classifications: ['client'], capabilities: ['overview', 'credentials'],
    organization: { id: organizationId, name: 'Regional Clinical Technology Group', legal_name: '', website: '', classifications: ['client'], access_mode: 'assigned_only', created_at: '2026-09-24T12:00:00Z', updated_at: '2026-09-24T12:00:00Z' },
  } }))
  await page.route('**/api/v1/credential-references**', credentialResponse)
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/credential-references**`, credentialResponse)
}

async function credentialResponse(route: Route) {
  const request = route.request()
  const url = new URL(request.url())
  const id = references.find((reference) => url.pathname.endsWith(`/${reference.id}`))
  if (id) return route.fulfill({ json: id })
  const query = (url.searchParams.get('q') ?? '').toLowerCase()
  const page = Number(url.searchParams.get('page') ?? 1)
  const pageSize = Number(url.searchParams.get('page_size') ?? 25)
  const filtered = references.filter((reference) => reference.title.toLowerCase().includes(query))
  const results = filtered.slice((page - 1) * pageSize, page * pageSize)
  return route.fulfill({ json: { results, page, page_size: pageSize, count: filtered.length, has_more: page * pageSize < filtered.length, can_manage: true } })
}

async function expectContained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`credential references remain focused and usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 600 : 760 })
    await fixtures(page)
    await page.goto('/credentials')

    await expect(page.getByRole('heading', { name: 'Credential links' })).toBeVisible()
    await expect(page.getByText('31 total')).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    const longRecord = page.getByRole('button', { name: /Regional emergency firewall administrator/ })
    await expect(longRecord).toBeVisible()
    await longRecord.click()

    const drawer = page.getByRole('dialog', { name: references[30].title })
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole('link', { name: 'Open in 1Password' })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`credential=${references[30].id}`))
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    if (width < 768) expect((await drawer.boundingBox())?.width).toBe(width)
    await expectContained(page)
    if (width === 390) expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(drawer).toHaveCount(0)
    await expect(page).toHaveURL(/page=2/)
    await expect(page).not.toHaveURL(/credential=/)
  })
}

test('organization direct links load off-page records and protect edits', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 650 })
  await fixtures(page)
  await page.goto(`/workspaces/organizations/${organizationId}/credentials?credential=${references[30].id}`)

  const drawer = page.getByRole('dialog', { name: references[30].title })
  await expect(drawer).toBeVisible()
  await drawer.getByRole('button', { name: 'Edit' }).click()
  await drawer.getByLabel('Title').fill('Changed emergency credential title')
  await drawer.getByRole('link', { name: 'Back to credential links' }).click()
  await expect(page.getByRole('dialog', { name: 'Unsaved changes' })).toContainText('Unsaved changes')
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByLabel('Title')).toHaveValue('Changed emergency credential title')
  await drawer.getByRole('link', { name: 'Back to credential links' }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(drawer).toHaveCount(0)
  await expect(page).not.toHaveURL(/credential=/)
})
