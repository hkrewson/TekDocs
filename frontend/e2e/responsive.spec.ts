import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Responsive Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Responsive MSP' },
}

async function mockAuthenticated(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 200,
    json: { status: 200, meta: { is_authenticated: true }, data: { user: context.user } },
  }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  await page.route('**/api/v1/notifications*', (route) => route.fulfill({ json: { results: [], count: 0 } }))
}

async function mockSignedOut(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 401,
    json: { status: 401, meta: { is_authenticated: false }, data: { flows: [{ id: 'login' }] } },
  }))
}

async function mockClientPortal(page: Page) {
  const portalContext = {
    ...context,
    user: { ...context.user, display_name: 'A client reader with a deliberately long display name' },
    organization: { id: crypto.randomUUID(), name: 'A client organization with a deliberately long name' },
    role: 'client_user', permissions: [], surface: 'client_portal',
  }
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { status: 200, meta: { is_authenticated: true }, data: { user: portalContext.user } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: portalContext }))
  await page.route('**/api/v1/portal/invoices', (route) => route.fulfill({ json: { count: 1, has_more: false, next_cursor: null, results: [{ id: 'invoice-1', number: 'INV-2026-000001', currency: 'USD', total: '145.43', due_date: '2026-10-07', lifecycle_state: 'issued' }] } }))
  await page.route('**/api/v1/portal/documents**', (route) => route.fulfill({ json: { count: 1, has_more: false, next_cursor: null, results: [{ id: 'document-1', title: 'A deliberately long client-facing network access and recovery guide', category: 'Guide', published_at: '2026-09-07T12:00:00Z' }] } }))
  await page.route('**/api/v1/portal/notifications*', (route) => route.fulfill({ json: { results: [], count: 0 } }))
}

async function expectNoHorizontalPageOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
}

test('small-screen shell reflows and navigation remains keyboard and touch operable', async ({ page }) => {
  await mockAuthenticated(page)
  await page.goto('/overview')

  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expectNoHorizontalPageOverflow(page)
  await page.getByRole('button', { name: 'Open navigation' }).click()
  const navigation = page.getByRole('navigation', { name: 'Workspace' })
  await expect(navigation).toBeVisible()
  await expect(navigation.getByRole('link', { name: 'Documentation' })).toBeVisible()
  await page.getByRole('complementary').getByRole('button', { name: 'Close navigation' }).click()
  await expect(navigation).toBeHidden()
  await expectNoHorizontalPageOverflow(page)
  await expect(new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()).resolves.toMatchObject({ violations: [] })
})

test('navigation groups remain usable at the required review widths and text zoom', async ({ page }) => {
  await mockAuthenticated(page)
  await page.goto('/overview')

  for (const width of [320, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    if (width <= 800) await page.getByRole('button', { name: 'Open navigation' }).click()
    const workspace = page.getByRole('button', { name: 'Workspace', exact: true })
    await expect(workspace).toBeVisible()
    await expect(workspace).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByRole('link', { name: 'Overview' })).toBeVisible()
    if (width <= 800) await page.getByRole('complementary').getByRole('button', { name: 'Close navigation' }).click()
    await expectNoHorizontalPageOverflow(page)
  }

  await page.setViewportSize({ width: 1280, height: 900 })
  await page.evaluate(() => { document.body.style.zoom = '2' })
  await expect(page.getByRole('button', { name: 'Workspace', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Overview' })).toBeVisible()
})

test('authentication and client portal shells reflow at review widths and text zoom', async ({ page }) => {
  await mockSignedOut(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()

  for (const width of [320, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expectNoHorizontalPageOverflow(page)
  }

  await page.setViewportSize({ width: 1280, height: 900 })
  await page.evaluate(() => { document.body.style.zoom = '2' })
  await expect(page.getByLabel('Email address')).toBeVisible()
  await expectNoHorizontalPageOverflow(page)

  await page.unrouteAll({ behavior: 'wait' })
  await page.evaluate(() => { document.body.style.zoom = '1' })
  await mockClientPortal(page)
  await page.goto('/portal')
  await expect(page.getByRole('heading', { name: /A client organization/ })).toBeVisible()

  for (const width of [320, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expectNoHorizontalPageOverflow(page)
  }

  await page.setViewportSize({ width: 1280, height: 900 })
  await page.evaluate(() => { document.body.style.zoom = '2' })
  await expect(page.getByRole('button', { name: /INV-2026-000001/ })).toBeVisible()
  await expectNoHorizontalPageOverflow(page)
  const skipLink = page.getByRole('link', { name: 'Skip to main content' })
  await skipLink.focus()
  await expect(skipLink).toBeFocused()
  await expect(new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()).resolves.toMatchObject({ violations: [] })
})
