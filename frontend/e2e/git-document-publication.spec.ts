import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import type { DocumentPublicationDetail, DocumentPublicationInput } from '../src/documentation/api'
import { createServer } from 'node:http'
import type { Server } from 'node:http'
import type { AddressInfo } from 'node:net'

let pdfServer: Server
let pdfUrl: string
test.beforeAll(async () => {
  // WebKit does not emit downloads for route.fulfill attachments. Serve only
  // these synthetic bytes over HTTP; keep the protected application URL under test.
  pdfServer = createServer((_request, response) => {
    response.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="retained-snapshot.pdf"' })
    response.end('%PDF-1.4\nretained snapshot\n%%EOF\n')
  })
  await new Promise<void>(resolve => pdfServer.listen(0, '127.0.0.1', resolve))
  pdfUrl = `http://127.0.0.1:${(pdfServer.address() as AddressInfo).port}/snapshot.pdf`
})
test.afterAll(async () => {
  await new Promise<void>((resolve, reject) => pdfServer.close(error => error ? reject(error) : resolve()))
})

const organizationId = crypto.randomUUID(), documentId = crypto.randomUUID(), contentId = crypto.randomUUID()
const legacyId = crypto.randomUUID(), publicationId = crypto.randomUUID(), correctionId = crypto.randomUUID()
const path = `/workspaces/organizations/${organizationId}/documentation`
const endpoint = `/api/v1/workspaces/organizations/${organizationId}/documents`
const legacy: DocumentPublicationDetail = {
  id: legacyId, source_document_id: documentId, title: 'Retained setup guide', category: 'guide',
  reason: 'Original release', audience: 'msp_internal', retention: 'permanent', retention_review_on: null,
  lifecycle_state: 'published', supersedes_id: null, superseded_by_id: null,
  artifacts: [{ id: crypto.randomUUID(), kind: 'pdf', filename: 'snapshot.pdf', media_type: 'application/pdf', size: 42, checksum: 'c'.repeat(64), source_attachment_id: null }],
  control_events: [{ id: crypto.randomUUID(), action: 'approved', reason: 'Internal release', actor: 'Fixture publisher', occurred_at: '2026-10-01T12:00:00Z' }],
  audience_projections: [{ audience: 'msp_staff', available: true, state: 'retained' }],
  content_digest: 'a'.repeat(64), signature_algorithm: 'Ed25519', signature: '', public_key: '', key_fingerprint: 'b'.repeat(64),
  published_by: 'Fixture publisher', published_at: '2026-10-01T12:00:00Z',
  verification: { valid: true, digest_valid: true, signature_valid: true, key_fingerprint_valid: true },
  canonical_markdown: 'Original signed instructions.', sanitized_html: '<p>Original signed instructions.</p>',
  manifest: { format: 'tekdocs-static-publication/v4' },
}

