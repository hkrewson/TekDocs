import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

const clientWorkspace = {
  kind: 'organization',
  id: crypto.randomUUID(),
  name: 'Acme Dental',
  classifications: ['client'],
  capabilities: ['overview', 'people', 'documentation', 'files', 'assets', 'licenses', 'networks', 'domains', 'certificates', 'credentials', 'services', 'tickets', 'vendors'],
  organization: { id: '', name: 'Acme Dental', legal_name: 'Acme Dental, LLC', website: '', classifications: ['client'], created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
}
clientWorkspace.organization.id = clientWorkspace.id

const supplierWorkspace = {
  kind: 'organization',
  id: crypto.randomUUID(),
  name: 'Northwind Supply',
  classifications: ['vendor', 'manufacturer'],
  capabilities: ['overview', 'people', 'documentation', 'files', 'products'],
  organization: { id: '', name: 'Northwind Supply', legal_name: 'Northwind Supply Company', website: '', classifications: ['vendor', 'manufacturer'], created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
}
supplierWorkspace.organization.id = supplierWorkspace.id

const secondClientWorkspace = {
  ...clientWorkspace,
  id: crypto.randomUUID(),
  name: 'Beacon Legal',
  organization: { ...clientWorkspace.organization, id: '', name: 'Beacon Legal', legal_name: 'Beacon Legal, LLC' },
}
secondClientWorkspace.organization.id = secondClientWorkspace.id

async function mockWorkspaceApplication(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/api/v1/workspaces/organizations**', (route) => {
    const url = new URL(route.request().url())
    const id = url.pathname.split('/').at(-1)
    if (id === clientWorkspace.id) return route.fulfill({ json: clientWorkspace })
    if (id === secondClientWorkspace.id) return route.fulfill({ json: secondClientWorkspace })
    if (id === supplierWorkspace.id) return route.fulfill({ json: supplierWorkspace })
    const query = url.searchParams.get('q')?.toLowerCase() ?? ''
    const classification = url.searchParams.get('classification')
    const choices = [clientWorkspace, secondClientWorkspace, supplierWorkspace]
      .filter((workspace) => !classification || workspace.classifications.includes(classification))
      .filter((workspace) => workspace.name.toLowerCase().includes(query))
    return route.fulfill({ json: { results: choices.map(({ id, name, classifications, capabilities }) => ({ id, name, classifications, capabilities })), page: 1, page_size: 15, has_more: false } })
  })
}

test('workspace switcher preserves routes, capability navigation, history, and accessibility', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto('/documentation')

  await page.getByRole('button', { name: /Current workspace: Example MSP/ }).click()
  await page.getByRole('textbox', { name: 'Find an organization' }).fill('north')
  await page.getByRole('button', { name: 'Northwind Supply. Vendor · Manufacturer' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${supplierWorkspace.id}/documentation$`))
  await expect(page.getByRole('link', { name: 'Products' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Networks' })).not.toBeVisible()
  await expect(page).toHaveTitle(/Northwind Supply · Documentation · TekDocs/)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])

  await page.getByRole('link', { name: 'Products' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${supplierWorkspace.id}/products$`))
  await page.getByRole('button', { name: /Current workspace: Northwind Supply/ }).click()
  await page.getByRole('button', { name: 'Back to Example MSP. MSP workspace' }).click()
  await expect(page).toHaveURL((url) => url.pathname === '/products')
  await page.goBack()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${supplierWorkspace.id}/products$`))
  await page.goForward()
  await expect(page).toHaveURL((url) => url.pathname === '/products')
})

test('direct workspace links reload deterministically and denial stays value-free', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/assets`)
  await expect(page.getByRole('heading', { name: 'Assets' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Assets' })).toBeVisible()

  const deniedId = crypto.randomUUID()
  await page.route(`**/api/v1/workspaces/organizations/${deniedId}`, (route) => route.fulfill({ status: 403, body: 'Private Client Name' }))
  await page.goto(`/workspaces/organizations/${deniedId}/overview`)
  await expect(page.getByRole('heading', { name: 'Workspace unavailable' })).toBeVisible()
  await expect(page.getByText('Private Client Name')).not.toBeVisible()
})

test('mobile workspace switching remains operable', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/overview')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: /Current workspace: Example MSP/ }).click()
  await expect(page.getByRole('textbox', { name: 'Find an organization' })).toBeVisible()
  await page.getByRole('textbox', { name: 'Find an organization' }).fill('acme')
  await page.getByRole('button', { name: 'Acme Dental. Client' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${clientWorkspace.id}/overview$`))
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
})

test('client context routes every menu item to that client and searches clients only', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/overview`)

  const navigationLinks = page.locator('aside nav a')
  await expect(navigationLinks).not.toHaveCount(0)
  for (const link of await navigationLinks.all()) {
    await expect(link).toHaveAttribute('href', new RegExp(`^/workspaces/organizations/${clientWorkspace.id}/`))
  }
  await expect(page.getByRole('link', { name: 'Accounting' })).not.toBeVisible()

  await page.getByRole('button', { name: /Current workspace: Acme Dental/ }).click()
  const search = page.getByRole('textbox', { name: 'Find a client' })
  await search.fill('north')
  await expect(page.getByText('No matching clients.')).toBeVisible()
  await search.fill('beacon')
  await page.getByRole('button', { name: 'Beacon Legal. Client' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${secondClientWorkspace.id}/overview$`))
  await expect(page.getByRole('button', { name: /Current workspace: Beacon Legal/ })).toBeVisible()

  await page.getByRole('button', { name: /Current workspace: Beacon Legal/ }).click()
  await page.getByRole('button', { name: 'Back to Example MSP. MSP workspace' }).click()
  await expect(page).toHaveURL((url) => url.pathname === '/overview')
  for (const link of await page.locator('aside nav a').all()) {
    await expect(link).not.toHaveAttribute('href', /^\/workspaces\/organizations\//)
  }
  await expect(page.getByRole('link', { name: 'Accounting' })).toHaveAttribute('href', '/accounting')
})

test('separate tabs retain independent URL-derived workspace context', async ({ page }) => {
  await mockWorkspaceApplication(page)
  const otherPage = await page.context().newPage()
  await mockWorkspaceApplication(otherPage)

  await page.goto(`/workspaces/organizations/${supplierWorkspace.id}/documentation`)
  await otherPage.goto(`/workspaces/organizations/${clientWorkspace.id}/assets`)
  await expect(page.getByRole('heading', { name: 'Documentation' })).toBeVisible()
  await expect(otherPage.getByRole('heading', { name: 'Assets' })).toBeVisible()

  await page.getByRole('link', { name: 'Products' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${supplierWorkspace.id}/products$`))
  await expect(otherPage).toHaveURL(new RegExp(`/workspaces/organizations/${clientWorkspace.id}/assets$`))
  await otherPage.close()
})
