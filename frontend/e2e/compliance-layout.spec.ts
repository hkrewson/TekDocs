import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const revision = {
  revision_number: 1, version_label: '2026.1', description: 'Operational baseline', source_url: '',
  content_digest: 'a'.repeat(64), created_at: '2026-09-21T12:00:00Z', created_by: 'Compliance owner',
  entries: [{ position: 0, control: {
    control_id: 'control-1', revision_number: 1, identifier: 'AC-1', title: 'Asset inventory',
    description: 'Maintain an inventory.', guidance: '', content_digest: 'b'.repeat(64), created_at: '2026-09-21T12:00:00Z',
  } }],
}

const framework = { id: 'framework-1', name: 'Security Baseline', revision_count: 1, can_manage: true, current_revision: revision }

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner',
    permissions: ['compliance.view', 'compliance.edit', 'data_flows.view', 'data_flows.edit'],
    surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/compliance/frameworks?*', (route) => route.fulfill({ json: { results: [framework], page: 1, page_size: 50, count: 1, has_more: false, can_manage: true } }))
  await page.route('**/compliance/frameworks/framework-1/revisions', (route) => route.fulfill({ json: [revision] }))
  await page.route('**/compliance/frameworks/framework-1/assignments', (route) => route.fulfill({ json: { results: [], owner_choices: [] } }))
  await page.route('**/compliance/evidence?*', (route) => route.fulfill({ json: { results: [], page: 1, page_size: 100, count: 0, has_more: false } }))
  await page.route('**/compliance/risks?*', (route) => route.fulfill({ json: {
    results: [], page: 1, page_size: 100, count: 0, has_more: false, owner_choices: [],
    summary: { total: 0, overdue: 0, by_status: {}, by_band: {} },
  } }))
  await page.route('**/compliance/bundles', (route) => route.fulfill({ json: [] }))
  await page.route('**/compliance/data-flows/choices', (route) => route.fulfill({ json: {
    endpoint_kinds: [], directions: [], transfer_mechanisms: [], data_classifications: [], protections: [], provenance_states: [],
  } }))
  await page.route(/\/compliance\/data-flows(\?|$)/, (route) => route.fulfill({ json: { results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true } }))
}

async function chooseSection(page: Page, section: 'evidence' | 'risks', mobile: boolean) {
  if (mobile) await page.getByRole('combobox', { name: 'Sections' }).selectOption(section)
  else await page.getByRole('link', { name: section === 'evidence' ? 'Evidence' : 'Risks' }).click()
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`compliance sections remain focused and fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 })
    await fixtures(page)
    await page.goto('/compliance')
    await expect(page.getByRole('heading', { name: 'Security Baseline' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Evidence' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Risk register' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)

    await chooseSection(page, 'evidence', width < 768)
    await expect(page).toHaveURL(/section=evidence/)
    await expect(page.getByRole('heading', { name: 'Evidence' })).toBeVisible()
    await page.getByRole('button', { name: 'Add or link evidence' }).click()
    await page.getByLabel('Title').fill('Draft evidence')
    await chooseSection(page, 'risks', width < 768)
    await expect(page.getByRole('heading', { name: 'Unsaved changes' })).toBeVisible()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(page).toHaveURL(/section=evidence/)
    await expect(page.getByLabel('Title')).toHaveValue('Draft evidence')
    await chooseSection(page, 'risks', width < 768)
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page).toHaveURL(/section=risks/)
    await expect(page.getByRole('heading', { name: 'Risk register' })).toBeVisible()
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('compliance frameworks can retry a failed load', async ({ page }) => {
  await fixtures(page)
  let attempts = 0
  await page.route('**/compliance/frameworks?*', (route) => {
    attempts += 1
    return attempts === 1
      ? route.fulfill({ status: 503, json: {} })
      : route.fulfill({ json: { results: [framework], page: 1, page_size: 50, count: 1, has_more: false, can_manage: true } })
  })
  await page.goto('/compliance')
  await expect(page.getByRole('alert')).toContainText('Compliance frameworks are unavailable.')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { name: 'Security Baseline' })).toBeVisible()
})
