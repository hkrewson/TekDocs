import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`current Git keys recover from a failed report at ${width}px`, async ({ page, baseURL }) => {
    const documentId = crypto.randomUUID(), contentId = crypto.randomUUID(), target = crypto.randomUUID()
    const endpoint = `/api/v1/documents/${documentId}`
    let reports = 0, writes = 0
    const record = {
      id: documentId, content_id: contentId, title: 'Operations guide', category: 'guide',
      owner_kind: 'msp', owner_organization_id: null, owner_organization_name: null,
      content_authority: 'repository', is_reference: false, is_template: false, library_visible: false,
      markdown: '', resolved_markdown: '', placements: [], placement_count: 1,
      attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [],
      publications: [], publication_count: 0, created_at: '2026-10-01T12:00:00Z', updated_at: '2026-10-31T12:00:00Z',
    }
    await page.setViewportSize({ width, height: 900 })
    await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL! }])
    await page.route('**/api/v1/bootstrap/status', r => r.fulfill({ json: { bootstrap_required: false } }))
    await page.route('**/_allauth/browser/v1/auth/session', r => r.fulfill({ json: { meta: { is_authenticated: true } } }))
    await page.route('**/api/v1/auth/context', r => r.fulfill({ json: {
      user: { id: crypto.randomUUID(), email: 'reader@example.invalid', display_name: 'Operations reader' },
      tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner', permissions: ['documents.view', 'documents.edit'],
    } }))
    await page.route(`**/api/v1/workspaces/msp/content-graph/documents/${contentId}**`, r => r.fulfill({ json: {
      id: contentId, kind: 'document', title: record.title, indexed_commit: 'b'.repeat(40),
      markdown: 'Visit <tekdocs://key/subject.code>.', sanitized_html: '<p>Visit OPS.</p>', entity_context: [],
    } }))
    await page.route('**/api/v1/documents**', async r => {
      const path = new URL(r.request().url()).pathname
      if (r.request().method() !== 'GET') writes++
      if (path.endsWith('/topic-schemas')) return r.fulfill({ json: { topics: [] } })
      if (path.endsWith('/key-bindings')) return r.fulfill({ json: { results: [{
        id: crypto.randomUUID(), name: 'subject', target_entity_id: target, target_display_name: 'Operations site',
        target_entity_type: 'site', addressable_fields: ['code', 'name'], also_bound_by: [],
      }], count: 1, addressable_entity_types: ['site'] } })
      if (path.endsWith('/keys')) {
        if (++reports === 1) return r.fulfill({ status: 503, json: { detail: 'Report unavailable' } })
        return r.fulfill({ json: { results: [{ expression: 'subject.code', state: 'resolved', label: 'Code', reason: null }], count: 1 } })
      }
      if (path === endpoint) return r.fulfill({ json: record })
      return r.fulfill({ json: { results: [record], count: 1, page: 1, page_size: 25, has_more: false } })
    })
    await page.goto(`/documentation?document=${documentId}`)
    await expect(page.locator('article')).toContainText('Visit OPS.')
    await page.getByRole('button', { name: /^Keys/ }).click()
    await expect(page.getByRole('alert')).toContainText('Keys could not be loaded')
    await expect(page.locator('article')).toContainText('Visit OPS.')
    await page.getByRole('button', { name: 'Retry keys' }).focus()
    await page.keyboard.press('Enter')
    const panel = page.locator('.document-keys')
    await expect(panel.getByRole('group', { name: 'Keys used in this document' })).toContainText('subject.code')
    await expect(panel.getByRole('group', { name: 'Declared key bindings' })).toContainText('Operations site')
    await expect(panel.getByRole('button', { name: 'Retire subject' })).toHaveCount(0)
    await expect(panel.getByRole('textbox', { name: 'Declare', exact: true })).toHaveCount(0)
    expect((await new AxeBuilder({ page }).include('.document-keys').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    expect(writes).toBe(0)
    await panel.getByRole('button', { name: 'Close keys' }).click()
    await expect(panel).toHaveCount(0)
  })
}
