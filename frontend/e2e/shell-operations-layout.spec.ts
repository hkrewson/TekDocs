import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const longSource = 'Northwest Regional Clinical Technology Recovery and Continuity Runbook'
const recordedAt = '2026-09-23T12:00:00Z'
const reminders = Array.from({ length: 61 }, (_, index) => ({
  id: `reminder-${index + 1}`, source_entity_id: 'document-1', source: longSource,
  domain: index % 2 ? 'documentation' : 'inventory', kind: 'review',
  title: `Quarterly recovery readiness review ${String(index + 1).padStart(2, '0')}`,
  due_on: `2026-${String(1 + Math.floor(index / 28)).padStart(2, '0')}-${String(1 + index % 28).padStart(2, '0')}`,
  lead_days: 14, recurrence: index % 3 ? 'none' : 'annual', owner_id: null,
  owner: index % 2 ? 'Alexandria Morgan-Santiago Kensington' : null, active: true, created_at: recordedAt,
}))
const activity = Array.from({ length: 61 }, (_, index) => ({
  id: `event-${index + 1}`, action: index % 2 ? 'document.review_requested' : 'network_circuit.handoff_updated',
  actor_id: 'owner', actor_name: 'Alexandria Morgan-Santiago Kensington', entity_id: `entity-${index + 1}`,
  entity_name: `${longSource} ${index + 1}`, entity_type: index % 2 ? 'document' : 'network_circuit',
  request_id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`, occurred_at: recordedAt,
}))

async function fixtures(page: Page) {
  await page.context().addCookies([{ name: 'csrftoken', value: 'layout-test', domain: 'localhost', path: '/' }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner',
    permissions: ['deadlines.view', 'deadlines.edit', 'activity.view'], surface: 'msp', organization: null,
    mfa_enrollment_required: false,
  } }))
  await page.route('**/api/v1/workspaces/msp/reminders?*', (route) => {
    const parameters = new URL(route.request().url()).searchParams
    const pageNumber = Number(parameters.get('page') ?? 1), pageSize = Number(parameters.get('page_size') ?? 25)
    const query = (parameters.get('q') ?? '').toLowerCase(), domain = parameters.get('domain')
    let found = reminders.filter((record) => `${record.title} ${record.source}`.toLowerCase().includes(query))
    if (domain) found = found.filter((record) => record.domain === domain)
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * pageSize, pageNumber * pageSize), count: found.length, page: pageNumber, page_size: pageSize, has_more: pageNumber * pageSize < found.length } })
  })
  await page.route('**/api/v1/workspaces/msp/reminders', (route) => route.fulfill({ status: 201, json: reminders[0] }))
  await page.route('**/api/v1/activity?*', (route) => {
    const parameters = new URL(route.request().url()).searchParams
    const pageNumber = Number(parameters.get('page') ?? 1), pageSize = Number(parameters.get('page_size') ?? 25)
    const query = (parameters.get('q') ?? '').toLowerCase()
    const found = activity.filter((record) => record.action.toLowerCase().includes(query))
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * pageSize, pageNumber * pageSize), count: found.length, page: pageNumber, page_size: pageSize, has_more: pageNumber * pageSize < found.length, actions: [...new Set(found.map((record) => record.action))] } })
  })
  await page.route('**/api/v1/entities/search?*', (route) => route.fulfill({ json: { results: [{ id: 'document-1', display_name: longSource, entity_type: 'document', visibility: 'msp_private', workspace_label: 'MSP', eligible_link_types: [] }], page: 1, page_size: 15, count: 1, has_more: false } }))
}

async function expectContained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`reminder agenda and activity stream fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 600 : 700 })
    await fixtures(page)

    await page.goto('/deadlines')
    await expect(page.getByText('61 active reminders')).toBeVisible()
    await expect(page.getByText(longSource).first()).toBeVisible()
    await expectContained(page)
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page.getByText('Quarterly recovery readiness review 26')).toBeVisible()

    await page.goto('/activity')
    await expect(page.getByText('61 recorded changes')).toBeVisible()
    await expect(page.getByText(/Northwest Regional Clinical Technology/).first()).toBeVisible()
    await expectContained(page)
    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}

test('reminder creation retains dirty work and restores its URL state', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 600 })
  await fixtures(page)
  await page.goto('/deadlines')
  await page.getByRole('button', { name: 'New reminder' }).click()
  await expect(page).toHaveURL(/new=1/)
  await page.getByLabel('Title').fill('Review the revised recovery procedure')
  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('heading', { name: 'Unsaved changes' })).toBeVisible()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page.getByLabel('Title')).toHaveValue('Review the revised recovery procedure')
  await page.getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(page).not.toHaveURL(/new=1/)
  await expect(page.getByLabel('Title')).toHaveCount(0)
})

test('successful reminder creation closes its focused form', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 600 })
  await fixtures(page)
  await page.goto('/deadlines')
  await page.getByRole('button', { name: 'New reminder' }).click()
  await page.getByLabel('Related record').fill('Recovery')
  await page.getByRole('button', { name: new RegExp(longSource) }).click()
  await page.getByLabel('Title').fill('Review the revised recovery procedure')
  await page.getByLabel('Due date').fill('2027-12-31')
  await page.getByRole('button', { name: 'Create reminder' }).click()
  await expect(page).not.toHaveURL(/new=1/)
  await expect(page.getByLabel('Title')).toHaveCount(0)
})
