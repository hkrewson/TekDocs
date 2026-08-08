import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

test('profile settings update the visible shell identity', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/_allauth/browser/v1/auth/sessions', (route) => route.fulfill({ json: { data: [] } }))
  await page.route('**/_allauth/browser/v1/account/authenticators', (route) => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/v1/auth/profile', async (route) => {
    expect(route.request().method()).toBe('PATCH')
    expect(route.request().postDataJSON()).toEqual({ display_name: 'Operations Lead' })
    await route.fulfill({ json: { ...context, user: { ...context.user, display_name: 'Operations Lead' } } })
  })

  await page.goto('/settings')
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  await page.getByLabel('Display name').fill('Operations Lead')
  await page.getByRole('button', { name: 'Save profile' }).click()

  await expect(page.getByRole('status')).toHaveText('Profile updated.')
  await expect(page.getByRole('button', { name: /Account menu for Operations Lead/ })).toBeVisible()
  await expect(page.getByLabel('Email address')).toHaveValue('owner@example.com')
  await expect(page.getByLabel('Email address')).toHaveAttribute('readonly', '')
})

test('sign in exposes only the safe configured OIDC provider identity', async ({ page }) => {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ status: 401, json: { meta: { is_authenticated: false } } }))
  await page.route('**/api/v1/auth/providers', (route) => route.fulfill({
    json: { providers: [{ id: 'company-sso', name: 'Company SSO' }] },
  }))

  await page.goto('/')
  const button = page.getByRole('button', { name: 'Continue with Company SSO' })
  await expect(button).toBeVisible()
  const form = button.locator('xpath=..')
  await expect(form).toHaveAttribute('action', '/_allauth/browser/v1/auth/provider/redirect')
  await expect(form.locator('input[name="provider"]')).toHaveValue('company-sso')
  await expect(page.locator('body')).not.toContainText('client-secret')
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
})
