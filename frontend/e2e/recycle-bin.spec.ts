import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('MSP recycle bin confirms and restores an archived cascade', async ({ page, baseURL }) => {
  const tenantId = crypto.randomUUID()
  const siteId = crypto.randomUUID()
  let restored = false
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
    tenant: { id: tenantId, name: 'Example MSP' },
  } }))
  await page.route('**/api/v1/recycle-bin?*', (route) => route.fulfill({ json: {
    results: restored ? [] : [{
      id: siteId,
      record_type: 'site',
      label: 'Downtown office',
      archived_at: '2026-08-08T18:00:00Z',
      workspace_kind: 'msp',
      workspace_id: tenantId,
      workspace_name: 'Example MSP',
      cascade_count: 3,
      can_restore: true,
    }],
    page: 1,
    page_size: 50,
    count: restored ? 0 : 1,
    has_more: false,
  } }))
  await page.route(`**/api/v1/recycle-bin/site/${siteId}/restore`, (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().headers()['x-csrftoken']).toBeTruthy()
    restored = true
    return route.fulfill({ status: 204 })
  })

  await page.goto('/recycle-bin')
  await expect(page.getByRole('heading', { name: 'Recycle bin' })).toBeVisible()
  await expect(page.getByText('Downtown office')).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('button', { name: 'Restore' }).click()
  await expect(page.getByText('This also restores 2 records archived in the same cascade.')).toBeVisible()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Restore' }).click()
  await expect(page.getByRole('status')).toHaveText('Downtown office restored.')
  await expect(page.getByText('This workspace has no recoverable archived records.')).toBeVisible()
})
