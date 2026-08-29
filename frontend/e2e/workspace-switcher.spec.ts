import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
  role: 'owner',
  permissions: ['memberships.view', 'memberships.assign_role', 'organizations.manage_access', 'organizations.assign_staff'],
}

const accessMember = {
  id: crypto.randomUUID(),
  display_name: 'Morgan Ellis',
  email: 'morgan@example.com',
  role: 'read_only',
  is_owner: false,
  joined_at: '2026-08-08T13:00:00Z',
}

const accessCatalog = {
  permissions: [
    { key: 'memberships.assign_role', label: 'Assign tenant roles', category: 'Access control', requires_mfa: true },
    { key: 'organizations.manage_access', label: 'Manage organization access', category: 'Access control', requires_mfa: true },
    { key: 'organizations.assign_staff', label: 'Assign MSP staff', category: 'Access control', requires_mfa: true },
  ],
  custom_assignable_permissions: [
    { key: 'documents.edit', label: 'Edit documentation', category: 'Documentation', requires_mfa: true },
  ],
  roles: [
    { value: 'owner', label: 'Owner', description: 'Installation owner.', assignable_scope: 'installation', permissions: ['memberships.assign_role'] },
    { value: 'administrator', label: 'Administrator', description: 'Tenant administrator.', assignable_scope: 'tenant', permissions: ['memberships.assign_role'] },
    { value: 'technician', label: 'Technician', description: 'Operational staff.', assignable_scope: 'tenant', permissions: [] },
    { value: 'contributor', label: 'Contributor', description: 'Documentation contributor.', assignable_scope: 'tenant', permissions: [] },
    { value: 'read_only', label: 'Read-only', description: 'Read-only staff.', assignable_scope: 'tenant', permissions: [] },
    { value: 'client_administrator', label: 'Client Administrator', description: 'Client administrator.', assignable_scope: 'organization', permissions: [] },
    { value: 'client_user', label: 'Client User', description: 'Client user.', assignable_scope: 'organization', permissions: [] },
  ],
}

