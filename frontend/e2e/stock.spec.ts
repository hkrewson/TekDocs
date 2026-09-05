import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const itemId = crypto.randomUUID()
const clientId = crypto.randomUUID()

const stockItem = {
  id: itemId,
  name: 'Cat6 bulk cable',
  description: 'Riser-rated solid copper cable',
  vendor_id: crypto.randomUUID(),
  vendor_name: 'Cable Supplier',
  vendor_part_number: 'PART-1000',
  unit: 'foot',
  quantity_on_hand: '1000.000',
  reorder_level: '150.000',
  currency: 'USD',
  cost_per_unit: '0.145430',
  client_price_per_unit: '0.30',
  purchase_quantity: '1000.000',
  purchase_price: '107.99',
  order_total: '145.43',
  order_number: 'ORDER-1001',
  order_url: 'https://orders.example.invalid/ORDER-1001',
  ordered_on: '2026-08-01',
  tracking_number: 'TRACK-1001',
  tracking_url: 'https://tracking.example.invalid/TRACK-1001',
  movements: [],
  created_at: '2026-08-01T12:00:00Z',
  updated_at: '2026-08-01T12:00:00Z',
}

test('MSP stock records purchasing details, client use, and exact invoice pricing', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner',
    permissions: ['invoices.view', 'invoices.edit'],
  } }))
  await page.route('**/api/v1/workspaces/msp/stock', async (route) => {
    if (route.request().method() === 'POST') {
      const body = await route.request().postDataJSON() as Record<string, string>
      expect(body).toMatchObject({ name: 'Patch cable', cost_per_unit: '2.125000', client_price_per_unit: '4.2500' })
      await route.fulfill({ status: 201, json: { ...stockItem, id: crypto.randomUUID(), name: 'Patch cable', cost_per_unit: '2.125000', client_price_per_unit: '4.25' } })
      return
    }
    await route.fulfill({ json: {
      results: [stockItem],
      can_manage: true,
      vendors: [{ id: stockItem.vendor_id, name: stockItem.vendor_name }],
      clients: [{ id: clientId, name: 'Example Client' }],
    } })
  })
  await page.route(`**/api/v1/workspaces/msp/stock/${itemId}/movements`, async (route) => {
    expect(await route.request().postDataJSON()).toMatchObject({
      movement_type: 'used', quantity_change: '-125.500', client_id: clientId,
    })
    await route.fulfill({ status: 201, json: {
      ...stockItem,
      quantity_on_hand: '874.500',
      movements: [{
        id: crypto.randomUUID(), movement_type: 'used', quantity_change: '-125.500', quantity_after: '874.500',
        client_id: clientId, client_name: 'Example Client', note: 'Conference room runs',
        occurred_at: '2026-09-05T12:00:00Z', recorded_at: '2026-09-05T12:00:00Z', actor: 'Primary Owner',
      }],
    } })
  })

  await page.goto('/stock')
  await expect(page.getByRole('heading', { name: 'Stock', exact: true })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Stock items' })).toContainText('0.145430')
  await expect(page.getByText('ORDER-1001')).toHaveAttribute('href', /ORDER-1001$/)

  await page.getByRole('button', { name: 'Adjust stock' }).click()
  await page.getByLabel('Action').selectOption('used')
  await page.getByLabel('Quantity (foot)').fill('125.500')
  await page.getByRole('dialog').locator('select').nth(1).selectOption(clientId)
  await page.getByLabel('Note').fill('Conference room runs')
  await expect(page.getByRole('status')).toContainText('874.500 foot')
  await page.getByRole('button', { name: 'Save change' }).click()
  await expect(page.getByRole('group', { name: 'Stock history' })).toContainText('Example Client')

  await page.getByRole('button', { name: 'New item' }).click()
  await page.getByLabel('Item name').fill('Patch cable')
  await page.getByLabel('Unit', { exact: true }).fill('each')
  await page.getByLabel('Cost per unit').fill('2.125000')
  await page.getByLabel('Client price per unit').fill('4.2500')
  await page.getByRole('button', { name: 'Save item' }).click()
  await expect(page.getByRole('heading', { name: 'Patch cable' })).toBeVisible()
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})
