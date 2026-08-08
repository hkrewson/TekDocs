import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

test('account settings lists and revokes another active browser', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    json: { status: 200, meta: { is_authenticated: true }, data: { user: context.user } },
  }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/_allauth/browser/v1/account/authenticators', (route) => route.fulfill({ json: { data: [] } }))
  await page.route('**/_allauth/browser/v1/auth/sessions', async (route) => {
    if (route.request().method() === 'DELETE') {
      expect(route.request().postDataJSON()).toEqual({ sessions: [2] })
      await route.fulfill({ json: { data: [{ id: 1, user_agent: 'Chrome on Mac', ip: '192.0.2.10', created_at: 1_786_000_000, last_seen_at: 1_786_003_600, is_current: true }] } })
      return
    }
    await route.fulfill({ json: { data: [
      { id: 1, user_agent: 'Chrome/140.0 Macintosh', ip: '192.0.2.10', created_at: 1_786_000_000, last_seen_at: 1_786_003_600, is_current: true },
      { id: 2, user_agent: 'Firefox/141.0 Windows', ip: '198.51.100.20', created_at: 1_785_000_000, last_seen_at: 1_785_003_600, is_current: false },
    ] } })
  })

  await page.goto('/overview')
  await page.getByRole('button', { name: /Account menu for Primary Owner/ }).click()
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  await expect(page.getByRole('heading', { name: 'Active sessions' })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.getByRole('button', { name: 'Revoke' }).click()
  await expect(page.getByText('Firefox on Windows')).not.toBeVisible()
})
