import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const organizationId = '00000000-0000-4000-8000-000000000073'
const createdAt = '2026-09-23T12:00:00Z'

const fields = Array.from({ length: 31 }, (_, index) => {
  const number = index + 1
  const id = `10000000-0000-4000-8000-${String(number).padStart(12, '0')}`
  return {
    id,
    key: `regional_metadata_${number}`,
    entity_type: number % 2 ? 'site' : 'location',
    owner: 'msp', organization_id: null, inherited: false, archived: false,
    current_version: {
      id: `11000000-0000-4000-8000-${String(number).padStart(12, '0')}`,
      version: 2, label: `Regional metadata field ${String(number).padStart(2, '0')}`,
      description: number === 31 ? 'A deliberately long field description with operational guidance and an_identifier_that_must_remain_readable_without_horizontal_page_overflow.' : 'Technician-maintained metadata.',
      required: number % 3 === 0, field_type: 'text', schema: {}, display_order: number, created_at: createdAt,
    },
    versions: [{ id: `11000000-0000-4000-8000-${String(number).padStart(12, '0')}`, version: 2, label: `Regional metadata field ${String(number).padStart(2, '0')}`, created_at: createdAt }],
  }
})

const taxonomies = Array.from({ length: 31 }, (_, index) => {
  const number = index + 1
  const id = `20000000-0000-4000-8000-${String(number).padStart(12, '0')}`
  return {
    id, key: `regional_taxonomy_${number}`, binding: number % 2 ? 'document_tags' : 'platform', archived: false,
    current_version: {
      id: `21000000-0000-4000-8000-${String(number).padStart(12, '0')}`,
      version: 1, label: `Regional taxonomy ${String(number).padStart(2, '0')}`,
      description: number === 31 ? 'A deliberately long controlled vocabulary description with an_identifier_that_must_wrap_on_narrow_viewports_without_clipping.' : 'Shared documentation terms.',
      allow_local_terms: false, created_at: createdAt,
      terms: [{ id: `22000000-0000-4000-8000-${String(number).padStart(12, '0')}`, stable_key: `term-${number}`, label: `Term ${number}`, description: '', parent_key: '', aliases: [], status: 'active', replacement_key: '', sort_order: 0 }],
    },
    versions: [{ id: `21000000-0000-4000-8000-${String(number).padStart(12, '0')}`, version: 1, label: `Regional taxonomy ${String(number).padStart(2, '0')}`, created_at: createdAt }],
    impact: { documents: number, templates: number % 4 },
  }
})

