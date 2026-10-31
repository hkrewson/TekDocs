import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const organization = crypto.randomUUID(), source = crypto.randomUUID(), document = crypto.randomUUID()
const content = crypto.randomUUID(), enrollment = crypto.randomUUID(), revision = crypto.randomUUID()
const placement = crypto.randomUUID(), block = crypto.randomUUID()
const endpoint = `/api/v1/workspaces/organizations/${organization}/documents`
const location = `/workspaces/organizations/${organization}/documentation`

async function setup(page: Page, baseURL: string) {
  let created = false, applied = false, detached = false, sourceChanged = false, writes = 0, detaches = 0
  const record = () => ({
    id: document, content_id: content, title: 'Client enrollment guide', category: 'guide',
    owner_kind: 'organization', owner_organization_id: organization, owner_organization_name: 'Example client',
    content_authority: 'repository', is_reference: false, is_template: false, library_visible: false,
    template_enrollment_id: enrollment, template_applied_revision_id: revision, template_source_id: source,
    markdown: '', resolved_markdown: '', placements: [], placement_count: 2,
    attachments: [], attachment_count: 0, primary_file: null, primary_file_versions: [],
    publications: [], publication_count: 0, created_at: '2026-10-01T12:00:00Z', updated_at: '2026-10-30T12:00:00Z',
  })
  const review = () => ({
    enrollment_id: enrollment, applied_revision_id: revision, current_revision: applied ? 3 : 1,
    available_revision: sourceChanged ? 3 : 2, up_to_date: applied, base_commit: 'b'.repeat(40), composition_digest: 'c'.repeat(64),
    added: applied ? [] : [{ source_block_id: block, name: 'Additional checklist' }],
    changed: [], removed: [], conflicts: [],
    reused_sections: detached ? [] : [{ placement_id: placement, title: 'Shared procedure', mode: 'pinned' }],
  })
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', r => r.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', r => r.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', r => r.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'template-editor@example.invalid', display_name: 'Client editor' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'contributor',
    permissions: ['documents.view', 'documents.edit'],
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organization}`, r => r.fulfill({ json: {
    kind: 'organization', id: organization, name: 'Example client', classifications: ['client'], capabilities: ['documentation'], organization: null,
  } }))
  await page.route('**/api/v1/documents/topic-schemas', r => r.fulfill({ json: { topics: [] } }))
  await page.route(`**/api/v1/workspaces/organizations/${organization}/content-graph/documents/${content}`, r => r.fulfill({ json: {
    id: content, kind: 'document', title: 'Client enrollment guide', indexed_commit: 'b'.repeat(40),
    sanitized_html: '<p>Local client introduction.</p><p>Selected template procedure.</p>', entity_context: [],
  } }))
  await page.route(`**${endpoint}**`, async r => {
    const url = new URL(r.request().url())
    if (url.pathname.endsWith('/template-library')) return r.fulfill({ json: { results: [{
      id: source, title: 'Approved Git template', category: 'guide', content_authority: 'repository',
      source_state: 'ready', definition_sha256: 'a'.repeat(64), placement_count: 1,
      placements: [{ id: crypto.randomUUID(), block_id: block, block_name: 'Introduction', is_primary: true, resolved_html: '<p>Template introduction.</p>' }],
    }], count: 1, page: 1, page_size: 25, has_more: false } })
    if (url.pathname.endsWith('/from-template')) {
      expect((r.request().postDataJSON() as { expected_source_sha256: string }).expected_source_sha256).toBe('a'.repeat(64))
      created = true
      return r.fulfill({ status: 201, json: record() })
    }
    if (url.pathname.endsWith('/template-rollouts/preview')) return r.fulfill({ json: review() })
    if (url.pathname.endsWith('/template-rollouts/apply')) {
      writes++
      expect(r.request().postDataJSON()).toMatchObject({
        expected_base: 'b'.repeat(40), expected_composition: 'c'.repeat(64), expected_applied_revision_id: revision,
        expected_available_revision: sourceChanged ? 3 : 2, placement_rules: { [block]: 'live' },
      })
      if (writes === 1) {
        sourceChanged = true
        return r.fulfill({ status: 409, json: { code: 'placement_conflict', detail: 'Template changed after review. Review again.' } })
      }
      applied = true
      return r.fulfill({ json: review() })
    }
    if (url.pathname.endsWith(`/placements/${placement}/detach`)) {
      detaches++
      expect(r.request().postDataJSON()).toMatchObject({
        expected_base: 'b'.repeat(40), expected_composition: 'c'.repeat(64), expected_applied_revision_id: revision,
      })
      if (detaches === 1) return r.fulfill({ status: 403, json: { detail: 'Template change denied.' } })
      detached = true
      return r.fulfill({ json: record() })
    }
    if (url.pathname.endsWith(`/${document}`)) return r.fulfill({ json: record() })
    return r.fulfill({ json: { results: created ? [record()] : [], count: created ? 1 : 0, page: 1, page_size: 25, has_more: false } })
  })
  return { writes: () => writes, detaches: () => detaches }
}

for (const width of [320, 1440]) {
  test(`reviewed Git template creation, updates and detach at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 900 })
    const state = await setup(page, baseURL!)
    await page.goto(location)
    await page.getByRole('button', { name: 'Templates from your MSP' }).click()
    await page.getByRole('button', { name: 'Use template' }).click()
    await expect(page.getByRole('heading', { name: 'Create from Approved Git template' })).toBeFocused()
    await page.getByLabel('Document title', { exact: true }).fill('Client enrollment guide')
    await page.getByRole('button', { name: 'Create document', exact: true }).click()
    await expect(page.getByText('Local client introduction.')).toBeVisible()
    await page.getByRole('button', { name: 'Check template updates' }).click()
    await expect(page.getByRole('heading', { name: 'Template updates', exact: true })).toBeFocused()
    await page.getByRole('combobox', { name: 'Additional checklist', exact: true }).selectOption('live')
    await page.getByRole('button', { name: 'Apply update', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('Template changed after review')
    expect(state.writes()).toBe(1)
    await expect(page.getByRole('combobox', { name: 'Additional checklist', exact: true })).toHaveValue('live')
    await page.getByRole('button', { name: 'Check template updates' }).click()
    await page.getByRole('button', { name: 'Discard changes', exact: true }).click()
    await expect(page.getByText('Your version: 1 · Latest template: 3', { exact: true })).toBeVisible()
    await page.getByRole('combobox', { name: 'Additional checklist', exact: true }).selectOption('live')
    await page.getByRole('button', { name: 'Apply update', exact: true }).click()
    await page.getByRole('button', { name: 'Check template updates' }).click()
    await page.getByRole('button', { name: 'Make Shared procedure a local copy' }).click()
    await expect(page.getByRole('alert')).toContainText('Your account is not authorized to change documentation')
    expect(state.detaches()).toBe(1)
    await page.getByRole('button', { name: 'Make Shared procedure a local copy' }).click()
    await expect(page.getByRole('button', { name: 'Make Shared procedure a local copy' })).toHaveCount(0)
    await expect(page.getByText('Local client introduction.')).toBeVisible()
    expect(await page.evaluate(() => window.document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  })
}
