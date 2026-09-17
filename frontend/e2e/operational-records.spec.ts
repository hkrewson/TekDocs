import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const organizationId = crypto.randomUUID()
const personId = crypto.randomUUID()
const siteId = crypto.randomUUID()
const longOrganizationName = 'Lakeview Pediatric and Family Health Collaborative of Southern Wisconsin'
const longPersonName = 'Alexandria Morgan-Santiago Kensington'
const longSiteName = 'Northwest Regional Clinical Services and Technology Operations Campus'
const recordedAt = '2026-09-17T12:00:00Z'

const organization = {
  id: organizationId,
  name: longOrganizationName,
  legal_name: `${longOrganizationName}, Incorporated`,
  website: 'https://lakeview.example.com/technology-and-clinical-services',
  access_mode: 'assigned_only',
  classifications: ['client', 'partner'],
  created_at: recordedAt,
  updated_at: recordedAt,
}

const person = {
  id: personId,
  association_id: crypto.randomUUID(),
  organization_id: null,
  full_name: longPersonName,
  preferred_name: 'Alex',
  kind: 'employee',
  role: 'Principal Infrastructure and Identity Operations Administrator',
  responsibility: 'Coordinates regional network, identity, and clinical systems continuity',
  location: 'Northwest Regional Campus',
  office: 'Technology Operations Center 214',
  site_id: null,
  structured_location_id: null,
  phone: '+1 555 010 0240',
  email: 'alexandria.morgan-santiago@example.com',
  created_at: recordedAt,
  updated_at: recordedAt,
}

const site = {
  id: siteId,
  organization_id: null,
  name: longSiteName,
  code: 'NWR-CS-TECH-OPS',
  address_line_1: '1000 East Regional Medical Services Boulevard',
  address_line_2: 'Clinical Technology Operations Center, Suite 214',
  city: 'Madison',
  region: 'Wisconsin',
  postal_code: '53703',
  country_code: 'US',
  timezone: 'America/Chicago',
  phone: '+1 555 010 0300',
  locations: [{ id: crypto.randomUUID(), site_id: siteId, parent_id: null, name: 'Clinical Technology Operations Center', kind: 'office', code: 'CTOC-214', created_at: recordedAt, updated_at: recordedAt }],
  created_at: recordedAt,
  updated_at: recordedAt,
}

const pageResult = (records: unknown[]) => ({ results: records, page: 1, page_size: 25, count: records.length, has_more: false })

async function mockOperationalRecords(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner',
    permissions: [],
  } }))
  await page.route('**/api/v1/organizations**', (route) => {
    const detail = new URL(route.request().url()).pathname.endsWith(`/${organizationId}`)
    return route.fulfill({ json: detail ? organization : pageResult([organization]) })
  })
  await page.route('**/api/v1/people**', (route) => {
    const detail = new URL(route.request().url()).pathname.endsWith(`/${personId}`)
    return route.fulfill({ json: detail ? person : pageResult([person]) })
  })
  await page.route('**/api/v1/sites**', (route) => {
    const detail = new URL(route.request().url()).pathname.endsWith(`/${siteId}`)
    return route.fulfill({ json: detail ? site : pageResult([site]) })
  })
}

async function expectViewportContained(page: Page) {
  const measurement = await page.evaluate(() => ({
    contained: document.documentElement.scrollWidth <= window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    offenders: [...document.querySelectorAll<HTMLElement>('body *')].map((element) => {
      const bounds = element.getBoundingClientRect()
      return { tag: element.tagName, className: element.className, right: Math.round(bounds.right), width: element.scrollWidth, text: element.textContent?.trim().slice(0, 60) }
    }).filter((item) => item.right > window.innerWidth + 1).slice(0, 8),
  }))
  expect(measurement.contained, JSON.stringify(measurement)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`organization, person, and site records remain usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 })
    await mockOperationalRecords(page)

    await page.goto('/organizations')
    await page.getByRole('button', { name: longOrganizationName, exact: true }).click()
    await expect(page.getByRole('heading', { name: longOrganizationName })).toBeVisible()
    await expect(page.getByText('Assigned staff only')).toBeVisible()
    await expectViewportContained(page)
    if (width === 390) expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)

    await page.goto('/people')
    await page.getByRole('button', { name: longPersonName, exact: true }).click()
    await expect(page.getByRole('heading', { name: longPersonName })).toBeVisible()
    await expect(page.getByText(person.responsibility)).toBeVisible()
    await expectViewportContained(page)
    if (width === 390) expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)

    await page.goto('/sites')
    await page.getByRole('button', { name: longSiteName, exact: true }).click()
    await expect(page.getByRole('heading', { name: longSiteName })).toBeVisible()
    await expect(page.getByText('Clinical Technology Operations Center', { exact: true })).toBeVisible()
    await expectViewportContained(page)
    if (width === 390) expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([])
  })
}

test('record drawers preserve history and protect dirty organization edits', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockOperationalRecords(page)
  await page.goto('/organizations')
  await page.getByRole('button', { name: longOrganizationName, exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`organization=${organizationId}`))

  await page.goBack()
  await expect(page).not.toHaveURL(/organization=/)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.goForward()
  await expect(page.getByRole('heading', { name: longOrganizationName })).toBeVisible()

  await page.getByRole('button', { name: 'Edit details' }).click()
  await page.getByLabel('Legal name').fill('A changed legal name')
  await page.getByRole('link', { name: 'Back to organizations' }).click()
  await expect(page.getByRole('alertdialog')).toContainText('Unsaved changes')
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page.getByLabel('Legal name')).toHaveValue('A changed legal name')
  await page.getByRole('link', { name: 'Back to organizations' }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
