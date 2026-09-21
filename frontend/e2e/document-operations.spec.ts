import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const organizationId = crypto.randomUUID(), documentId = crypto.randomUUID(), blockId = crypto.randomUUID(), revisionId = crypto.randomUUID()
const placement = { id: crypto.randomUUID(), block_id: blockId, block_name: 'Network guidance', block_kind: 'rich_text', parent_id: null, position: 0, depth: 0, resolution_mode: 'live', audience_profile: 'shared', pinned_revision_id: null, resolved_revision_id: revisionId, resolved_revision_number: 1, resolved_checksum: 'abc', resolved_markdown: 'Reviewed guidance', resolved_html: '<p>Reviewed guidance</p>', is_primary: true }
const record = { id: documentId, title: 'Network baseline', owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null, is_reference: false, category: 'guide', is_template: true, library_visible: true, markdown: 'Reviewed guidance', block_id: blockId, current_revision_id: revisionId, revision_number: 1, checksum: 'abc', resolved_markdown: 'Reviewed guidance', placements: [placement, { ...placement, id: crypto.randomUUID(), block_id: crypto.randomUUID(), block_name: 'Shared instructions', is_primary: false, position: 1 }], placement_count: 2, attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [], publication_count: 0, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
async function setup(page: Page, baseURL: string) {
  const reviewerId = crypto.randomUUID()
  let current = { ...record, is_template: false, owner_organization_id: organizationId, owner_kind: 'organization', owner_id: null as string | null, owner_name: null as string | null, review_due_on: null as string | null, collection: '', tags: [] as string[], review_state: 'unreviewed', health_status: 'unowned', reviewer_id: null as string | null, reviewer_name: null as string | null, review_note: '', review_decided_at: null as string | null }
  let choicesAvailable = false, writes = 0, decisions = 0
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (r) => r.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (r) => r.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (r) => r.fulfill({ json: { user: { id: reviewerId, email: 'reviewer@example.invalid', display_name: 'Alex Rivera' }, tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.edit', 'documents.approve'] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (r) => r.fulfill({ json: { kind: 'organization', id: organizationId, name: 'Example client', classifications: ['client'], capabilities: ['overview', 'documentation'], organization: null } }))
  await page.route('**/api/v1/documents/topic-schemas', (r) => r.fulfill({ json: { topics: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/taxonomies`, (r) => r.fulfill({ json: { results: [], count: 0 } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/documents**`, async (r) => {
    const url = new URL(r.request().url())
    if (url.pathname.endsWith('/operations/choices')) {
      if (!choicesAvailable) return r.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
      return r.fulfill({ json: [{ id: reviewerId, display_name: 'Alex Rivera', can_approve: true }] })
    }
    if (url.pathname.endsWith('/operations')) {
      if (++writes === 1) return r.fulfill({ status: 403, json: { detail: 'Permission denied.' } })
      const input = r.request().postDataJSON() as { owner_id: string; review_due_on: string; collection: string; tags: string[] }
      expect(input).toMatchObject({ owner_id: reviewerId, review_due_on: '2026-12-31', collection: 'Runbooks', tags: ['network'] })
      current = { ...current, ...input, owner_name: 'Alex Rivera', health_status: 'unreviewed' }
      return r.fulfill({ json: current })
    }
    if (url.pathname.endsWith('/reviews')) {
      expect(r.request().postDataJSON()).toEqual({ reviewer_id: reviewerId, note: 'Verify recovery steps' })
      current = { ...current, reviewer_id: reviewerId, reviewer_name: 'Alex Rivera', review_state: 'pending', health_status: 'pending', review_note: 'Verify recovery steps' }
      return r.fulfill({ json: current })
    }
    if (url.pathname.endsWith('/reviews/decision')) {
      if (++decisions === 1) return r.fulfill({ status: 403, json: { detail: 'This review is assigned to another person.' } })
      expect(r.request().postDataJSON()).toEqual({ decision: 'changes_requested', note: 'Add recovery contact' })
      current = { ...current, review_state: 'changes_requested', health_status: 'changes_requested', review_note: 'Add recovery contact', review_decided_at: '2026-09-20T12:00:00Z' }
      return r.fulfill({ json: current })
    }
    if (url.pathname.endsWith(`/${documentId}`)) return r.fulfill({ json: current })
    return r.fulfill({ json: { results: [current], count: 1, page: 1, page_size: 25, has_more: false } })
  })
  return { reviewerId, allowChoices: () => { choicesAvailable = true } }
}
for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`ownership and review at ${width}px`, async ({ page, baseURL }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const { reviewerId, allowChoices } = await setup(page, baseURL!)
    await page.goto(`/workspaces/organizations/${organizationId}/documentation?document=${documentId}`)
    await page.getByRole('button', { name: 'Ownership and review' }).click()
    const panel = page.getByRole('region', { name: 'Ownership and review' })
    await expect(panel.getByRole('alert')).toContainText('could not be loaded')
    await expect(panel.getByRole('combobox', { name: 'Owner', exact: true })).toHaveCount(0)
    allowChoices()
    await panel.getByRole('button', { name: 'Retry' }).click()
    await expect(panel.getByRole('heading', { name: 'Ownership and review' })).toBeFocused()
    await expect(page).toHaveURL(/document_view=operations/)
    await panel.getByRole('combobox', { name: 'Owner', exact: true }).selectOption(reviewerId)
    await panel.getByLabel('Review due').fill('2026-12-31')
    await panel.getByLabel('Collection', { exact: true }).fill('Runbooks')
    await panel.getByLabel('Tags', { exact: true }).fill('network')
    await panel.getByRole('button', { name: 'Save ownership and organization' }).click()
    await expect(panel.getByRole('alert')).toContainText('Your unsaved choices are preserved.')
    await page.getByRole('button', { name: 'Document settings' }).click()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(panel.getByRole('combobox', { name: 'Owner', exact: true })).toHaveValue(reviewerId)
    await expect(page).toHaveURL(/document_view=operations/)
    await panel.getByRole('button', { name: 'Save ownership and organization' }).click()
    await expect(panel.getByRole('status')).toHaveText('Ownership and content organization saved.')
    await panel.getByRole('combobox', { name: 'Reviewer', exact: true }).selectOption(reviewerId)
    await panel.getByRole('textbox', { name: 'Review note', exact: true }).fill('Verify recovery steps')
    await panel.getByRole('button', { name: 'Send for review' }).click()
    await expect(panel.getByRole('status')).toHaveText('Review requested.')
    await panel.getByRole('combobox', { name: 'Decision', exact: true }).selectOption('changes_requested')
    await panel.getByLabel('Decision note').fill('Add recovery contact')
    await panel.getByRole('button', { name: 'Record decision' }).click()
    await expect(panel.getByRole('alert')).toContainText('Your account is not authorized to change documentation in this workspace.')
    await expect(panel.getByLabel('Decision note')).toHaveValue('Add recovery contact')
    expect((await new AxeBuilder({ page }).include('.document-operations').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    await panel.getByRole('heading', { name: 'Ownership and review' }).focus()
    if (testInfo.project.name === 'chromium' && [320, 1440].includes(width)) await page.screenshot({ path: `../artifacts/document-operations-${width}.png`, fullPage: true })
    await panel.getByRole('button', { name: 'Record decision' }).click()
    await expect(panel.getByRole('status')).toHaveText('Changes requested.')
    await expect(page).toHaveURL(/document_view=operations/)
    await page.reload()
    await expect(panel.getByRole('heading', { name: 'Ownership and review' })).toBeVisible()
    await expect(panel.getByText('Add recovery contact', { exact: true })).toBeVisible()
    await expect(panel.getByRole('combobox', { name: 'Owner', exact: true })).toHaveValue(reviewerId)
    await panel.getByRole('textbox', { name: 'Review note', exact: true }).fill('Unsaved follow-up')
    await panel.getByRole('button', { name: 'Back to document' }).click()
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('button', { name: 'Ownership and review' })).toBeFocused()
  })
}

test('browser Back protects an unfinished review request', async ({ page, baseURL }) => {
  const { allowChoices } = await setup(page, baseURL!)
  await page.goto(`/workspaces/organizations/${organizationId}/documentation`)
  await page.getByRole('button', { name: /Network baseline/ }).click()
  await page.getByRole('button', { name: 'Ownership and review' }).click()
  const retry = page.getByRole('button', { name: 'Retry' })
  await expect(retry).toBeVisible()
  allowChoices()
  await retry.click()
  await page.getByRole('textbox', { name: 'Review note', exact: true }).fill('Keep this request')
  await page.evaluate(() => history.back())
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(page.getByRole('textbox', { name: 'Review note', exact: true })).toHaveValue('Keep this request')
  await page.evaluate(() => history.back())
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(page.getByRole('button', { name: 'Ownership and review' })).toBeVisible()
  await expect.poll(() => new URL(page.url()).searchParams.get('document_view')).toBeNull()
  await expect(page.getByRole('region', { name: 'Ownership and review' })).toHaveCount(0)
  await page.goBack()
  await expect.poll(() => new URL(page.url()).searchParams.get('document')).toBeNull()
  await expect(page.getByRole('button', { name: /Network baseline/ })).toBeVisible()
})

test('reload opens the selected document while retaining template-library URL state', async ({ page, baseURL }) => {
  await setup(page, baseURL!)
  await page.goto(`/workspaces/organizations/${organizationId}/documentation?doc_library=templates&template_q=Network&document=${documentId}`)
  await expect(page.locator('.document-content-item')).toHaveCount(2)
  await page.reload()
  await expect(page.locator('.document-content-item')).toHaveCount(2)
})
