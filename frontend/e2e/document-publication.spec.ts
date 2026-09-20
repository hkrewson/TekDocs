import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const organizationId = crypto.randomUUID(), documentId = crypto.randomUUID(), blockId = crypto.randomUUID(), revisionId = crypto.randomUUID()
const placement = { id: crypto.randomUUID(), block_id: blockId, block_name: 'Network guidance', block_kind: 'rich_text', parent_id: null, position: 0, depth: 0, resolution_mode: 'live', audience_profile: 'shared', pinned_revision_id: null, resolved_revision_id: revisionId, resolved_revision_number: 1, resolved_checksum: 'abc', resolved_markdown: 'Reviewed guidance', resolved_html: '<p>Reviewed guidance</p>', is_primary: true }
const record = { id: documentId, title: 'Network baseline', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, category: 'guide', is_template: true, library_visible: true, markdown: 'Reviewed guidance', block_id: blockId, current_revision_id: revisionId, revision_number: 1, checksum: 'abc', resolved_markdown: 'Reviewed guidance', placements: [placement, { ...placement, id: crypto.randomUUID(), block_id: crypto.randomUUID(), block_name: 'Shared instructions', is_primary: false, position: 1 }], placement_count: 2, attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [], publication_count: 0, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
async function setup(page: Page, baseURL: string) {
  const reviewerId = crypto.randomUUID()
  const current = { ...record, is_template: false, owner_organization_id: organizationId, owner_kind: 'organization' }
  let checks = 0
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (r) => r.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (r) => r.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (r) => r.fulfill({ json: { user: { id: reviewerId, email: 'reviewer@example.invalid', display_name: 'Alex Rivera' }, tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.edit', 'documents.approve'] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (r) => r.fulfill({ json: { kind: 'organization', id: organizationId, name: 'Example client', classifications: ['client'], capabilities: ['overview', 'documentation'], organization: null } }))
  await page.route('**/api/v1/documents/topic-schemas', (r) => r.fulfill({ json: { topics: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/documents**`, async (route) => {
    const url = new URL(route.request().url())
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
    await page.getByRole('button', { name: /Network baseline/ }).click()
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
    expect((await new AxeBuilder({ page }).include('.document-export-panel').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
  })
}