async function setup(page: Page, baseURL: string, options: { blocked?: boolean; noHistory?: boolean; unavailable?: boolean } = {}) {
  const records = new Map<string, typeof legacy>(options.noHistory ? [] : [[legacyId, structuredClone(legacy)]])
  const source = () => ({
    id: documentId, content_id: contentId, title: 'Git setup guide', content_authority: 'repository',
    owner_kind: 'organization', owner_organization_id: organizationId, owner_organization_name: 'Example client',
    is_reference: false, category: 'guide', is_template: false, library_visible: false,
    template_enrollment_id: null, template_applied_revision_id: null, template_source_id: null,
    markdown: '', resolved_markdown: '', placements: [], placement_count: 1,
    attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [],
    publications: [...records.values()].reverse(), publication_count: records.size,
    created_at: '2026-10-01T12:00:00Z', updated_at: '2026-10-27T12:00:00Z',
  })
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', r => r.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', r => r.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', r => r.fulfill({ json: { user: { id: crypto.randomUUID(), email: 'publisher@example.invalid', display_name: 'Fixture publisher' }, tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.publish', 'documents.approve'] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, r => r.fulfill({ json: { kind: 'organization', id: organizationId, name: 'Example client', classifications: ['client'], capabilities: ['documentation'], organization: null } }))
  await page.route('**/api/v1/documents/topic-schemas', r => r.fulfill({ json: { topics: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/content-graph/documents/${contentId}`, r => r.fulfill(options.unavailable
    ? { status: 409, json: { detail: 'Repository index unavailable' } }
    : { json: { id: contentId, kind: 'document', title: 'Git setup guide', indexed_commit: 'd'.repeat(40), sanitized_html: '<p>Current Git instructions.</p>', entity_context: [] } }))
  let creates = 0, withdrawals = 0, downloads = 0
  await page.route(`**${endpoint}**`, async r => {
    const url = new URL(r.request().url())
    if (url.pathname.endsWith('/preflight')) return r.fulfill({ json: {
      version: 'tekdocs-preflight/v1', scope: 'document', scope_id: documentId, composition_digest: 'e'.repeat(64),
      audience: 'msp_internal', valid: !options.blocked, counts: { blocker: options.blocked ? 1 : 0, warning: 0, info: 0 },
      findings: options.blocked ? [{ code: 'repository.publication.unavailable', severity: 'blocker', summary: 'Git content is not ready.', remediation: 'Refresh the Git index.', target: 'document', section_id: null, line: null }] : [],
    } })
    if (url.pathname.endsWith('/publications') && r.request().method() === 'POST') {
      const input = r.request().postDataJSON() as DocumentPublicationInput
      expect(input.audience).toBe('msp_internal')
      expect(input.retention).toBe('permanent')
      expect(input.retention_review_on).toBeNull()
      if (++creates === 1) return r.fulfill({ status: 403, json: { detail: 'Publication permission denied.' } })
      const id = input.supersedes_id ? correctionId : publicationId
      const result: DocumentPublicationDetail = { ...legacy, id, title: 'Git setup guide', reason: input.reason, supersedes_id: input.supersedes_id ?? null,
        canonical_markdown: 'Current Git instructions.', sanitized_html: '<p>Current Git instructions.</p>',
        manifest: { format: 'tekdocs-static-publication/v5' } }
      if (input.supersedes_id) records.set(input.supersedes_id, { ...records.get(input.supersedes_id)!, lifecycle_state: 'superseded', superseded_by_id: id })
      records.set(id, result)
      return r.fulfill({ status: 201, json: result })
    }
    if (url.pathname.endsWith('/withdraw')) {
      if (++withdrawals === 1) return r.fulfill({ status: 409, json: { detail: 'Withdrawal could not be recorded.' } })
      const result: DocumentPublicationDetail = { ...records.get(correctionId)!, lifecycle_state: 'withdrawn', control_events: [...legacy.control_events, { ...legacy.control_events[0], id: crypto.randomUUID(), action: 'withdrawn', reason: (r.request().postDataJSON() as { reason: string }).reason }] }
      records.set(correctionId, result)
      return r.fulfill({ json: result })
    }
    if (url.pathname.endsWith('/export')) {
      downloads++
      expect(url.searchParams.get('export_format')).toBe('pdf')
      expect([legacyId, correctionId]).toContain(url.pathname.split('/').at(-2))
      return r.continue({ url: pdfUrl })
    }
    const id = url.pathname.split('/').at(-1)!
    if (records.has(id)) return r.fulfill({ json: records.get(id) })
    if (id === documentId) return r.fulfill({ json: source() })
    return r.fulfill({ json: { results: [source()], count: 1, page: 1, page_size: 25, has_more: false } })
  })
  page.on('dialog', dialog => void dialog.accept())
  return { records, creates: () => creates, downloads: () => downloads }
}

for (const width of [320, 1440]) {
  test(`promoted document publication workflow at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 900 })
    const state = await setup(page, baseURL!)
    await page.goto(path)
    await page.getByRole('button', { name: /^Git setup guide Guide/ }).click()
    await expect(page.getByText('Current Git instructions.', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Publish document', exact: true }).click()
    const form = page.locator('.publication-form')
    await expect(form.getByRole('combobox', { name: 'Who can see it?' })).toBeDisabled()
    await expect(form.getByRole('combobox', { name: 'How long should it be kept?' })).toBeDisabled()
    await form.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Current internal release')
    await form.getByRole('button', { name: 'Publish', exact: true }).click()
    await expect(page.getByRole('alert')).toHaveText('Your account is not authorized to change documentation in this workspace.')
    await expect(form.getByRole('textbox')).toHaveValue('Current internal release')
    await form.getByRole('button', { name: 'Publish', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('Published version created')
    expect(state.creates()).toBe(2)
    const viewer = page.locator('.static-publication')
    await expect(viewer.getByText('Current Git instructions.', { exact: true })).toBeVisible()
    await viewer.getByRole('button', { name: 'Publish correction', exact: true }).click()
    await form.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Correct the internal instructions')
    await form.getByRole('button', { name: 'Publish correction', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('Correction published')
    expect(state.records.get(correctionId)?.supersedes_id).toBe(publicationId)
    await viewer.getByRole('button', { name: 'Withdraw publication' }).click()
    await viewer.getByRole('textbox', { name: 'Decision reason' }).fill('Stop distributing this correction')
    await viewer.getByRole('button', { name: 'Withdraw', exact: true }).click()
    await expect(page.getByRole('alert')).toHaveText('The documentation request was not completed.')
    await expect(viewer.getByRole('textbox', { name: 'Decision reason' })).toHaveValue('Stop distributing this correction')
    await viewer.getByRole('button', { name: 'Withdraw', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('Published version withdrawn')
    await expect(viewer.getByRole('button', { name: 'Withdraw publication' })).toHaveCount(0)
    await viewer.getByRole('button', { name: 'History', exact: true }).click()
    await expect(viewer.getByText('Stop distributing this correction', { exact: true })).toBeVisible()
    await viewer.getByRole('button', { name: 'Downloads', exact: true }).click()
    const downloadPromise = page.waitForEvent('download')
    await viewer.getByRole('link', { name: 'Download PDF', exact: true }).click()
    expect((await downloadPromise).suggestedFilename()).toBe('retained-snapshot.pdf')
    expect(state.downloads()).toBe(1)
    expect((await new AxeBuilder({ page }).include('.static-publication').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    await page.goto(`${path}?document=${documentId}&document_view=publications`)
    const history = page.getByRole('region', { name: 'Publication history' })
    await expect(history.getByRole('heading', { name: 'Publication history' })).toBeFocused()
    expect((await new AxeBuilder({ page }).include('[aria-labelledby="document-publications-heading"]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    await history.getByRole('button', { name: 'Close publication history' }).click()
    await expect(page.getByRole('button', { name: 'Publication history', exact: true })).toBeFocused()
    await page.getByRole('button', { name: 'Publication history', exact: true }).press('Enter')
    await history.getByRole('button', { name: /^Retained setup guide/ }).click()
    await expect(viewer.getByText('Original signed instructions.', { exact: true })).toBeVisible()
    await viewer.getByRole('button', { name: 'Downloads', exact: true }).click()
    await expect(viewer.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', new RegExp(`/publications/${legacyId}/export\\?export_format=pdf$`))
    const legacyDownload = page.waitForEvent('download')
    await viewer.getByRole('link', { name: 'Download PDF' }).click()
    expect((await legacyDownload).suggestedFilename()).toBe('retained-snapshot.pdf')
    expect(state.downloads()).toBe(2)
    expect(state.records.get(legacyId)).toEqual(legacy)
  })
}

test('unsupported Git content remains blocked and the publication draft can be retried', async ({ page, baseURL }) => {
  const state = await setup(page, baseURL!, { blocked: true, noHistory: true })
  await page.goto(`${path}?document=${documentId}&document_view=publications`)
  await expect(page.getByText('No published versions yet.')).toBeVisible()
  await page.getByRole('button', { name: 'Publish document', exact: true }).click()
  const form = page.locator('.publication-form')
  await form.getByRole('textbox').fill('Keep this draft')
  await expect(form.getByText('Git content is not ready.')).toBeVisible()
  await expect(form.getByRole('button', { name: 'Publish', exact: true })).toBeDisabled()
  await page.route('**/preflight?**', r => r.fulfill({ status: 503, json: { detail: 'Unavailable' } }))
  await form.getByRole('button', { name: 'Retry publication check' }).click()
  await expect(form.getByRole('alert')).toBeVisible()
  await expect(form.getByRole('textbox')).toHaveValue('Keep this draft')
  await expect(form.getByRole('button', { name: 'Publish', exact: true })).toBeDisabled()
  expect(state.creates()).toBe(0)
})

test('an unavailable Git reader blocks publishing while retained history stays readable', async ({ page, baseURL }) => {
  await setup(page, baseURL!, { unavailable: true })
  await page.goto(`${path}?document=${documentId}`)
  await expect(page.getByText(/Git-backed content is unavailable/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Publish document', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Publication history', exact: true }).click()
  await page.getByRole('region', { name: 'Publication history' }).getByRole('button', { name: /^Retained setup guide/ }).click()
  await expect(page.getByText('Original signed instructions.', { exact: true })).toBeVisible()
})
