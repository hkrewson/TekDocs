import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('password reset request uses one accessible confirmation state', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/_allauth/browser/v1/auth/password/request', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ email: 'someone@example.com' })
    await route.fulfill({ json: { status: 200, data: { email: 'someone@example.com' } } })
  })

  await page.goto('/auth/reset-password')
  await page.getByLabel('Email address').fill('someone@example.com')
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  await page.getByRole('button', { name: 'Send reset link' }).click()

  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  await expect(page.getByText(/same message is shown for every address/i)).toBeVisible()
})

test('password reset scrubs its key and returns to sign in after completion', async ({ page, baseURL }) => {
  const key = `${crypto.randomUUID()}-${crypto.randomUUID()}`
  const password = `${crypto.randomUUID()}Aa7!`
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/_allauth/browser/v1/auth/password/reset', async (route) => {
    const request = route.request()
    if (request.method() === 'GET') {
      expect(request.headers()['x-password-reset-key']).toBe(key)
      await route.fulfill({ json: { status: 200 } })
      return
    }
    expect(request.postDataJSON()).toEqual({ key, password })
    await route.fulfill({ status: 401, json: { status: 401, meta: { is_authenticated: false } } })
  })

  await page.goto(`/auth/reset-password#key=${encodeURIComponent(key)}`)
  await expect(page).toHaveURL('/auth/reset-password')
  await page.getByLabel('New password', { exact: true }).fill(password)
  await page.getByLabel('Confirm new password').fill(password)
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  await page.getByRole('button', { name: 'Change password' }).click()

  await expect(page.getByRole('heading', { name: 'Password changed' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Continue to sign in' })).toBeVisible()
})

test('invalid reset key has one accessible unavailable state', async ({ page }) => {
  const key = `${crypto.randomUUID()}-${crypto.randomUUID()}`
  await page.route('**/_allauth/browser/v1/auth/password/reset', (route) => route.fulfill({ status: 400, json: { status: 400 } }))

  await page.goto(`/auth/reset-password#key=${encodeURIComponent(key)}`)

  await expect(page.getByRole('heading', { name: 'Reset link unavailable' })).toBeVisible()
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
})
