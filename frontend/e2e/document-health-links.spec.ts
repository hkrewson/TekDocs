import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const organizationId = crypto.randomUUID()
const staleId = crypto.randomUUID()
const candidateId = crypto.randomUUID()
const revisionId = crypto.randomUUID()
const placement = { id: crypto.randomUUID(), block_id: crypto.randomUUID(), block_name: 'Recovery standard — content', block_kind: 'rich_text', parent_id: null, position: 0, depth: 0, resolution_mode: 'live', audience_profile: 'shared', pinned_revision_id: null, resolved_revision_id: revisionId, resolved_revision_number: 1, resolved_checksum: 'abc', resolved_markdown: 'Recovery steps', resolved_html: '<p>Recovery steps</p>', is_primary: true }
const base = { owner_kind: 'organization', owner_organization_id: organizationId, owner_organization_name: 'Example client', is_reference: false, category: 'guide', is_template: false, library_visible: false, template_enrollment_id: null, template_applied_revision_id: null, template_source_id: null, collection: 'Runbooks', tags: ['recovery'], owner_id: null, owner_name: null, review_due_on: null, review_state: 'unreviewed', review_requested_by_id: null, review_requested_by_name: null, review_requested_at: null, reviewer_id: null, reviewer_name: null, review_decided_at: null, last_reviewed_by_id: null, last_reviewed_by_name: null, last_reviewed_at: null, review_note: '', attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [], publication_count: 0, markdown: 'Recovery steps', block_id: placement.block_id, current_revision_id: revisionId, revision_number: 1, checksum: 'abc', resolved_markdown: 'Recovery steps', placements: [placement], placement_count: 1, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
const current = { ...base, id: crypto.randomUUID(), title: 'Current network standard', health_status: 'current' }
const stale = { ...base, id: staleId, title: 'Recovery standard requiring review', health_status: 'stale' }
const candidate = { ...base, id: candidateId, title: 'Off-page disaster recovery plan', health_status: 'unowned', current_revision_id: crypto.randomUUID() }

async function setup(page: Page, baseURL: string) {
  let linkReads = 0
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' }, tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.edit'] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: { kind: 'organization', id: organizationId, name: 'Example client', classifications: ['client'], capabilities: ['overview', 'documentation'], organization: null } }))
  await page.route('**/api/v1/documents/topic-schemas', (route) => route.fulfill({ json: { topics: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/documents**`, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/block-library')) return route.fulfill({ json: { results: [], count: 0, page: 1, page_size: 20, has_more: false } })
    if (url.pathname.endsWith(`/${staleId}/placements`) && route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toMatchObject({ source_document_id: candidateId, resolution_mode: 'live', pinned_revision_id: null, audience_profile: 'shared' })
      return route.fulfill({ json: { ...stale, placements: [placement, { ...placement, id: crypto.randomUUID(), block_id: candidate.block_id, block_name: 'Off-page disaster recovery plan — content', is_primary: false, position: 1, resolved_markdown: 'Linked recovery plan', resolved_html: '<p>Linked recovery plan</p>' }], placement_count: 2 } })
    }
    if (url.pathname.endsWith(`/${staleId}`)) return route.fulfill({ json: stale })
    if (url.pathname.endsWith('/search')) {
      if (url.searchParams.get('exclude_document') === staleId) {
        if (++linkReads === 1) return route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
        expect(url.searchParams.get('page_size')).toBe('20')
        const results = url.searchParams.get('q') ? [candidate] : [candidate, current]
        return route.fulfill({ json: { results, count: results.length, page: 1, page_size: 20, has_more: false } })
      }
      if (url.searchParams.get('health') === 'attention') return route.fulfill({ json: { results: [stale], count: 26, page: 1, page_size: 25, has_more: true, health: [{ value: 'current', count: 1 }, { value: 'stale', count: 26 }] } })
      return route.fulfill({ json: { results: [current], count: 51, page: 1, page_size: 25, has_more: true, health: [{ value: 'current', count: 51 }] } })
    }
    return route.fulfill({ status: 404, json: { detail: 'Not found' } })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`content health and document links at ${width}px`, async ({ page, baseURL }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await setup(page, baseURL!)
    await page.goto(`/workspaces/organizations/${organizationId}/documentation`)
    await page.getByRole('button', { name: 'Content health' }).click()
    await expect(page).toHaveURL(/doc_library=health/)
    await expect(page.getByRole('button', { name: /Recovery standard requiring review/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /Current network standard/ })).toHaveCount(0)
    await expect(page.getByRole('navigation', { name: 'documents pages' })).toContainText('1–25 of 26')
    expect((await new AxeBuilder({ page }).include('.document-index').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/document-health-${width}.png`, fullPage: true })

    await page.getByRole('button', { name: /Recovery standard requiring review/ }).click()
    await page.getByRole('button', { name: 'Add content here' }).last().click()
    await page.getByRole('button', { name: 'Existing content' }).click()
    const picker = page.locator('.document-link-picker')
    await expect(picker.getByRole('alert')).toContainText('Documents could not be loaded')
    await picker.getByRole('button', { name: 'Retry' }).click()
    await picker.getByRole('searchbox', { name: 'Find a document' }).fill('disaster recovery')
    const insertDocument = picker.getByRole('button', { name: 'Insert Off-page disaster recovery plan' })
    await expect(insertDocument).toBeVisible()
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/document-link-picker-${width}.png`, fullPage: true })
    await insertDocument.click()
    await expect(page.getByRole('status')).toHaveText('Off-page disaster recovery plan inserted.')
    await expect(page.getByText('Linked recovery plan', { exact: true })).toBeVisible()
    expect((await new AxeBuilder({ page }).include('.document-page').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  })
}
