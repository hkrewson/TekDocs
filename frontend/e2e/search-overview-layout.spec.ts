import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const clientId = '00000000-0000-4000-8000-000000000042'
const updatedAt = '2026-09-23T12:00:00Z'
const searchResults = Array.from({ length: 31 }, (_, index) => ({
  id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  result_type: 'document', entity_type: 'document',
  title: `Recovery runbook ${String(index + 1).padStart(2, '0')}`,
  excerpt: 'A long operational recovery procedure that remains readable on narrow screens.',
  workspace_label: 'Synthetic MSP', target: `/documentation?document=document-${index + 1}`,
  score: 1_000 - index, updated_at: updatedAt, review_state: index ? 'unreviewed' : 'approved',
}))

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: [],
    surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/api/v1/search?*', (route) => {
    const parameters = new URL(route.request().url()).searchParams
    const pageNumber = Number(parameters.get('page') ?? 1)
    const pageSize = Number(parameters.get('page_size') ?? 25)
    const start = (pageNumber - 1) * pageSize
    return route.fulfill({ json: {
      results: searchResults.slice(start, start + pageSize),
      facets: [{ value: 'document', label: 'Documents', count: searchResults.length }],
      page: pageNumber, page_size: pageSize, count: searchResults.length,
      has_more: start + pageSize < searchResults.length, truncated: false,
    } })
  })
  await page.route(`**/api/v1/workspaces/organizations/${clientId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: clientId, name: 'Northwest Clinical Technology Group',
    classifications: ['client'], capabilities: ['overview', 'integrations'],
    organization: {
      id: clientId, name: 'Northwest Clinical Technology Group',
      legal_name: 'Northwest Clinical Technology Group and Regional Recovery Services, LLC',
      website: 'https://northwest-clinical-technology.example.invalid', classifications: ['client'],
      access_mode: 'assigned_only', created_at: updatedAt, updated_at: updatedAt,
      billing_contact_name: '', billing_email: '', billing_phone: '', billing_address_line_1: '',
      billing_address_line_2: '', billing_city: '', billing_region: '', billing_postal_code: '', billing_country_code: '',
    },
  } }))
  await page.route('**/api/v1/entity-link-types', (route) => route.fulfill({ json: [] }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/links`, (route) => route.fulfill({ json: { relationships: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${clientId}/integrations/halo/tickets`, (route) => route.fulfill({ json: [{
    id: '00000000-0000-4000-8000-000000000099', number: '1042',
    title: 'Regional printer queue unavailable after overnight network maintenance',
    status: 'In progress', priority: 'High', assigned_team: 'Service desk', assigned_agent: 'Taylor Morgan',
    respond_by: null, fix_by: null, opened_at: null, closed_at: null,
    source_updated_at: updatedAt, source_last_synced_at: updatedAt, stale: false,
    external_url: 'https://support.example.invalid/tickets/1042',
  }] }))
}

async function expectContained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`search and focused overviews fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 600 : 700 })
    await fixtures(page)

    await page.goto('/overview')
    await expect(page.getByRole('heading', { name: 'Start here' })).toBeVisible()
    await expect(page.getByRole('link', { name: /Client organizations/ })).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    await expectContained(page)

    await page.goto('/search?q=runbook')
    await expect(page.getByText('31 records found.')).toBeVisible()
    await expect(page.getByRole('link', { name: /Recovery runbook 01/ })).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page.getByRole('link', { name: /Recovery runbook 26/ })).toBeVisible()
    await page.getByLabel('Rows per page').selectOption('50')
    await expect(page).toHaveURL(/page_size=50/)
    await expect(page).not.toHaveURL(/page=2/)
    await expectContained(page)

    await page.goto(`/workspaces/organizations/${clientId}/overview`)
    await expect(page.getByRole('heading', { name: 'Northwest Clinical Technology Group' })).toBeVisible()
    await expect(page.getByText(/#1042 Regional printer queue unavailable/)).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    await expectContained(page)

    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}
