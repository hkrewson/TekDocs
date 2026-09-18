import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const supplierId = crypto.randomUUID()
const productId = crypto.randomUUID()
const product = {
  id: productId,
  name: `EdgeSwitch ${'Industrial Distribution Platform '.repeat(5)}`.trim(),
  kind: 'hardware',
  description: `Managed switching for ${'distributed campus environments '.repeat(8)}`.trim(),
  unit_amount: '1299.0000',
  currency: 'USD',
  updated_at: '2026-09-17T12:00:00Z',
  documents: [{ id: 'document-link-1', publication_id: 'publication-1', model_id: 'model-1', model_name: 'EdgeSwitch 48', title: 'Installation and service guide', category: 'guide' }],
  models: [{
    id: 'model-1', name: 'EdgeSwitch 48', model_number: 'ES-48-LONG-CAMPUS-SKU',
    current_revision: { id: 'revision-1', revision: 3, parent_id: 'revision-0', specification_version_id: 'template-version-1', specification_definition_id: 'template-1', specification_definition_name: 'Managed switch', specification_version: 2, lifecycle: 'active', specifications: { ports: 48, uplink_type: '25-gigabit-fiber-with-redundant-paths' }, notes: 'Current production specification', checksum: 'b'.repeat(64), created_by: 'Primary Owner', created_at: '2026-09-17T12:00:00Z' },
    revisions: [{ id: 'revision-1', revision: 3, parent_id: 'revision-0', specification_version_id: 'template-version-1', specification_definition_id: 'template-1', specification_definition_name: 'Managed switch', specification_version: 2, lifecycle: 'active', specifications: { ports: 48, uplink_type: '25-gigabit-fiber-with-redundant-paths' }, notes: 'Current production specification', checksum: 'b'.repeat(64), created_by: 'Primary Owner', created_at: '2026-09-17T12:00:00Z' }],
  }],
}

async function mockProductWorkspace(page: Page, baseURL: string | undefined, listed = true) {
  let currentProduct = product
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL! }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner', permissions: ['assets.view', 'assets.edit', 'documents.view'],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${supplierId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: supplierId, name: 'Northwind Industrial Systems', classifications: ['vendor', 'manufacturer'], capabilities: ['overview', 'products'],
    organization: { id: supplierId, name: 'Northwind Industrial Systems', legal_name: '', website: '', classifications: ['vendor', 'manufacturer'], created_at: '2026-09-05T12:00:00Z', updated_at: '2026-09-17T12:00:00Z' },
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${supplierId}/catalog/specification-definitions`, (route) => route.fulfill({ json: {
    results: [{ id: 'template-1', name: 'Managed switch', product_kind: 'hardware', versions: [{ id: 'template-version-1', version: 2, schema: { type: 'object', additionalProperties: false, properties: { ports: { type: 'integer', title: 'Port count' }, uplink_type: { type: 'string', title: 'Uplink type' } }, required: ['ports'] }, checksum: 'a'.repeat(64), created_by: 'Primary Owner', created_at: '2026-09-17T12:00:00Z' }] }],
    can_manage: true,
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${supplierId}/catalog/products**`, (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith(`/${productId}`)) {
      if (request.method() === 'PATCH') {
        currentProduct = { ...currentProduct, ...request.postDataJSON() as Partial<typeof product> }
        return route.fulfill({ json: currentProduct })
      }
      return route.fulfill({ json: currentProduct })
    }
    const query = new URL(request.url()).searchParams
    expect(query.get('ordering')).toBe('name')
    expect(query.get('page')).toBe(listed ? '1' : '2')
    expect(query.get('page_size')).toBe('25')
    return route.fulfill({ json: { results: listed ? [currentProduct] : [], page: listed ? 1 : 2, page_size: 25, count: listed ? 1 : 0, has_more: false, can_manage: true } })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`product collection and complete record fit at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 760 })
    await mockProductWorkspace(page, baseURL)
    await page.goto(`/workspaces/organizations/${supplierId}/products`)

    await expect(page.getByRole('heading', { name: 'Product directory' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.locator('tbody .collection-name').click()
    const drawer = page.getByRole('dialog', { name: product.name })
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole('heading', { level: 2 })).toBeFocused()
    await expect(drawer.getByText('ES-48-LONG-CAMPUS-SKU · Active · version 3')).toBeVisible()
    await expect(drawer.getByText('Installation and service guide')).toBeVisible()
    expect(await drawer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)

    if (width === 1024) {
      await drawer.getByRole('button', { name: 'Edit product' }).click()
      await drawer.getByLabel('Product name').fill('EdgeSwitch Campus Core')
      await drawer.getByRole('button', { name: 'Save product' }).click()
      await expect(page.getByRole('dialog', { name: 'EdgeSwitch Campus Core' })).toBeVisible()
    }
    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}

test('a direct product URL retrieves a record outside the current page', async ({ page, baseURL }) => {
  await mockProductWorkspace(page, baseURL, false)
  await page.goto(`/workspaces/organizations/${supplierId}/products?product_page=2&product=${productId}`)
  const drawer = page.getByRole('dialog', { name: product.name })
  await expect(drawer.getByText('ES-48-LONG-CAMPUS-SKU · Active · version 3')).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`product_page=2.*product=${productId}`))
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await expect(page).toHaveURL(new RegExp('product_page=2$'))
})