const clientWorkspace = {
  kind: 'organization',
  id: crypto.randomUUID(),
  name: 'Acme Dental',
  classifications: ['client'],
  capabilities: ['overview', 'people', 'sites', 'custom_fields', 'documentation', 'files', 'assets', 'licenses', 'networks', 'domains', 'certificates', 'credentials', 'services', 'tickets', 'vendors'],
  organization: { id: '', name: 'Acme Dental', legal_name: 'Acme Dental, LLC', website: '', classifications: ['client'], created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
}
clientWorkspace.organization.id = clientWorkspace.id

const supplierWorkspace = {
  kind: 'organization',
  id: crypto.randomUUID(),
  name: 'Northwind Supply',
  classifications: ['vendor', 'manufacturer'],
  capabilities: ['overview', 'people', 'sites', 'custom_fields', 'documentation', 'files', 'products'],
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

const person = {
  id: crypto.randomUUID(),
  association_id: crypto.randomUUID(),
  organization_id: clientWorkspace.id,
  full_name: 'Jordan Avery',
  preferred_name: 'Jordy',
  kind: 'employee',
  role: 'Systems Administrator',
  responsibility: 'Network and identity operations',
  location: 'North Office',
  office: 'Desk 214',
  site_id: null,
  structured_location_id: null,
  phone: '+1 555 010 0240',
  email: 'jordan@example.com',
  created_at: '2026-08-08T12:00:00Z',
  updated_at: '2026-08-08T12:00:00Z',
}
const site = {
  id: crypto.randomUUID(), organization_id: clientWorkspace.id, name: 'North Campus', code: 'NORTH', address_line_1: '100 Main Street', address_line_2: '', city: 'Madison', region: 'WI', postal_code: '53703', country_code: 'US', timezone: 'America/Chicago', phone: '', created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z',
  locations: [{ id: crypto.randomUUID(), site_id: '', parent_id: null, name: 'Office 214', kind: 'office', code: '214', created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' }],
}
site.locations[0].site_id = site.id
const customFieldVersion = {
  id: crypto.randomUUID(), version: 1, label: 'Door code', description: 'Facilities entry code', required: false, field_type: 'text', schema: { type: 'string' }, display_order: 1, created_at: '2026-08-08T12:00:00Z',
}
const customFieldDefinition = {
  id: crypto.randomUUID(), key: 'door_code', entity_type: 'site', owner: 'organization', organization_id: clientWorkspace.id, inherited: false, archived: false, current_version: customFieldVersion, versions: [customFieldVersion],
}
const relationship = {
  id: crypto.randomUUID(),
  link_type: 'supplied_by',
  label: 'Supplied by',
  direction: 'outgoing',
  source_id: clientWorkspace.id,
  target_id: supplierWorkspace.id,
  related_entity: { id: supplierWorkspace.id, display_name: supplierWorkspace.name, entity_type: 'organization', visibility: 'msp_private', workspace_label: 'MSP organization directory', eligible_link_types: ['related_to', 'supplied_by', 'manufactured_by'] },
  created_at: '2026-08-08T12:00:00Z',
}

async function mockWorkspaceApplication(page: Page) {
  const customRole = { id: crypto.randomUUID(), name: 'Documentation lead', description: '', scope: 'tenant', permissions: ['documents.edit'], assignment_count: 0, archived_at: null, created_at: '2026-08-08T13:00:00Z', updated_at: '2026-08-08T13:00:00Z' }
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/api/v1/access-control/catalog', (route) => route.fulfill({ json: accessCatalog }))
  await page.route('**/api/v1/access-control/custom-roles**', (route) => route.fulfill({ status: route.request().method() === 'POST' ? 201 : 200, json: route.request().method() === 'GET' ? [] : customRole }))
  await page.route('**/api/v1/access-control/collections**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/access-control/role-assignments**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/access-control/members', (route) => route.fulfill({ json: [
    { ...context.user, role: 'owner', is_owner: true, joined_at: '2026-08-08T12:00:00Z' },
    accessMember,
  ] }))
  await page.route('**/api/v1/access-control/members/*', (route) => route.fulfill({ json: { ...accessMember, role: 'technician' } }))
  await page.route('**/api/v1/access-control/organizations', (route) => route.fulfill({ json: [
    { id: clientWorkspace.id, name: clientWorkspace.name, access_mode: 'all_authorized', assigned_staff: [] },
  ] }))
  await page.route('**/api/v1/access-control/organizations/*', (route) => route.fulfill({ json: {
      id: clientWorkspace.id,
      name: clientWorkspace.name,
      access_mode: 'assigned_only',
      assigned_staff: [],
    } }))
  await page.route('**/api/v1/access-control/organizations/*/staff**', (route) => route.fulfill({ json: {
    id: clientWorkspace.id,
    name: clientWorkspace.name,
    access_mode: 'assigned_only',
    assigned_staff: route.request().method() === 'POST' ? [{ ...accessMember, role: 'technician' }] : [],
  } }))
  await page.route('**/api/v1/entity-link-types', (route) => route.fulfill({ json: [
    { value: 'related_to', forward_label: 'Related to', inverse_label: 'Related to', symmetric: true, target_types: [] },
    { value: 'supplied_by', forward_label: 'Supplied by', inverse_label: 'Supplies', symmetric: false, target_types: ['organization'] },
  ] }))
  await page.route('**/api/v1/workspaces/organizations**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/entities/search')) {
      const query = url.searchParams.get('q')?.toLowerCase() ?? ''
      const results = [supplierWorkspace]
        .filter((workspace) => workspace.name.toLowerCase().includes(query))
        .map((workspace) => ({ id: workspace.id, display_name: workspace.name, entity_type: 'organization', visibility: 'msp_private', workspace_label: 'MSP organization directory', eligible_link_types: ['related_to', 'supplied_by', 'manufactured_by'] }))
      return route.fulfill({ json: { results, page: 1, page_size: 15, count: results.length, has_more: false } })
    }
    if (url.pathname.endsWith('/links')) {
      if (route.request().method() === 'POST') return route.fulfill({ status: 201, json: relationship })
      return route.fulfill({ json: { relationships: [] } })
    }
    if (/\/links\/[^/]+$/.test(url.pathname) && route.request().method() === 'DELETE') return route.fulfill({ status: 204 })
    if (url.pathname.endsWith('/custom-field-definitions')) {
      return route.fulfill({ json: { results: [customFieldDefinition], count: 1 } })
    }
    if (url.pathname.endsWith('/custom-fields')) {
      return route.fulfill({ json: { entity_id: site.id, entity_type: 'site', fields: [{ definition: customFieldDefinition, has_value: true, value: '4231', value_version_id: customFieldVersion.id, value_version: 1, is_current: true, valid_for_current: true }] } })
    }
    if (url.pathname.endsWith(`/custom-fields/${customFieldDefinition.id}`)) {
      return route.fulfill({ json: { entity_id: site.id, entity_type: 'site', fields: [{ definition: customFieldDefinition, has_value: true, value: '9912', value_version_id: customFieldVersion.id, value_version: 1, is_current: true, valid_for_current: true }] } })
    }
    if (url.pathname.endsWith('/people')) {
      return route.fulfill({ json: { results: [person], page: 1, page_size: 25, count: 1, has_more: false } })
    }
    if (url.pathname.endsWith('/sites')) return route.fulfill({ json: { results: [site], count: 1 } })
    if (url.pathname.endsWith('/documents')) return route.fulfill({ json: { results: [], count: 0 } })
    if (url.pathname.endsWith('/assets')) return route.fulfill({ json: { results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true, can_view_relationships: true, can_create_relationships: true, can_archive_relationships: true } })
    if (url.pathname.endsWith('/products')) return route.fulfill({ json: { results: [], count: 0 } })
    if (url.pathname.endsWith('/specification-definitions')) return route.fulfill({ json: { results: [], count: 0 } })
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

test('owner reviews role, client access-mode, and staff-assignment changes through the policy interface', async ({ page, baseURL }) => {
  if (!baseURL) throw new Error('Browser test base URL is unavailable.')
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await mockWorkspaceApplication(page)
  await page.goto('/overview')

  await page.getByRole('button', { name: /Account menu for Primary Owner/ }).click()
  await page.getByRole('menuitem', { name: 'Access control' }).click()
  await expect(page.getByRole('heading', { name: 'Access control' })).toBeVisible()

  await page.getByRole('combobox', { name: 'Role for Morgan Ellis' }).selectOption('technician')
  await page.getByRole('button', { name: 'Review change' }).first().click()
  await expect(page.getByRole('alertdialog')).toContainText('Change Morgan Ellis from Read-only to Technician')
  await page.getByRole('button', { name: 'Confirm change' }).click()
  await expect(page.getByRole('status')).toContainText("Morgan Ellis's role was updated")

  await page.getByRole('combobox', { name: 'Access mode for Acme Dental' }).selectOption('assigned_only')
  await page.getByRole('button', { name: 'Review change' }).last().click()
  await expect(page.getByRole('alertdialog')).toContainText('explicitly assigned MSP staff')
  await page.getByRole('button', { name: 'Confirm change' }).click()
  await expect(page.getByRole('status')).toContainText("Acme Dental's access mode was updated")

  await page.getByRole('combobox', { name: 'Staff member for Acme Dental' }).selectOption(accessMember.id)
  await page.getByRole('button', { name: 'Review assignment' }).click()
  await expect(page.getByRole('alertdialog')).toContainText('MSP role still determines what they can do')
  await page.getByRole('button', { name: 'Confirm change' }).click()
  await expect(page.getByRole('status')).toContainText('Morgan Ellis was assigned to Acme Dental')
  await page.getByRole('button', { name: 'Remove' }).click()
  await page.getByRole('button', { name: 'Confirm change' }).click()
  await expect(page.getByRole('status')).toContainText('Morgan Ellis was removed from Acme Dental')
  await page.getByRole('textbox', { name: 'Role name' }).fill('Documentation lead')
  await page.getByRole('checkbox', { name: /Edit documentation/ }).check()
  await page.getByRole('button', { name: 'Review role' }).click()
  await expect(page.getByRole('alertdialog')).toContainText('grants nothing until assigned')
  await page.getByRole('button', { name: 'Confirm change' }).click()
  await expect(page.getByText('Documentation lead was created.')).toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})

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
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible()
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
  await expect(page.getByRole('link', { name: 'Accounting' })).toHaveCount(0)

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
  await expect(page.getByRole('link', { name: 'Accounting' })).toHaveCount(0)
})

test('client People directory supports field controls and remains accessible', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/people`)

  await expect(page.getByRole('heading', { name: 'People' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Jordan Avery', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Choose visible columns' }).click()
  await page.getByRole('checkbox', { name: 'Responsibility' }).check()
  await expect(page.getByRole('columnheader', { name: 'Responsibility' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Network and identity operations' })).toBeVisible()
  await page.getByRole('button', { name: 'Full name' }).click()
  await expect(page.getByRole('columnheader', { name: 'Full name' })).toHaveAttribute('aria-sort', 'descending')
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('client Sites area shows nested workspace-owned locations accessibly', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/sites`)

  await expect(page.getByRole('heading', { name: 'Sites' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'North Campus' })).toBeVisible()
  await expect(page.getByText('Office 214')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sites' })).toHaveAttribute('href', `/workspaces/organizations/${clientWorkspace.id}/sites`)
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})

test('client custom-field definitions and Site values remain workspace scoped and accessible', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/custom_fields`)

  await expect(page.getByRole('heading', { name: 'Custom fields' })).toBeVisible()
  await expect(page.getByText('Door code', { exact: true })).toBeVisible()
  await expect(page.getByText('This organization')).toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])

  await page.getByRole('link', { name: 'Sites' }).click()
  await page.getByRole('button', { name: 'Custom fields for site North Campus' }).click()
  await expect(page.getByRole('heading', { name: 'Custom fields for North Campus' })).toBeVisible()
  await expect(page.getByLabel('Door code')).toHaveValue('4231')
  await page.getByLabel('Door code').fill('9912')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByLabel('Door code')).toHaveValue('9912')
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})

test('client overview searches and creates a typed organization relationship accessibly', async ({ page, baseURL }) => {
  if (!baseURL) throw new Error('Browser test base URL is unavailable.')
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await mockWorkspaceApplication(page)
  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/overview`)

  await expect(page.getByRole('heading', { name: 'Organization relationships' })).toBeVisible()
  await expect(page.getByText('No relationships have been added.')).toBeVisible()
  await page.getByRole('button', { name: 'Add relationship' }).click()
  await page.getByLabel('Relationship type').selectOption('supplied_by')
  await page.getByRole('searchbox', { name: 'Related organization' }).fill('Northwind')
  await page.getByRole('radio', { name: /Northwind Supply/ }).check()
  await page.getByRole('button', { name: 'Add supplied by' }).click()

  await expect(page.getByText('Relationship added.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Northwind Supply' })).toHaveAttribute('href', `/workspaces/organizations/${supplierWorkspace.id}/overview`)
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
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

