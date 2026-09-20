import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const organizationId = crypto.randomUUID(), documentId = crypto.randomUUID(), blockId = crypto.randomUUID(), revisionId = crypto.randomUUID()
const placement = { id: crypto.randomUUID(), block_id: blockId, block_name: 'Network guidance', block_kind: 'rich_text', parent_id: null, position: 0, depth: 0, resolution_mode: 'live', audience_profile: 'shared', pinned_revision_id: null, resolved_revision_id: revisionId, resolved_revision_number: 1, resolved_checksum: 'abc', resolved_markdown: 'Reviewed guidance', resolved_html: '<p>Reviewed guidance</p>', is_primary: true }
const record = { id: documentId, title: 'Network baseline', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, category: 'guide', is_template: true, library_visible: true, markdown: 'Reviewed guidance', block_id: blockId, current_revision_id: revisionId, revision_number: 1, checksum: 'abc', resolved_markdown: 'Reviewed guidance', placements: [placement, { ...placement, id: crypto.randomUUID(), block_id: crypto.randomUUID(), block_name: 'Shared instructions', is_primary: false, position: 1 }], placement_count: 2, attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [], publication_count: 0, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
const publicationId = crypto.randomUUID()
const publication = { id: publicationId, source_document_id: documentId, title: 'Network baseline', category: 'policy' as const, reason: 'Approved for operations', audience: 'client_visible' as const, retention: 'permanent' as const, retention_review_on: null, lifecycle_state: 'pending_approval' as const, supersedes_id: null, superseded_by_id: null, control_events: [{ id: 'event-1', action: 'submitted' as const, reason: 'Approved for operations', actor: 'Primary Owner', occurred_at: '2026-08-09T01:00:00Z' }, { id: 'event-2', action: 'approved' as const, reason: 'Approved for MSP-internal distribution at publication time.', actor: 'Primary Owner', occurred_at: '2026-08-09T01:00:00Z' }], audience_projections: [{ audience: 'msp_staff' as const, available: true, state: 'retained' }, { audience: 'client_portal' as const, available: false, state: 'not_intended' }], artifacts: [{ id: 'pdf-1', kind: 'pdf' as const, filename: 'firewall-static.pdf', media_type: 'application/pdf', size: 1200, checksum: 'c'.repeat(64), source_attachment_id: null }], content_digest: 'a'.repeat(64), signature_algorithm: 'Ed25519' as const, signature: 'signature', public_key: 'public-key', key_fingerprint: 'b'.repeat(64), published_by: 'Primary Owner', published_at: '2026-08-09T01:00:00Z', verification: { valid: true, digest_valid: true, signature_valid: true, key_fingerprint_valid: true }, canonical_markdown: '# Firewall\n', sanitized_html: '<h1>Firewall</h1>', manifest: { format: 'tekdocs-static-publication/v2' } }
async function setup(page: Page, baseURL: string) {
  const reviewerId = crypto.randomUUID()
  const attachment = { id: 'attachment-1', filename: 'network-recovery-instructions-with-a-long-filename.txt', media_type: 'text/plain', size: 42, checksum: 'd'.repeat(64), scan_status: 'clean', scan_engine: 'test-scanner', scanned_at: '2026-09-01T00:00:00Z', created_at: '2026-09-01T00:00:00Z' }
  const primary = { ...attachment, id: 'primary-1', filename: 'current-guide.txt', version_number: 1, replaces_id: null, is_current: true }
  let current = { ...record, is_template: false, owner_organization_id: organizationId, owner_kind: 'organization', publications: [publication], publication_count: 1, attachments: [attachment], attachment_count: 1, primary_file: primary, primary_file_versions: [primary] }
  let checks = 0, publicationReads = 0, approvals = 0
  let retained = { ...publication, control_events: publication.control_events.slice(0, 1), lifecycle_state: 'pending_approval', artifacts: [...publication.artifacts, { id: 'retained-1', kind: 'attachment', filename: 'network-recovery-checklist-with-a-very-long-descriptive-filename-for-testing.txt', media_type: 'text/plain', size: 42, checksum: 'd'.repeat(64), source_attachment_id: 'file-1' }] }
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (r) => r.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (r) => r.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (r) => r.fulfill({ json: { user: { id: reviewerId, email: 'reviewer@example.invalid', display_name: 'Alex Rivera' }, tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.edit', 'documents.approve'] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (r) => r.fulfill({ json: { kind: 'organization', id: organizationId, name: 'Example client', classifications: ['client'], capabilities: ['overview', 'documentation'], organization: null } }))
  await page.route('**/api/v1/documents/topic-schemas', (r) => r.fulfill({ json: { topics: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/documents**`, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/attachments/attachment-1') && route.request().method() === 'DELETE') {
      current = { ...current, attachments: [], attachment_count: 0 }
      return route.fulfill({ status: 204, body: '' })
    }
    if (url.pathname.endsWith('/approve')) {
      expect(route.request().postDataJSON()).toEqual({ reason: 'Independent approval' })
      if (++approvals === 1) return route.fulfill({ status: 403, json: { detail: 'Denied' } })
      retained = { ...retained, control_events: publication.control_events, lifecycle_state: 'published' }
      return route.fulfill({ json: retained })
    }
    if (url.pathname.endsWith('/withdraw')) {
      expect(route.request().postDataJSON()).toEqual({ reason: 'Replaced instructions' })
      retained = { ...retained, lifecycle_state: 'withdrawn' }
      return route.fulfill({ json: retained })
    }
    if (url.pathname.endsWith(`/publications/${publicationId}`)) {
      if (++publicationReads === 1) return route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
      return route.fulfill({ json: retained })
    }
    if (url.pathname.endsWith('/preflight')) {
      if (++checks === 1) return route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
      return route.fulfill({ json: { version: 'tekdocs-preflight/v1', scope: 'document', scope_id: documentId, composition_digest: 'a'.repeat(64), audience: url.searchParams.get('audience'), valid: true, counts: { blocker: 0, warning: 0, info: 0 }, findings: [] } })
    }
    if (url.pathname.endsWith(`/${documentId}`)) return route.fulfill({ json: current })
    return route.fulfill({ json: { results: [current], count: 1, page: 1, page_size: 25, has_more: false } })
  })
}
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`publication draft and editable exports at ${width}px`, async ({ page, baseURL }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await setup(page, baseURL!)
    await page.goto(`/workspaces/organizations/${organizationId}/documentation`)
    await page.getByRole('button', { name: /^Network baseline Guide/ }).click()
    await page.getByRole('button', { name: 'Publish document' }).click()
    const form = page.locator('.publication-form')
    await expect(form.getByRole('alert')).toBeVisible()
    await expect(form.getByRole('heading', { level: 2 })).toBeFocused()
    await form.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Reviewed client release')
    await form.getByRole('combobox', { name: 'Who can see it?' }).selectOption('client_visible')
    await expect(form.getByRole('button', { name: 'Publish', exact: true })).toBeEnabled()
    await form.getByRole('button', { name: 'Retry publication check' }).click()
    await expect(form.getByRole('button', { name: 'Publish', exact: true })).toBeEnabled()
    await page.goBack()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(form.getByRole('textbox', { name: 'Why are you publishing this?' })).toHaveValue('Reviewed client release')
    expect((await new AxeBuilder({ page }).include('.publication-form').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    await form.getByRole('heading', { level: 2 }).focus()
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/document-publication-${width}.png`, fullPage: true })
    await form.getByRole('button', { name: 'Cancel publication' }).click()
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('button', { name: 'Publish document' })).toBeFocused()
    await page.getByRole('button', { name: 'Export', exact: true }).click()
    const exports = page.locator('.document-export-panel')
    for (const [name, format] of [['Markdown', 'md'], ['HTML', 'html'], ['PDF', 'pdf'], ['DOCX', 'docx'], ['Download ZIP', 'bundle']]) {
      await expect(exports.getByRole('link', { name, exact: true })).toHaveAttribute('href', new RegExp(`/documents/${documentId}/export\\?export_format=${format}$`))
    }
    await expect(exports.getByRole('status')).toHaveText('Files selected for ZIP: 0')
    await exports.getByRole('checkbox', { name: /network-recovery-instructions/ }).check()
    await expect(exports.getByRole('link', { name: 'Download ZIP' })).toHaveAttribute('href', /export_format=bundle&attachment_ids=attachment-1$/)
    await expect(exports.getByRole('checkbox', { name: /current-guide/ })).not.toBeChecked()
    await exports.getByRole('button', { name: 'Close downloads' }).click()
    await expect(page.getByRole('button', { name: 'Export', exact: true })).toBeFocused()
    await page.getByRole('button', { name: 'Export', exact: true }).click()
    await expect(exports.getByRole('checkbox', { name: /network-recovery-instructions/ })).toBeChecked()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/document-exports-${width}.png`, fullPage: true })
    expect((await new AxeBuilder({ page }).include('.document-export-panel').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    await page.getByRole('button', { name: 'Files (1)', exact: true }).click()
    await page.getByRole('button', { name: 'Remove network-recovery-instructions-with-a-long-filename.txt' }).click()
    await page.getByRole('button', { name: 'Export', exact: true }).click()
    await expect(exports.getByRole('link', { name: 'Download ZIP' })).toHaveAttribute('href', /export_format=bundle$/)
    await expect(exports.getByRole('status')).toHaveText('Files selected for ZIP: 0')
  })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`retained publication sections and lifecycle at ${width}px`, async ({ page, baseURL }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await setup(page, baseURL!)
    await page.goto(`/workspaces/organizations/${organizationId}/documentation`)
    const row = page.getByRole('button', { name: /Published ·/ })
    await row.click()
    const viewer = page.locator('.static-publication')
    await expect(viewer.getByRole('alert')).toHaveText('This published version could not be loaded.')
    await viewer.getByRole('button', { name: 'Try again' }).click()
    await expect(viewer.getByRole('heading', { name: 'Network baseline', exact: true })).toBeFocused()
    await expect(viewer.getByRole('region', { name: 'Content', exact: true })).toContainText('Firewall')
    await viewer.getByRole('button', { name: 'Downloads', exact: true }).click()
    await expect(viewer.getByRole('link', { name: 'Download PDF', exact: true })).toHaveAttribute('href', new RegExp(`/publications/${publicationId}/export\\?export_format=pdf$`))
    await expect(viewer.getByRole('link', { name: /network-recovery-checklist/ })).toHaveAttribute('href', new RegExp(`/publications/${publicationId}/artifacts/retained-1/download$`))
    await viewer.getByRole('button', { name: 'History', exact: true }).click()
    await expect(viewer.getByRole('region', { name: 'Publication history' })).toContainText('Approved for operations')
    await viewer.getByRole('button', { name: 'Approve publication' }).click()
    await viewer.getByRole('textbox', { name: 'Decision reason' }).fill('Independent approval')
    await viewer.getByRole('button', { name: 'Downloads', exact: true }).click()
    await expect(viewer.getByRole('textbox', { name: 'Decision reason' })).toHaveValue('Independent approval')
    page.once('dialog', (dialog) => dialog.accept())
    await viewer.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('Your account is not authorized')
    await expect(viewer.getByRole('textbox', { name: 'Decision reason' })).toHaveValue('Independent approval')
    page.once('dialog', (dialog) => dialog.accept())
    await viewer.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('Published version approved')
    await viewer.getByRole('button', { name: 'Publish correction' }).click()
    await expect(page.getByRole('combobox', { name: 'Who can see it?' })).toBeDisabled()
    await page.getByRole('button', { name: 'Cancel publication' }).click()
    await expect(viewer.getByRole('button', { name: 'Publish correction' })).toBeFocused()
    await viewer.getByRole('button', { name: 'Withdraw publication' }).click()
    await viewer.getByRole('textbox', { name: 'Decision reason' }).fill('Replaced instructions')
    await viewer.getByRole('button', { name: 'Close published version' }).click()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    page.once('dialog', (dialog) => dialog.accept())
    await viewer.getByRole('button', { name: 'Withdraw', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('Published version withdrawn')
    await expect(viewer.getByRole('button', { name: 'Withdraw publication' })).toHaveCount(0)
    await viewer.getByRole('button', { name: 'Downloads', exact: true }).click()
    expect((await new AxeBuilder({ page }).include('.static-publication').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    await viewer.getByRole('heading', { name: 'Network baseline', exact: true }).focus()
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/publication-viewer-${width}.png`, fullPage: true })
    await viewer.getByRole('button', { name: 'Close published version' }).click()
    await expect(row).toBeFocused()
  })
}
