import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const organizationId = '00000000-0000-4000-8000-000000000082'
const columns = ['name', 'document', 'kind', 'type', 'size', 'added']

async function fixtures(page: Page, organization = false) {
  let preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
  const requests: string[] = []
  const files = Array.from({ length: 31 }, (_, index) => ({
    id: `00000000-0000-4000-9000-${String(index + 1).padStart(12, '0')}`,
    document_id: `00000000-0000-4000-a000-${String(index + 1).padStart(12, '0')}`,
    document_title: `Document ${String(index + 1).padStart(3, '0')}`,
    filename: `File ${String(index + 1).padStart(3, '0')}${index === 30 ? ` ${'LongFilename'.repeat(30)}` : ''}.pdf`,
    kind: index % 5 === 0 ? 'primary' : 'attachment', version: index % 5 === 0 ? 1 : null,
    media_type: 'application/pdf', size: 2048 + index, checksum: 'a'.repeat(64), created_at: `2026-09-${String((index % 25) + 1).padStart(2, '0')}T12:00:00Z`,
  }))
  const selectedFile = files[30]
  const revisionId = '00000000-0000-4000-b000-000000000031'
  const blockId = '00000000-0000-4000-c000-000000000031'
  const selectedDocument = {
    id: selectedFile.document_id, title: selectedFile.document_title, owner_kind: organization ? 'organization' : 'msp', owner_organization_id: organization ? organizationId : null, owner_organization_name: organization ? 'Regional Technology Group' : null,
    is_reference: false, category: 'guide', is_template: false, library_visible: false, template_enrollment_id: null, template_applied_revision_id: null, template_source_id: null,
    collection: 'Operations', tags: ['acceptance'], owner_id: null, owner_name: null, review_due_on: null, review_state: 'unreviewed', review_requested_by_id: null, review_requested_by_name: null,
    review_requested_at: null, reviewer_id: null, reviewer_name: null, review_decided_at: null, last_reviewed_by_id: null, last_reviewed_by_name: null, last_reviewed_at: null, review_note: '', health_status: 'current',
    attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [], publications: [], publication_count: 0, markdown: '# File-linked document', block_id: blockId,
    current_revision_id: revisionId, revision_number: 1, checksum: 'abc', resolved_markdown: '# File-linked document', placements: [{ id: '00000000-0000-4000-d000-000000000031', block_id: blockId, block_name: 'File-linked document', block_kind: 'rich_text', parent_id: null, position: 0, depth: 0, resolution_mode: 'live', audience_profile: 'shared', pinned_revision_id: null, resolved_revision_id: revisionId, resolved_revision_number: 1, resolved_checksum: 'abc', resolved_markdown: '# File-linked document', resolved_html: '<h1>File-linked document</h1>', is_primary: true }], placement_count: 1,
    created_at: '2026-09-01T12:00:00Z', updated_at: '2026-09-25T12:00:00Z',
  }
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: { user: { id: 'owner', email: 'files@example.invalid', display_name: 'Files owner' }, tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: ['documents.view'], surface: 'msp', organization: null, mfa_enrollment_required: false } }))
  if (organization) await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Regional Technology Group', classifications: ['client'], capabilities: ['overview', 'documentation', 'files'],
    organization: { id: organizationId, name: 'Regional Technology Group', legal_name: '', website: '', classifications: ['client'], access_mode: 'assigned_only', created_at: '2026-09-25T12:00:00Z', updated_at: '2026-09-25T12:00:00Z' },
  } }))
  await page.route('**/collection-preferences/files', (route) => {
    if (route.request().method() === 'PUT') preferences = { ...preferences, ...route.request().postDataJSON() as { columns: string[]; page_size: number } }
    if (route.request().method() === 'DELETE') preferences = { columns, available_columns: columns, default_columns: columns, page_size: 25 }
    return route.fulfill({ json: preferences })
  })
  await page.route('**/api/v1/documents/topic-schemas', (route) => route.fulfill({ json: { topics: [] } }))
  await page.route('**/api/v1/documents**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith(`/${selectedDocument.id}`)) return route.fulfill({ json: selectedDocument })
    return route.fulfill({ json: { results: [selectedDocument], count: 1, page: 1, page_size: 25, has_more: false } })
  })
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/documents**`, (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith(`/${selectedDocument.id}`)) return route.fulfill({ json: selectedDocument })
    return route.fulfill({ json: { results: [selectedDocument], count: 1, page: 1, page_size: 25, has_more: false } })
  })
  await page.route('**/documents/files?*', (route) => {
    requests.push(route.request().url())
    const query = new URL(route.request().url()).searchParams
    const pageNumber = Number(query.get('page') ?? 1), pageSize = Number(query.get('page_size') ?? 25)
    let found = files.filter((file) => `${file.filename} ${file.document_title} ${file.media_type}`.toLowerCase().includes((query.get('q') ?? '').toLowerCase()))
    if (query.get('kind')) found = found.filter((file) => file.kind === query.get('kind'))
    if (query.get('ordering')?.startsWith('-')) found = [...found].reverse()
    return route.fulfill({ json: { results: found.slice((pageNumber - 1) * pageSize, pageNumber * pageSize), count: found.length, page: pageNumber, page_size: pageSize, has_more: pageNumber * pageSize < found.length } })
  })
  return { files, requests, selectedDocument }
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`Files collection fits ${width}px and searches the complete workspace`, async ({ page }) => {
    const { files } = await fixtures(page)
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/files')
    await expect(page.getByText('31 files', { exact: true })).toBeVisible()
    await expect(page.getByText(files[30].filename, { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect((await new AxeBuilder({ page }).include('.content-section').analyze()).violations).toEqual([])
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page.getByText('File 006.pdf', { exact: true })).toBeVisible()
    await page.getByRole('searchbox', { name: 'Search files' }).fill('File 031')
    await page.locator('.collection-search').getByRole('button', { name: 'Search', exact: true }).click()
    await expect(page.getByText(files[30].filename, { exact: true })).toBeVisible()
    await expect(page).not.toHaveURL(/page=2/)
    const documentLink = page.getByRole('link', { name: 'Document 031' })
    await expect(documentLink).toHaveAttribute('href', '/documentation?document=00000000-0000-4000-a000-000000000031')
    await documentLink.click()
    await expect(page).toHaveURL('/documentation?document=00000000-0000-4000-a000-000000000031')
    await expect(page.getByRole('region', { name: 'Document 031', exact: true })).toBeVisible()
    await page.goBack()
    await expect(page.getByRole('searchbox', { name: 'Search files' })).toHaveValue('File 031')
    await expect(page.getByText(files[30].filename, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Columns', exact: true }).click()
    await expect(page.getByRole('checkbox', { name: 'File name', exact: true })).toBeDisabled()
    await page.getByRole('checkbox', { name: 'File type', exact: true }).uncheck()
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Columns', exact: true })).toHaveAttribute('aria-expanded', 'false')
    if (width >= 768) await expect(page.getByRole('columnheader', { name: 'File type' })).toHaveCount(0)
    await page.reload()
    await expect(page.getByText(files[30].filename, { exact: true })).toBeVisible()
    if (width >= 768) await expect(page.getByRole('columnheader', { name: 'File type' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

for (const width of [390, 1280]) {
  test(`Organization Files uses its own collection at ${width}px`, async ({ page }) => {
    const { requests } = await fixtures(page, true)
    await page.setViewportSize({ width, height: 600 })
    const path = `/workspaces/organizations/${organizationId}/files`
    await page.goto(path)
    await expect(page.getByText('31 files', { exact: true })).toBeVisible()
    expect(requests.some((url) => url.includes(`/workspaces/organizations/${organizationId}/documents/files?`))).toBe(true)
    expect(requests.some((url) => url.includes('/api/v1/documents/files?'))).toBe(false)
    const documentLink = page.getByRole('link', { name: 'Document 031' })
    await expect(documentLink).toHaveAttribute('href', `/workspaces/organizations/${organizationId}/documentation?document=00000000-0000-4000-a000-000000000031`)
    await documentLink.click()
    await expect(page).toHaveURL(`/workspaces/organizations/${organizationId}/documentation?document=00000000-0000-4000-a000-000000000031`)
    await expect(page.getByRole('region', { name: 'Document 031', exact: true })).toBeVisible()
    await page.goBack()
    await expect(page.getByText('31 files', { exact: true })).toBeVisible()
    expect((await new AxeBuilder({ page }).include('.content-section').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
