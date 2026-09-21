import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const documentId = crypto.randomUUID()
const publicationId = crypto.randomUUID()
const currentRevisionId = crypto.randomUUID()
const olderRevisionId = crypto.randomUUID()
const placement = { id: crypto.randomUUID(), block_id: crypto.randomUUID(), block_name: 'Recovery guide — content', block_kind: 'rich_text', parent_id: null, position: 0, depth: 0, resolution_mode: 'live', audience_profile: 'shared', pinned_revision_id: null, resolved_revision_id: currentRevisionId, resolved_revision_number: 75, resolved_checksum: 'abc', resolved_markdown: 'Recovery steps', resolved_html: '<p>Recovery steps</p>', is_primary: true }
const publication = {
  id: publicationId, source_document_id: documentId, title: 'Retained recovery guide', category: 'guide', reason: 'Approved for disaster recovery', audience: 'msp_internal', retention: 'permanent', retention_review_on: null, lifecycle_state: 'published', supersedes_id: null, superseded_by_id: null,
  control_events: [{ id: crypto.randomUUID(), action: 'approved', reason: 'Approved for disaster recovery', actor: 'Primary Owner', occurred_at: '2026-09-20T12:00:00Z' }],
  audience_projections: [{ audience: 'msp_staff', available: true, state: 'retained' }, { audience: 'client_portal', available: false, state: 'not_intended' }],
  artifacts: [], content_digest: 'a'.repeat(64), signature_algorithm: 'Ed25519', signature: 'signature', public_key: 'public-key', key_fingerprint: 'b'.repeat(64), published_by: 'Primary Owner', published_at: '2026-09-20T12:00:00Z', verification: { valid: true, digest_valid: true, signature_valid: true, key_fingerprint_valid: true }, canonical_markdown: '# Recovery guide', sanitized_html: '<h1>Recovery guide</h1>', manifest: { format: 'tekdocs-static-publication/v2' },
}
const document = {
  id: documentId, title: 'Recovery guide', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, category: 'guide', is_template: false, library_visible: false, template_enrollment_id: null, template_applied_revision_id: null, template_source_id: null, collection: 'Runbooks', tags: ['recovery'], owner_id: null, owner_name: null, review_due_on: null, review_state: 'approved', review_requested_by_id: null, review_requested_by_name: null, review_requested_at: null, reviewer_id: null, reviewer_name: null, review_decided_at: null, last_reviewed_by_id: null, last_reviewed_by_name: null, last_reviewed_at: null, review_note: '', health_status: 'current', attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [publication], publication_count: 1, markdown: '# Recovery guide', block_id: placement.block_id, current_revision_id: currentRevisionId, revision_number: 75, checksum: 'abc', resolved_markdown: '# Recovery guide', placements: [placement], placement_count: 1, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-20T12:00:00Z',
}

async function setup(page: Page, baseURL: string) {
  let historyReads = 0
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' }, tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.edit'] } }))
  await page.route('**/api/v1/documents/topic-schemas', (route) => route.fulfill({ json: { topics: [] } }))
  await page.route('**/api/v1/documents**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith(`/publications/${publicationId}`)) return route.fulfill({ json: publication })
    if (url.pathname.endsWith(`/revisions/${olderRevisionId}`)) return route.fulfill({ json: { id: olderRevisionId, parent_id: crypto.randomUUID(), revision_number: 25, checksum: 'def', created_by: 'Primary Owner', created_at: '2026-09-08T00:00:00Z', is_current: false, markdown: '# Older recovery guide', diff_from_parent: '+# Older recovery guide' } })
    if (url.pathname.endsWith(`/${documentId}/revisions`)) {
      if (++historyReads === 1) return route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
      const pageNumber = Number(url.searchParams.get('page') ?? '1')
      const revision = pageNumber === 2
        ? { id: olderRevisionId, parent_id: crypto.randomUUID(), revision_number: 25, checksum: 'def', created_by: 'Primary Owner', created_at: '2026-09-08T00:00:00Z', is_current: false }
        : { id: currentRevisionId, parent_id: olderRevisionId, revision_number: 75, checksum: 'abc', created_by: 'Primary Owner', created_at: '2026-09-20T00:00:00Z', is_current: true }
      return route.fulfill({ json: { results: [revision], count: 75, page: pageNumber, page_size: 50, has_more: pageNumber === 1 } })
    }
    if (url.pathname.endsWith(`/${documentId}`)) return route.fulfill({ json: document })
    if (url.pathname.endsWith('/search')) return route.fulfill({ json: { results: [document], count: 1, page: 1, page_size: 25, has_more: false } })
    return route.fulfill({ status: 404, json: { detail: 'Not found' } })
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`document and publication history links at ${width}px`, async ({ page, baseURL }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await setup(page, baseURL!)
    await page.goto(`/documentation?document=${documentId}`)
    await page.getByRole('button', { name: 'History' }).click()
    await expect(page).toHaveURL(/document_view=history/)
    const revisionHistory = page.locator('.revision-history')
    await expect(revisionHistory.getByRole('alert')).toContainText('Revision history is unavailable.')
    await revisionHistory.getByRole('button', { name: 'Retry' }).click()
    await expect(page.getByText(/page 1/)).toBeVisible()
    await page.getByRole('button', { name: 'Older' }).click()
    await expect(page).toHaveURL(/document_history_page=2/)
    await page.getByRole('button', { name: /Revision 25/ }).click()
    await expect(page).toHaveURL(new RegExp(`document_revision=${olderRevisionId}`))
    await expect(page.getByRole('heading', { name: 'Revision 25' })).toBeVisible()
    await page.goBack()
    await expect(page).not.toHaveURL(/document_revision=/)
    await expect(page.getByText(/page 2/)).toBeVisible()
    await page.goBack()
    await expect(page).not.toHaveURL(/document_history_page=/)
    await expect(page.getByText(/page 1/)).toBeVisible()
    await page.goForward()
    await page.goForward()
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Revision 25' })).toBeVisible()
    expect((await new AxeBuilder({ page }).include('.revision-history').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => globalThis.document.documentElement.scrollWidth <= globalThis.document.documentElement.clientWidth + 1)).toBe(true)
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/document-history-link-${width}.png`, fullPage: true })

    await page.goto(`/documentation?document=${documentId}&publication=${publicationId}&publication_section=history`)
    const history = page.getByRole('region', { name: 'Publication history' })
    await expect(history).toContainText('Approved for disaster recovery')
    await page.getByRole('button', { name: 'Downloads' }).click()
    await expect(page).toHaveURL(/publication_section=downloads/)
    await expect(page.getByRole('heading', { name: 'Downloads' })).toBeVisible()
    await page.goBack()
    await expect(page).toHaveURL(/publication_section=history/)
    await expect(history).toBeVisible()
    expect((await new AxeBuilder({ page }).include('.static-publication').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => globalThis.document.documentElement.scrollWidth <= globalThis.document.documentElement.clientWidth + 1)).toBe(true)
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/publication-history-link-${width}.png`, fullPage: true })
  })
}
