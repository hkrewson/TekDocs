import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

type OrganizationInput = {
  name: string
  legal_name: string
  website: string
  classifications: string[]
}

test('organization administration supports create, edit, filter, and archive', async ({ page, baseURL }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const id = crypto.randomUUID()
  let organizations: Array<Record<string, unknown>> = []
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/api/v1/organizations**', async (route) => {
    const detail = new URL(route.request().url()).pathname.endsWith(`/${id}`)
    if (route.request().method() === 'GET') {
      if (detail) return route.fulfill({ json: organizations[0] })
      return route.fulfill({ json: { results: organizations, page: 1, page_size: 25, count: organizations.length, has_more: false } })
    }
    expect(route.request().headers()['x-csrftoken']).toBeTruthy()
    if (route.request().method() === 'DELETE') {
      organizations = []
      return route.fulfill({ status: 204 })
    }
    const input = route.request().postDataJSON() as OrganizationInput
    if (detail) {
      organizations = [{ ...organizations[0], ...input, updated_at: new Date().toISOString() }]
      return route.fulfill({ json: organizations[0] })
    }
    organizations = [{ id, ...input, access_mode: 'assigned_only', created_at: new Date().toISOString(), updated_at: new Date().toISOString() }]
    return route.fulfill({ status: 201, json: organizations[0] })
  })

  await page.goto('/organizations')
  await expect(page.getByText('No organizations have been added.')).toBeVisible()
  await page.getByRole('button', { name: 'New organization' }).click()
  await page.getByLabel('Display name').fill('Acme Dental')
  await page.getByRole('checkbox', { name: 'Partner' }).check()
  await page.getByRole('button', { name: 'Save organization' }).click()
  await expect(page.getByRole('status')).toHaveText('Acme Dental was added.')
  await expect(page.getByText('Client, Partner')).toBeVisible()

  await page.getByRole('button', { name: 'Edit details' }).click()
  await page.getByLabel('Display name').fill('Acme Health')
  await page.getByRole('button', { name: 'Save organization' }).click()
  await expect(page.getByRole('heading', { name: 'Acme Health' })).toBeVisible()
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  if (testInfo.project.name === 'chromium') await page.screenshot({ path: '../artifacts/clients-organization-record-1440.png', fullPage: true })

  await page.setViewportSize({ width: 320, height: 900 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1))
    .toBe(true)
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  if (testInfo.project.name === 'chromium') await page.screenshot({ path: '../artifacts/clients-organization-record-320.png', fullPage: true })

  await page.getByText('More', { exact: true }).click()
  await page.getByRole('button', { name: 'Archive', exact: true }).click()
  await page.getByRole('button', { name: 'Archive organization' }).click()
  await expect(page.getByRole('status')).toHaveText('Acme Health was moved to the recycle bin.')
  await expect(page.getByText('No organizations have been added.')).toBeVisible()
})
