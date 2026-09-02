import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const wcag22Tags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

test.beforeEach(async ({ page, baseURL }) => {
  const tenantId = crypto.randomUUID()
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
    tenant: { id: tenantId, name: 'Example MSP' },
    permissions: [],
  } }))
})

test('taxonomy hierarchy can be revised, reordered, and used without accessibility violations', async ({ page }) => {
  const taxonomyId = crypto.randomUUID()
  const versionId = crypto.randomUUID()
  const terms = [
    { id: crypto.randomUUID(), stable_key: 'microsoft', label: 'Microsoft', description: 'Microsoft products and services.', parent_key: '', aliases: ['MSFT'], status: 'active', replacement_key: '', sort_order: 0, impact: { documents: 2, templates: 1 } },
    { id: crypto.randomUUID(), stable_key: 'entra-id', label: 'Entra ID', description: 'Microsoft identity services.', parent_key: 'microsoft', aliases: ['Azure AD'], status: 'active', replacement_key: '', sort_order: 1, impact: { documents: 1, templates: 0 } },
  ]
  const taxonomy = {
    id: taxonomyId,
    key: 'technology',
    binding: 'document_tags',
    archived: false,
    current_version: { id: versionId, version: 1, label: 'Technology', description: 'Approved platforms.', allow_local_terms: false, created_at: '2026-09-01T12:00:00Z', terms },
    versions: [{ id: versionId, version: 1, label: 'Technology', created_at: '2026-09-01T12:00:00Z' }],
    impact: { documents: 3, templates: 1 },
  }
  const revisions: Record<string, unknown>[] = []
  await page.route(/\/api\/v1\/taxonomies(\?|$)/, (route) => route.fulfill({ json: { results: [taxonomy], count: 1 } }))
  await page.route(`**/api/v1/taxonomies/${taxonomyId}`, (route) => {
    if (route.request().method() !== 'PATCH') return route.fallback()
    revisions.push(route.request().postDataJSON() as Record<string, unknown>)
    return route.fulfill({ json: { ...taxonomy, current_version: { ...taxonomy.current_version, version: 2 } } })
  })

  await page.goto('/taxonomies')
  await expect(page.getByRole('heading', { name: 'Taxonomies' })).toBeVisible()
  await expect(page.getByText('3 documents · 1 template')).toBeVisible()
  await page.getByRole('button', { name: 'New version' }).click()
  await expect(page.getByText('Affects 2 documents · 1 template')).toBeVisible()
  await expect(page.getByLabel('Parent').nth(1)).toHaveValue('microsoft')
  await page.getByRole('button', { name: 'Move up' }).nth(1).click()
  await page.getByRole('button', { name: 'Save taxonomy' }).click()

  await expect.poll(() => revisions.length).toBe(1)
  const submittedTerms = (revisions[0] as { terms: Array<{ stable_key: string; sort_order: number }> }).terms
  expect(submittedTerms.map((term) => [term.stable_key, term.sort_order])).toEqual([['entra-id', 0], ['microsoft', 1]])
  await expect(new AxeBuilder({ page }).include('main').withTags(wcag22Tags).analyze())
    .resolves.toMatchObject({ violations: [] })
})