test('keyboard-only workspace switching restores focus and keeps unsupported routes in context', async ({ page }) => {
  await mockWorkspaceApplication(page)
  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/overview`)

  const trigger = page.getByRole('button', { name: /Current workspace: Acme Dental/ })
  await expect(trigger).toBeVisible()
  let focusedLabel = ''
  for (let step = 0; step < 20 && !focusedLabel.includes('Current workspace: Acme Dental'); step += 1) {
    await page.keyboard.press('Tab')
    const focused = page.locator(':focus')
    focusedLabel = (await focused.count()) > 0 ? ((await focused.getAttribute('aria-label')) ?? '') : ''
  }
  await expect(trigger).toBeFocused()
  await page.keyboard.press('Enter')
  const search = page.getByRole('textbox', { name: 'Find a client' })
  await expect(search).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('button', { name: 'Back to Example MSP. MSP workspace' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()

  await page.goto(`/workspaces/organizations/${clientWorkspace.id}/unsupported-area`)
  await expect(page).toHaveURL(new RegExp(`/workspaces/organizations/${clientWorkspace.id}/overview$`))
  await expect(page.getByRole('button', { name: /Current workspace: Acme Dental/ })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('workspace denial and capability-denied states remain accessible and non-disclosing', async ({ page }) => {
  await mockWorkspaceApplication(page)

  await page.goto(`/workspaces/organizations/${supplierWorkspace.id}/networks`)
  await expect(page.getByRole('heading', { name: 'Area unavailable' })).toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])

  const deniedId = crypto.randomUUID()
  await page.route(`**/api/v1/workspaces/organizations/${deniedId}`, (route) => route.fulfill({ status: 404, body: 'Confidential Organization' }))
  await page.goto(`/workspaces/organizations/${deniedId}/overview`)
  await expect(page.getByRole('heading', { name: 'Workspace unavailable' })).toBeVisible()
  await expect(page.getByText('Confidential Organization')).not.toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})
