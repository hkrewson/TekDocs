import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

for (const width of [320, 390, 768, 1440]) {
  test(`saved Git editor fits ${width}px with files and source metadata`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const id = crypto.randomUUID()
    const organizationId = crypto.randomUUID()
    const workspace = `/api/v1/workspaces/organizations/${organizationId}`
    const commit = 'a'.repeat(40)
    const source = {
      content_id: id, title: 'Device setup', kind: 'document', path: 'docs/device-setup.md',
      markdown: '# Setup\n\nInstructions.\n', source: `---\nid: ${id}\n---\n# Setup\n`,
      source_blob: 'b'.repeat(40), accepted_commit: commit, indexed_commit: commit,
    }
    await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
    await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
    await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
      user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Owner' },
      tenant: { id: crypto.randomUUID(), name: 'Example MSP' }, role: 'owner',
      permissions: ['documents.view', 'documents.edit'],
    } }))
    await page.route('**/api/v1/notifications*', (route) => route.fulfill({ json: { results: [], count: 0 } }))
    await page.route('**/api/v1/documents**', (route) => route.fulfill({ json: { results: [], topics: [], count: 0 } }))
    await page.route(`**${workspace}`, (route) => route.fulfill({ json: {
      kind: 'organization', id: organizationId, name: 'Example client',
      classifications: ['client'], capabilities: ['overview', 'documentation'], organization: null,
    } }))
    await page.route(`**${workspace}/documents**`, (route) => route.fulfill({ json: { results: [], count: 0 } }))
    await page.route(`**${workspace}/content-graph/**`, (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith(`/authoring/${id}`)) return route.fulfill({ json: source })
      if (path.endsWith('/attachments')) return route.fulfill({ json: {
        results: [{ id: crypto.randomUUID(), filename: 'live-git-setup.txt', size: 26, linked_current: true, can_archive: false }],
        count: 1, has_more: false, page: 1, page_size: 25,
      } })
      if (path.endsWith('/documents')) return route.fulfill({ json: {
        results: [{ id, title: source.title, kind: source.kind, path: source.path }],
        count: 1, has_more: false, accepted_commit: commit, indexed_commit: commit,
      } })
      return route.fulfill({ json: { results: [], count: 0, has_more: false } })
    })
    await page.goto(`/workspaces/organizations/${organizationId}/documentation?repository=${id}`)
    await page.getByRole('tab', { name: 'Markdown', exact: true }).click()
    await expect(page.getByRole('textbox', { name: 'Markdown source', exact: true })).toHaveValue(source.markdown)
    await page.getByRole('tab', { name: 'Editor', exact: true }).click()
    await expect(page.getByLabel('Repository path', { exact: true })).toBeHidden()
    await expect(page.getByText('live-git-setup.txt', { exact: true })).toBeHidden()
    const repositoryExports = page.getByText('More', { exact: true })
    await expect(page.getByRole('button', { name: 'Download Markdown source snapshot' })).toBeHidden()
    await repositoryExports.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('button', { name: 'Download Markdown source snapshot' })).toBeVisible()
    await page.keyboard.press('Enter')
    const fileExports = page.getByText('File exports', { exact: true })
    await expect(page.getByRole('button', { name: 'Download saved HTML' })).toBeHidden()
    await fileExports.click()
    const htmlExport = page.getByRole('button', { name: 'Download saved HTML' })
    await expect(htmlExport).toBeVisible()
    const menuOverflow = await page.evaluate(() => [...document.querySelectorAll('.repository-export-menu[open] *')]
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
      .map((element) => ({ tag: element.tagName, className: element.className })))
    expect(menuOverflow).toEqual([])
    await fileExports.click()
    await page.getByText('Source details', { exact: true }).click()
    await expect(page.getByLabel('Repository path', { exact: true })).toBeVisible()
    await page.getByText('Files (1)', { exact: true }).click()
    await expect(page.getByRole('listitem').filter({ hasText: 'live-git-setup.txt' })).toBeVisible()
    const overflow = await page.evaluate(() => [...document.querySelectorAll('.repository-authoring *')]
      .filter((element) => !element.classList.contains('sr-only')
        && !element.closest('.editor-format-controls')
        && !element.closest('.mode-tabs')
        && element.getBoundingClientRect().right > innerWidth + 1)
      .map((element) => ({ tag: element.tagName, className: element.className })))
    expect(overflow).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  })
}
