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

test('organization administration supports create, edit, filter, and archive', async ({ page, baseURL }) => {
  const id = crypto.randomUUID()
  let organizations: Array<Record<string, unknown>> = []
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/api/v1/organizations', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: organizations })
    expect(route.request().headers()['x-csrftoken']).toBeTruthy()
    const input = route.request().postDataJSON() as OrganizationInput
    organizations = [{ id, ...input, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }]
    return route.fulfill({ status: 201, json: organizations[0] })
  })
  await page.route(`**/api/v1/organizations/${id}`, async (route) => {
    expect(route.request().headers()['x-csrftoken']).toBeTruthy()
    if (route.request().method() === 'DELETE') {
      organizations = []
      return route.fulfill({ status: 204 })
    }
    const input = route.request().postDataJSON() as OrganizationInput
    organizations = [{ ...organizations[0], ...input, updated_at: new Date().toISOString() }]
    return route.fulfill({ json: organizations[0] })
  })

  await page.goto('/organizations')
  await expect(page.getByText('No organizations have been added.')).toBeVisible()
  await page.getByRole('button', { name: 'New organization' }).click()
  await page.getByLabel('Display name').fill('Acme Dental')
  await page.getByRole('checkbox', { name: 'Partner' }).check()
  await page.getByRole('button', { name: 'Save organization' }).click()
  await expect(page.getByRole('status')).toHaveText('Organization added.')
  await expect(page.getByText('Client, Partner')).toBeVisible()

  await page.getByRole('button', { name: 'Edit Acme Dental' }).click()
  await page.getByLabel('Display name').fill('Acme Health')
  await page.getByRole('button', { name: 'Save organization' }).click()
  await expect(page.getByRole('button', { name: 'Edit Acme Health' })).toBeVisible()
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })

  await page.getByRole('button', { name: 'Archive Acme Health' }).click()
  await page.getByRole('button', { name: 'Archive organization' }).click()
  await expect(page.getByRole('status')).toHaveText('Organization archived.')
  await expect(page.getByText('No organizations have been added.')).toBeVisible()
})
