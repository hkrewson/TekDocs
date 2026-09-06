import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const supplierId = crypto.randomUUID()

test('supplier products use plain version language and explain archive consequences', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner',
    permissions: ['assets.view', 'assets.edit'],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${supplierId}`, (route) => route.fulfill({ json: {
    kind: 'organization',
    id: supplierId,
    name: 'Example Manufacturer',
    classifications: ['vendor', 'manufacturer'],
    capabilities: ['overview', 'products'],
    organization: { id: supplierId, name: 'Example Manufacturer', legal_name: '', website: '', classifications: ['vendor', 'manufacturer'], created_at: '2026-09-05T12:00:00Z', updated_at: '2026-09-05T12:00:00Z' },
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${supplierId}/catalog/specification-definitions`, (route) => route.fulfill({ json: {
    results: [{ id: 'template-1', name: 'Managed switch', product_kind: 'hardware', versions: [{ id: 'template-version-1', version: 1, schema: { type: 'object', additionalProperties: false, properties: { ports: { type: 'integer', title: 'Port count' } }, required: ['ports'] }, checksum: 'a'.repeat(64), created_by: 'Primary Owner', created_at: '2026-09-05T12:00:00Z' }] }],
    can_manage: true,
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${supplierId}/catalog/products*`, (route) => route.fulfill({ json: {
    results: [{
      id: 'product-1', name: 'EdgeSwitch', kind: 'hardware', description: 'Managed switching product line', updated_at: '2026-09-05T12:00:00Z', documents: [],
      models: [{ id: 'model-1', name: 'EdgeSwitch 24', model_number: 'ES-24', current_revision: { id: 'revision-1', revision: 1, parent_id: null, specification_version_id: 'template-version-1', specification_definition_id: 'template-1', specification_definition_name: 'Managed switch', specification_version: 1, lifecycle: 'active', specifications: { ports: 24 }, notes: '', checksum: 'b'.repeat(64), created_by: 'Primary Owner', created_at: '2026-09-05T12:00:00Z' }, revisions: [] }],
    }],
    can_manage: true,
  } }))

  await page.goto(`/workspaces/organizations/${supplierId}/products`)
  await expect(page.getByRole('heading', { name: 'Example Manufacturer products' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Specification templates' })).toBeVisible()
  await expect(page.getByText('ES-24 · Active · version 1')).toBeVisible()

  await page.getByRole('button', { name: 'Archive EdgeSwitch' }).click()
  const confirmation = page.getByRole('alertdialog')
  await expect(confirmation).toContainText('Existing assets keep their saved product and model details.')
  await expect(confirmation).toContainText('TekDocs does not provide a restore action')
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})
