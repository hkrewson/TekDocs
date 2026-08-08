import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

test('pending two-factor sign-in accepts a recovery code', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ status: 401, json: { meta: { is_authenticated: false } } }))
  await page.route('**/_allauth/browser/v1/auth/login', (route) => route.fulfill({
    status: 401,
    json: { data: { flows: [{ id: 'mfa_authenticate', is_pending: true, types: ['totp', 'recovery_codes'] }] } },
  }))
  await page.route('**/_allauth/browser/v1/auth/2fa/authenticate', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ code: 'recovery-one' })
    await route.fulfill({ json: { data: { user: context.user } } })
  })
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))

  await page.goto('/')
  await page.getByLabel('Email address').fill('owner@example.com')
  await page.getByLabel('Password').fill('not-retained-password')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Two-factor authentication' })).toBeVisible()
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  await page.getByLabel('Authentication code').fill('recovery-one')
  await page.getByRole('button', { name: 'Verify code' }).click()

  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

test('security settings enrolls an authenticator and acknowledges one-time recovery codes', async ({ page, baseURL }) => {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const secret = Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) => alphabet[value % alphabet.length]).join('')
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/_allauth/browser/v1/auth/sessions', (route) => route.fulfill({ json: { data: [] } }))
  await page.route('**/_allauth/browser/v1/account/authenticators', (route) => route.fulfill({ json: { data: [] } }))
  await page.route('**/_allauth/browser/v1/account/authenticators/totp', async (route) => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({ code: '123456' })
      await route.fulfill({ json: { data: { type: 'totp' } } })
      return
    }
    await route.fulfill({ status: 404, json: { meta: { secret, totp_url: `otpauth://totp/TekDocs?secret=${secret}` } } })
  })
  await page.route('**/_allauth/browser/v1/account/authenticators/recovery-codes', (route) => route.fulfill({
    json: { data: { total_code_count: 2, unused_code_count: 2, unused_codes: ['alpha-bravo', 'charlie-delta'] } },
  }))

  await page.goto('/overview')
  await page.getByRole('button', { name: /Account menu for Primary Owner/ }).click()
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'Set up authenticator' }).click()
  await expect(page.locator('.mfa-qr-code svg')).toBeVisible()
  await expect(page.getByText('Scan with your authenticator app')).toBeVisible()
  await expect(page.getByText(secret, { exact: true })).toBeVisible()
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  await page.getByLabel('Authentication code').fill('123456')
  await page.getByRole('button', { name: 'Enable two-factor authentication' }).click()
  await expect(page.getByText('alpha-bravo')).toBeVisible()
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  await page.getByRole('button', { name: 'I saved these codes' }).click()

  await expect(page.getByText('alpha-bravo')).not.toBeVisible()
  await expect(page.getByText('2 of 2 codes remain. Each code works once.')).toBeVisible()
})
