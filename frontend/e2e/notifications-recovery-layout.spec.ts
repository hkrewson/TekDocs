import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const organizationId = '00000000-0000-4000-8000-000000000073'
const archivedAt = '2026-09-23T12:00:00Z'
const archived = Array.from({ length: 31 }, (_, index) => ({
  id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  record_type: index % 2 ? 'location' : 'site',
  label: `Archived regional technology location ${String(index + 1).padStart(2, '0')}`,
  archived_at: archivedAt,
  workspace_kind: 'msp',
  workspace_id: 'installation',
  workspace_name: 'Synthetic MSP',
  cascade_count: index + 1,
  can_restore: true,
}))

async function fixtures(page: Page) {
  await page.context().addCookies([{ name: 'csrftoken', value: 'layout-csrf-token', url: 'http://localhost:3200' }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner',
    permissions: ['notifications.manage'], surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/api/v1/notifications', (route) => route.fulfill({ json: {
    results: [{
      id: 'notification-1', topic: 'document_publication.available',
      title: 'Regional recovery documentation published',
      message: 'A deliberately long notification message remains readable without creating a second horizontal scrolling surface.',
      read: false, created_at: archivedAt, target: null,
    }],
    unread_count: 1, has_more: false, next_cursor: null,
  } }))
  await page.route('**/api/v1/notification-deliveries*', (route) => route.fulfill({ json: {
    results: [{
      id: 'delivery-1', state: 'dead_letter', surface: 'client_portal', attempts: 3, retry_generation: 0,
      event_topic: 'document_publication.available.with.a.deliberately.long.operational.identifier',
      organization: 'Northwest Clinical Technology Group and Regional Recovery Services',
      recipient: 'A deliberately long recipient display label for responsive validation',
      created_at: archivedAt, available_at: archivedAt, last_attempt_at: archivedAt,
      delivered_at: null, last_error_code: 'recipient_rejected',
    }],
    has_more: false, next_cursor: null,
  } }))
  const recycleResponse = async (route: Route, organization = false) => {
    const parameters = new URL(route.request().url()).searchParams
    const pageNumber = Number(parameters.get('page') ?? 1)
    const pageSize = Number(parameters.get('page_size') ?? 25)
    const type = parameters.get('record_type')
    const query = parameters.get('q')?.toLowerCase() ?? ''
    const source = archived.map((item) => organization ? { ...item, workspace_kind: 'organization', workspace_id: organizationId, workspace_name: 'Northwest Clinical Technology Group' } : item)
      .filter((item) => !type || item.record_type === type)
      .filter((item) => !query || item.label.toLowerCase().includes(query))
    const start = (pageNumber - 1) * pageSize
    return route.fulfill({ json: {
      results: source.slice(start, start + pageSize), page: pageNumber, page_size: pageSize,
      count: source.length, has_more: start + pageSize < source.length,
    } })
  }
  await page.route('**/api/v1/recycle-bin?*', (route) => recycleResponse(route))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/recycle-bin?*`, (route) => recycleResponse(route, true))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Northwest Clinical Technology Group',
    classifications: ['client'], capabilities: ['overview', 'recycle_bin'],
    organization: {
      id: organizationId, name: 'Northwest Clinical Technology Group', legal_name: '', website: '',
      classifications: ['client'], access_mode: 'assigned_only', created_at: archivedAt, updated_at: archivedAt,
      billing_contact_name: '', billing_email: '', billing_phone: '', billing_address_line_1: '',
      billing_address_line_2: '', billing_city: '', billing_region: '', billing_postal_code: '', billing_country_code: '',
    },
  } }))
}

async function expectContained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`notifications and recovery workspaces fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 600 : 700 })
    await fixtures(page)

    await page.goto('/recycle-bin')
    await expect(page.getByRole('heading', { name: 'Recycle bin' })).toBeVisible()
    await expect(page.getByText('31 archived records')).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page.getByText('Archived regional technology location 26')).toBeVisible()
    await page.getByLabel('Rows per page').selectOption('50')
    await expect(page).toHaveURL(/page_size=50/)
    await expect(page).not.toHaveURL(/page=2/)
    await expectContained(page)

    await page.goto(`/workspaces/organizations/${organizationId}/recycle_bin?q=location%2031`)
    await expect(page.getByText('Archived regional technology location 31')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Search: location 31 ×' })).toBeVisible()
    await expectContained(page)

    await page.goto('/notification-delivery?status=dead_letter')
    await expect(page.getByRole('heading', { name: 'Email delivery' })).toBeVisible()
    await expect(page.getByText('A deliberately long recipient display label for responsive validation')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Status: Failed ×' })).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    await expectContained(page)

    await page.getByRole('button', { name: 'Notifications' }).click()
    await expect(page.getByRole('dialog', { name: 'Notifications' })).toBeVisible()
    await expect(page.getByText('A deliberately long notification message remains readable without creating a second horizontal scrolling surface.')).toBeVisible()
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    if (width < 768) {
      const bounds = await page.getByRole('dialog', { name: 'Notifications' }).boundingBox()
      expect(bounds?.x).toBe(0)
      expect(bounds?.y).toBe(0)
      expect(bounds?.width).toBe(width)
    }
    await expectContained(page)
    if (width < 768) await page.getByRole('button', { name: 'Close notifications' }).click()
    else await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: 'Notifications' })).toHaveCount(0)

    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}
