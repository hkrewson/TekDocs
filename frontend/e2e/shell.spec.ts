import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}

async function mockAuthenticated(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 200,
    json: { status: 200, meta: { is_authenticated: true }, data: { user: context.user } },
  }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
}

test('authenticated application shell exposes primary navigation and backend health', async ({ page, request }) => {
  const health = await request.get('/api/v1/health/ready')
  expect(health.ok()).toBeTruthy()
  await mockAuthenticated(page)

  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expect(page.getByText('Example MSP', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Documentation' }).click()
  await expect(page.getByRole('heading', { name: 'Documentation' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Editor' })).toBeVisible()
})

test('raw Markdown remains the editable canonical representation', async ({ page }) => {
  await mockAuthenticated(page)
  await page.goto('/documentation')
  await page.getByRole('tab', { name: 'Markdown' }).click()
  const source = page.getByLabel('Markdown source')
  await expect(source).toHaveValue(/# Firewall replacement/)
  await source.fill('# Updated procedure\n\nUse **approved** access.')
  await page.getByRole('tab', { name: 'Editor' }).click()
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await expect(source).toHaveValue('# Updated procedure\n\nUse **approved** access.')
})

test('mobile authenticated navigation is operable', async ({ page }) => {
  await mockAuthenticated(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/overview')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('link', { name: 'Documentation' })).toBeVisible()
  await page.getByRole('button', { name: 'Close navigation' }).first().click()
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
})

test('first-owner browser setup enters the authenticated shell', async ({ page, baseURL }) => {
  const csrf = crypto.randomUUID().replaceAll('-', '')
  await page.context().addCookies([{ name: 'csrftoken', value: csrf, url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: true } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 401,
    json: { status: 401, meta: { is_authenticated: false }, data: { flows: [{ id: 'login' }] } },
  }))
  await page.route('**/api/v1/bootstrap/owner', (route) => route.fulfill({ status: 201, json: { tenant: {}, owner: {} } }))
  await page.route('**/_allauth/browser/v1/auth/login', (route) => route.fulfill({
    status: 200,
    json: { status: 200, meta: { is_authenticated: true }, data: { user: context.user } },
  }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))

  await page.goto('/')
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  const password = `${crypto.randomUUID()}Aa7!`
  await page.getByLabel('Deployment token').fill(crypto.randomUUID())
  await page.getByLabel('MSP name').fill('Example MSP')
  await page.getByLabel('Your name').fill('Primary Owner')
  await page.getByLabel('Email address').fill('owner@example.com')
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await page.getByRole('button', { name: 'Create workspace' }).click()

  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

test('sign-in boundary has no detectable accessibility violations', async ({ page }) => {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 401,
    json: { status: 401, meta: { is_authenticated: false }, data: { flows: [{ id: 'login' }] } },
  }))

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})

test('sign out removes the shell and returns to sign in', async ({ page, baseURL }) => {
  await mockAuthenticated(page)
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/_allauth/browser/v1/auth/session', (route) => {
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 401, json: { status: 401, meta: { is_authenticated: false } } })
    }
    return route.fallback()
  })

  await page.goto('/overview')
  await page.getByRole('button', { name: /Account menu for Primary Owner/ }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Overview' })).not.toBeVisible()
})
