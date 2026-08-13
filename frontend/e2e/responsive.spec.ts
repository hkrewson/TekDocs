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
