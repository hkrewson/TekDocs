import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const organizationId = crypto.randomUUID(), documentId = crypto.randomUUID(), blockId = crypto.randomUUID(), revisionId = crypto.randomUUID()
const placement = { id: crypto.randomUUID(), block_id: blockId, block_name: 'Network guidance', block_kind: 'rich_text', parent_id: null, position: 0, depth: 0, resolution_mode: 'live', audience_profile: 'shared', pinned_revision_id: null, resolved_revision_id: revisionId, resolved_revision_number: 1, resolved_checksum: 'abc', resolved_markdown: 'Reviewed guidance', resolved_html: '<p>Reviewed guidance</p>', is_primary: true }
const record = { id: documentId, title: 'Network baseline', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, category: 'guide', is_template: true, library_visible: true, markdown: 'Reviewed guidance', block_id: blockId, current_revision_id: revisionId, revision_number: 1, checksum: 'abc', resolved_markdown: 'Reviewed guidance', placements: [placement, { ...placement, id: crypto.randomUUID(), block_id: crypto.randomUUID(), block_name: 'Shared instructions', is_primary: false, position: 1 }], placement_count: 2, attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [], publication_count: 0, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
function samplePdf() {
  const first = 'BT /F1 18 Tf 40 750 Td (Setup first page) Tj ET'
  const second = 'BT /F1 18 Tf 40 750 Td (Recovery second page) Tj ET'
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>', `<< /Length ${first.length} >>\nstream\n${first}\nendstream`, '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>', `<< /Length ${second.length} >>\nstream\n${second}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
  let pdf = '%PDF-1.4\n'
  const offsets = [0]
  for (const [index, object] of objects.entries()) { offsets.push(Buffer.byteLength(pdf)); pdf += `${index + 1} 0 obj\n${object}\nendobj\n` }
  const xref = Buffer.byteLength(pdf)
  pdf += `xref\n0 8\n0000000000 65535 f \n${offsets.slice(1).map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(pdf)
}
async function setup(page: Page, baseURL: string) {
  const reviewerId = crypto.randomUUID()
  const attachment = { id: 'attachment-1', filename: 'network-recovery-instructions-with-a-long-filename.pdf', media_type: 'application/pdf', size: 1024, checksum: 'd'.repeat(64), scan_status: 'clean', scan_engine: 'test-scanner', scanned_at: '2026-09-01T00:00:00Z', created_at: '2026-09-01T00:00:00Z' }
  const primary = { ...attachment, id: 'primary-1', filename: 'primary-guide.pdf', version_number: 1, replaces_id: null as string | null, is_current: true }
  let current = { ...record, is_template: false, owner_organization_id: organizationId, owner_kind: 'organization', attachments: [attachment], attachment_count: 1, primary_file: primary, primary_file_versions: [primary] }
  let downloads = 0, uploads = 0, replacements = 0
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (r) => r.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (r) => r.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (r) => r.fulfill({ json: { user: { id: reviewerId, email: 'reviewer@example.invalid', display_name: 'Alex Rivera' }, tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.edit', 'documents.approve'] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (r) => r.fulfill({ json: { kind: 'organization', id: organizationId, name: 'Example client', classifications: ['client'], capabilities: ['overview', 'documentation'], organization: null } }))
  await page.route('**/api/v1/documents/topic-schemas', (r) => r.fulfill({ json: { topics: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/documents**`, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/download')) {
      if (url.pathname.includes('/attachment-1/') && ++downloads === 1) return route.fulfill({ status: 403 })
      return route.fulfill({ contentType: 'application/pdf', body: samplePdf() })
    }
    if (url.pathname.endsWith('/attachments') && route.request().method() === 'POST') {
      if (++uploads === 1) return route.fulfill({ status: 403, json: { detail: 'Denied' } })
      const added = { ...attachment, id: 'notes-1', filename: 'notes.txt', media_type: 'text/plain' }
      current = { ...current, attachments: [...current.attachments, added], attachment_count: current.attachment_count + 1 }
      return route.fulfill({ json: added })
    }
    if (url.pathname.endsWith('/primary-file')) {
      if (++replacements === 1) return route.fulfill({ status: 403, json: { detail: 'Denied' } })
      const replaced = { ...primary, id: 'primary-2', filename: 'replacement.pdf', version_number: 2, replaces_id: primary.id }
      current = { ...current, primary_file: replaced, primary_file_versions: [replaced, { ...primary, is_current: false }] }
      return route.fulfill({ json: replaced })
    }
    if (url.pathname.endsWith('/attachments/attachment-1') && route.request().method() === 'DELETE') {
      current = { ...current, attachments: current.attachments.filter((file) => file.id !== 'attachment-1'), attachment_count: current.attachment_count - 1 }
      return route.fulfill({ status: 204, body: '' })
    }
    if (url.pathname.endsWith(`/${documentId}`)) return route.fulfill({ json: current })
    return route.fulfill({ json: { results: [current], count: 1, page: 1, page_size: 25, has_more: false } })
  })
}
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`managed files and PDF switching at ${width}px`, async ({ page, baseURL }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await setup(page, baseURL!)
    await page.goto(`/workspaces/organizations/${organizationId}/documentation?document=${documentId}`)
    await page.getByRole('button', { name: 'Files (1)', exact: true }).click()
    const files = page.locator('.document-files')
    const pdf = files.locator('.pdf-viewer')
    await expect(pdf.getByText('Page 1 of 2')).toBeVisible()
    await pdf.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(pdf.getByText('Page 2 of 2')).toBeVisible()
    await pdf.getByRole('searchbox').fill('Recovery')
    await pdf.getByRole('button', { name: 'Search', exact: true }).click()
    await expect(pdf.getByRole('status')).toHaveText('Found on page 2.')
    const attachmentRow = files.locator('li').filter({ hasText: 'network-recovery-instructions-with-a-long-filename.pdf' })
    await attachmentRow.getByRole('button', { name: 'View PDF' }).click()
    await expect(pdf.getByRole('alert')).toHaveText('The PDF could not be opened.')
    await pdf.getByRole('button', { name: 'Try again' }).click()
    await expect(pdf.getByText('Page 1 of 2')).toBeVisible()
    await expect(pdf.getByRole('searchbox')).toHaveValue('')
    await pdf.getByText('Page text', { exact: true }).click()
    await expect(pdf.getByText('Setup first page', { exact: true })).toBeVisible()
    await pdf.getByRole('button', { name: 'Zoom in' }).click()
    await expect(pdf.getByText('140%')).toBeVisible()
    expect((await new AxeBuilder({ page }).include('.document-files').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    await pdf.locator('.pdf-canvas').focus()
    await expect(pdf.locator('.pdf-canvas')).toBeFocused()
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/document-files-${width}.png`, fullPage: true })
    await page.keyboard.press('Escape')
    await expect(attachmentRow.getByRole('button', { name: 'View PDF' })).toBeFocused()
    const upload = { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Operational notes') }
    await files.getByLabel('Attachment', { exact: true }).setInputFiles(upload)
    await expect(page.getByRole('alert')).toContainText('Your account is not authorized')
    await files.getByLabel('Attachment', { exact: true }).setInputFiles(upload)
    await expect(files.getByRole('link', { name: /notes.txt/ })).toBeVisible()
    const replacement = { name: 'replacement.pdf', mimeType: 'application/pdf', buffer: samplePdf() }
    await files.getByLabel('Replacement primary file').setInputFiles(replacement)
    await expect(page.getByRole('alert')).toContainText('Your account is not authorized')
    await files.getByLabel('Replacement primary file').setInputFiles(replacement)
    await expect(files.getByText('Version 2 · Current · 1,024 bytes')).toBeVisible()
    await expect(files.getByText('Version 1 · 1,024 bytes')).toBeVisible()
    await expect(pdf.getByRole('heading', { name: 'replacement.pdf' })).toBeVisible()
    await attachmentRow.getByRole('button', { name: 'View PDF' }).click()
    await attachmentRow.getByRole('button', { name: /Remove / }).click()
    await expect(pdf).toHaveCount(0)
    await files.getByRole('button', { name: 'Close files' }).click()
    await expect(page.getByRole('button', { name: 'Files (1)', exact: true })).toBeFocused()
  })
}
