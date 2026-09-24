import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const checkedAt = '2026-09-23T18:00:00Z'

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner',
    permissions: ['system_diagnostics.view'], surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/api/v1/system/diagnostics', (route) => route.fulfill({ json: {
    status: 'degraded', checked_at: checkedAt, application_version: '0.8.46', database: 'ready',
    diagram_renderer: {
      status: 'stale', version: '@mermaid-js/mermaid-cli@11.16.0-with-a-deliberately-long-build-identifier-that-must-wrap',
      capacity: 8, queue: { waiting: 4, processing: 2, total: 6 },
      recent_failures: [{ code: 'renderer_timeout_with_a_deliberately_long_operational_identifier_that_must_wrap', occurred_at: Date.parse(checkedAt) }],
      last_checked_at: Date.parse(checkedAt),
    },
  } }))
}

async function expectContained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`help and system status fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 560 : 700 })
    await fixtures(page)
    await page.goto('/system-status')

    await expect(page.getByRole('heading', { name: 'System status' })).toBeVisible()
    await expect(page.getByRole('alert')).toContainText('services need attention')
    await expect(page.getByText('Check overdue')).toBeVisible()
    await expect(page.getByText(/renderer_timeout_with_a_deliberately_long/)).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    await expectContained(page)

    await page.getByRole('button', { name: 'Help for System status' }).click()
    const help = page.getByRole('dialog', { name: 'System status help' })
    await expect(help).toBeVisible()
    await expect(help.getByRole('heading', { name: 'System status', exact: true })).toBeFocused()
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    if (width < 768) {
      const bounds = await help.boundingBox()
      expect(bounds?.x).toBe(0)
      expect(bounds?.y).toBe(0)
      expect(bounds?.width).toBe(width)
      await page.getByRole('button', { name: 'Close help' }).click()
    } else {
      await page.keyboard.press('Escape')
    }
    await expect(help).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Help for System status' })).toBeFocused()
    await expectContained(page)

    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}