async function fixtures(page: Page) {
  await page.context().addCookies([{ name: 'csrftoken', value: 'metadata-layout-csrf-token', url: 'http://localhost:3200' }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: [], surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Northwest Clinical Technology Group', classifications: ['client'], capabilities: ['overview', 'custom_fields'],
    organization: { id: organizationId, name: 'Northwest Clinical Technology Group', legal_name: '', website: '', classifications: ['client'], access_mode: 'assigned_only', created_at: createdAt, updated_at: createdAt, billing_contact_name: '', billing_email: '', billing_phone: '', billing_address_line_1: '', billing_address_line_2: '', billing_city: '', billing_region: '', billing_postal_code: '', billing_country_code: '' },
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/custom-field-definitions`, (route) => route.fulfill({ json: { results: fields.map((field, index) => index < 2 ? { ...field, inherited: true } : { ...field, owner: 'organization', organization_id: organizationId }), count: fields.length } }))
  await page.route('**/api/v1/custom-field-definitions', (route) => route.fulfill({ json: { results: fields, count: fields.length } }))
  await page.route('**/api/v1/taxonomies**', (route) => taxonomyResponse(route))
}

async function taxonomyResponse(route: Route) {
  const url = new URL(route.request().url())
  if (url.pathname.endsWith('/migration')) {
    return route.fulfill({ json: { counts: { matched: 1, unmatched: 1, ambiguous: 0 }, rows: [{ document_id: '30000000-0000-4000-8000-000000000001', document_title: 'Regional identity recovery procedure with a long document title', tag: 'Azure AD', status: 'matched', term_id: taxonomies[0].current_version.terms[0].id, term_label: 'Term 1' }] } })
  }
  return route.fulfill({ json: { results: taxonomies, count: taxonomies.length } })
}

async function expectContained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`metadata administration fits ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 600 : 720 })
    await fixtures(page)

    await page.goto('/custom-fields')
    await expect(page.getByRole('heading', { name: 'Custom fields' })).toBeVisible()
    await expect(page.getByText('31 fields')).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page.getByText('Regional metadata field 26', { exact: true })).toBeVisible()
    await page.getByPlaceholder('Search custom fields').fill('Regional metadata field 31')
    await expect(page).toHaveURL(/q=Regional\+metadata\+field\+31/)
    await expect(page).not.toHaveURL(/page=2/)
    await expect(page.getByText('Regional metadata field 31', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Search: Regional metadata field 31 ×' })).toBeVisible()
    await expectContained(page)

    await page.getByRole('button', { name: 'New field' }).click()
    await expect(page).toHaveURL(/field=new/)
    const fieldEditor = page.getByRole('dialog', { name: 'Add custom field' })
    await expect(fieldEditor).toBeVisible()
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    if (width < 768) expect((await fieldEditor.boundingBox())?.width).toBe(width)
    await fieldEditor.getByRole('button', { name: 'Cancel' }).click()
    await expect(fieldEditor).toHaveCount(0)
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('')

    await page.goto('/custom-fields?field=missing-definition')
    const missingField = page.getByRole('alert').filter({ hasText: 'That custom field is no longer available.' })
    await expect(missingField).toBeVisible()
    await missingField.getByRole('button', { name: 'Close' }).click()
    await expect(page).not.toHaveURL(/field=/)

    await page.goto(`/workspaces/organizations/${organizationId}/custom_fields?q=Regional%20metadata%20field%2031`)
    await expect(page.getByText('Regional metadata field 31', { exact: true })).toBeVisible()
    await expect(page.getByText('This workspace · Version 2', { exact: true })).toBeVisible()
    await expectContained(page)

    await page.goto('/taxonomies')
    await expect(page.getByRole('heading', { name: 'Taxonomies' })).toBeVisible()
    await expect(page.getByText('31 taxonomies')).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.getByText('Regional taxonomy 26')).toBeVisible()
    await page.getByPlaceholder('Search taxonomies').fill('Regional taxonomy 31')
    await expect(page.getByText('Regional taxonomy 31', { exact: true })).toBeVisible()
    await expectContained(page)

    await page.goto('/taxonomies?taxonomy=missing-taxonomy')
    const missingTaxonomy = page.getByRole('alert').filter({ hasText: 'That taxonomy is no longer available.' })
    await expect(missingTaxonomy).toBeVisible()
    await missingTaxonomy.getByRole('button', { name: 'Close' }).click()
    await expect(page).not.toHaveURL(/taxonomy=/)

    await page.getByRole('button', { name: 'Match existing tags' }).click()
    await expect(page).toHaveURL(/view=migration/)
    await page.getByRole('button', { name: 'Preview matches' }).click()
    await expect(page.getByText('1 matched · 1 unmatched · 0 ambiguous')).toBeVisible()
    await expect(page.getByText('Regional identity recovery procedure with a long document title')).toBeVisible()
    await expectContained(page)

    await page.getByRole('button', { name: 'Back to taxonomies' }).click()
    await page.getByRole('button', { name: 'New taxonomy' }).click()
    const taxonomyEditor = page.getByRole('dialog', { name: 'New taxonomy' })
    await expect(taxonomyEditor).toBeVisible()
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    await expectContained(page)
    await taxonomyEditor.getByRole('button', { name: 'Cancel' }).click()

    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}
