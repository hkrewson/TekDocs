import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'
import type { RepositorySource } from '../src/documentation/repositoryApi'

async function saveToGit(page: Page, endpoint: string): Promise<RepositorySource> {
  const responsePromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname === endpoint && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  const saved = await response.json() as RepositorySource
  expect(saved.accepted_commit).toMatch(/^[a-f0-9]{40}(?:[a-f0-9]{24})?$/)
  expect(saved.indexed_commit).toBe(saved.accepted_commit)
  await expect(page.getByRole('status')).toHaveText('Saved as one accepted Git commit.')
  return saved
}

/** Use the real session, HTTP routes, PostgreSQL projection, and managed Git. */
export async function rehearseRepositoryContent(page: Page, organizationId: string) {
  const documentation = `/workspaces/organizations/${organizationId}/documentation`
  const graph = `/api/v1/workspaces/organizations/${organizationId}/content-graph`
  const endpoint = `${graph}/authoring`
  const initialBody = '# Device setup\n\nInitial Git instructions.\n'
  const currentBody = '# Device setup\n\nReviewed enrollment instructions.\n'
  const proposedBody = '# Device setup\n\nReviewed repair instructions.\n'

  await page.goto(documentation)
  await page.getByRole('button', { name: 'Repository content', exact: true }).click()
  await page.getByRole('button', { name: 'New Markdown file' }).click()
  await page.getByLabel('Title', { exact: true }).fill('Live Git setup guide')
  await page.getByLabel('Repository path', { exact: true }).fill('docs/live-git-setup.md')
  await page.getByLabel('Markdown body').fill(initialBody)
  const created = await saveToGit(page, endpoint)
  expect(created.markdown).toBe(initialBody)
  const directLink = `${documentation}?repository=${created.content_id}`

  // Reopening must read the saved Git file, including after a browser reload.
  await page.goto(directLink)
  await expect(page.getByLabel('Markdown body')).toHaveValue(initialBody)
  await page.reload()
  await expect(page.getByLabel('Markdown body')).toHaveValue(initialBody)

  // Two tabs start from the same revision. The second save must compare versions
  // and retain its draft until the user explicitly rebases and saves again.
  const secondPage = await page.context().newPage()
  try {
    await secondPage.goto(directLink)
    await expect(secondPage.getByLabel('Markdown body')).toHaveValue(initialBody)
    await page.getByLabel('Markdown body').fill(currentBody)
    const current = await saveToGit(page, endpoint)
    expect(current.accepted_commit).not.toBe(created.accepted_commit)
    await secondPage.getByLabel('Markdown body').fill(proposedBody)
    const conflictPromise = secondPage.waitForResponse((response) =>
      new URL(response.url()).pathname === endpoint && response.request().method() === 'POST')
    await secondPage.getByRole('button', { name: 'Save to Git', exact: true }).click()
    expect((await conflictPromise).status()).toBe(409)
    const conflict = secondPage.getByRole('alert')
    await expect(conflict).toContainText('The repository changed.')
    await expect(conflict).toContainText(initialBody.trim())
    await expect(conflict).toContainText(currentBody.trim())
    await expect(conflict).toContainText(proposedBody.trim())
    await expect(secondPage.getByLabel('Markdown body')).toHaveValue(proposedBody)
    await secondPage.getByRole('button', { name: 'Use current as base and review my draft' }).click()
    await expect(secondPage.getByRole('status')).toHaveText('Your draft is retained with the latest version as its base. Review it before saving.')
    await expect(secondPage.getByLabel('Markdown body')).toHaveValue(proposedBody)
    const rebased = await saveToGit(secondPage, endpoint)
    expect(rebased.accepted_commit).not.toBe(current.accepted_commit)
  } finally {
    await secondPage.close()
  }

  await page.goto(directLink)
  await expect(page.getByLabel('Markdown body')).toHaveValue(proposedBody)
  await page.getByLabel('Attach file to saved document').setInputFiles({
    name: 'live-git-setup.txt', mimeType: 'text/plain', buffer: Buffer.from('Live device setup details.'),
  })
  await expect(page.getByRole('status')).toContainText('Save to Git to keep its link')
  const linkedBody = await page.getByLabel('Markdown body').inputValue()
  expect(linkedBody).toMatch(/\[live-git-setup\.txt\]\(tekdocs:\/\/attachment\/[0-9a-f-]{36}\)/)
  const beforeSavingLink = await page.request.get(`${endpoint}/${created.content_id}`)
  expect(beforeSavingLink.status()).toBe(200)
  expect((await beforeSavingLink.json() as RepositorySource).markdown).toBe(proposedBody)
  const saved = await saveToGit(page, endpoint)
  expect(saved.markdown).toBe(linkedBody)
  await page.reload()
  await expect(page.getByLabel('Markdown body')).toHaveValue(linkedBody)
  await expect(page.getByRole('region', { name: 'Files for this document' })).toContainText('Linked in current Markdown')

  // A saved export excludes a later unsaved draft and names its actual Git commit.
  await page.getByLabel('Markdown body').fill(`${linkedBody}\nUnsaved browser-only text.\n`)
  const exportPromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname === `${graph}/documents/${created.content_id}/export/html`)
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download saved HTML' }).click()
  const exported = await exportPromise
  expect(exported.status()).toBe(200)
  expect(exported.headers()['x-tekdocs-repository-commit']).toBe(saved.accepted_commit)
  expect(exported.headers()['cache-control']).toBe('private, no-store')
  const html = await exported.text()
  expect(html).toContain('Reviewed repair instructions.')
  expect(html).not.toContain('Unsaved browser-only text.')
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('repository-document.html')
  await download.delete()
  await page.getByLabel('Markdown body').fill(linkedBody)

  // The same authenticated owner cannot resolve an organization document in MSP scope.
  const foreignScope = await page.request.get(`/api/v1/workspaces/msp/content-graph/authoring/${created.content_id}`)
  expect(foreignScope.status()).toBe(404)

  const viewport = page.viewportSize()
  try {
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.getByLabel('Markdown body')).toBeVisible()
    // Wait for the shell's 150ms desktop-to-mobile margin transition.
    await expect(page.locator('.app-body')).toHaveCSS('margin-left', '0px')
    const size = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }))
    expect(size.scroll).toBeLessThanOrEqual(size.width + 1)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  } finally {
    if (viewport) await page.setViewportSize(viewport)
  }
}
