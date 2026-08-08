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
  capabilities: ['overview', 'documentation', 'people', 'assets', 'networks', 'credentials'],
  organization: { id: '', name: 'Acme Dental', legal_name: 'Acme Dental, LLC', website: '', classifications: ['client'], created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
}
clientWorkspace.organization.id = clientWorkspace.id

const supplierWorkspace = {
  kind: 'organization',
  id: crypto.randomUUID(),
  name: 'Northwind Supply',
  classifications: ['vendor', 'manufacturer'],
  capabilities: ['overview', 'documentation', 'people', 'products'],
  organization: { id: '', name: 'Northwind Supply', legal_name: 'Northwind Supply Company', website: '', classifications: ['vendor', 'manufacturer'], created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
}
supplierWorkspace.organization.id = supplierWorkspace.id

async function mockWorkspaceApplication(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/api/v1/workspaces/organizations**', (route) => {
    const url = new URL(route.request().url())
    const id = url.pathname.split('/').at(-1)
    if (id === clientWorkspace.id) return route.fulfill({ json: clientWorkspace })
    if (id === supplierWorkspace.id) return route.fulfill({ json: supplierWorkspace })
    const query = url.searchParams.get('q')?.toLowerCase() ?? ''
    const choices = [clientWorkspace, supplierWorkspace].filter((workspace) => workspace.name.toLowerCase().includes(query))
    return route.fulfill({ json: { results: choices.map(({ id, name, classifications, capabilities }) => ({ id, name, classifications, capabilities })), page: 1, page_size: 15, has_more: false } })
  })
}

test('workspace switcher preserves routes, capability navigation, history, and accessibility', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto('/documentation')

  await page.getByRole('button', { name: /Current workspace: Example MSP/ }).click()
  await page.getByRole('textbox', { name: 'Find a workspace' }).fill('north')
  await page.getByRole('button', { name: 'Northwind Supply. Vendor · Manufacturer' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${supplierWorkspace.id}/documentation$`))
  await expect(page.getByRole('link', { name: 'Products' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Networks' })).not.toBeVisible()
  await expect(page).toHaveTitle(/Northwind Supply · Documentation · TekDocs/)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])

  await page.getByRole('link', { name: 'Products' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${supplierWorkspace.id}/products$`))
  await page.getByRole('button', { name: /Current workspace: Northwind Supply/ }).click()
  await page.getByRole('button', { name: 'Example MSP. MSP workspace' }).click()
  await expect(page).toHaveURL(/\/overview$/)
  await page.goBack()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${supplierWorkspace.id}/products$`))
  await page.goForward()
  await expect(page).toHaveURL(/\/overview$/)
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
  await expect(page.getByRole('textbox', { name: 'Find a workspace' })).toBeVisible()
  await page.getByRole('textbox', { name: 'Find a workspace' }).fill('acme')
  await page.getByRole('button', { name: 'Acme Dental. Client' }).click()
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${clientWorkspace.id}/overview$`))
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
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
