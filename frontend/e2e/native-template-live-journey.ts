import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'
import type { RepositorySource } from '../src/documentation/repositoryApi'

export type NativeTemplateFixture = { organization_id: string; source_id: string; fragments: Record<'copy' | 'live' | 'pinned', { id: string; title: string }> }
const modes = ['copy', 'live', 'pinned'] as const
const templateRegion = (page: Page) => page.getByRole('region', { name: 'Template settings and updates', exact: true })
async function edit(page: Page, path: string, markdown: string) {
  await page.goto(path)
  await page.getByLabel('Markdown body', { exact: true }).fill(markdown)
  const saved = page.waitForResponse(response => response.url().endsWith('/content-graph/authoring') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  expect((await saved).status()).toBe(200)
  await expect(page.getByRole('status').filter({ hasText: /^Saved as one accepted Git commit\.$/ })).toHaveText('Saved as one accepted Git commit.')
}
async function mutation(page: Page, name: string, status = 200) {
  const saved = page.waitForResponse(response => response.url().endsWith('/template') && response.request().method() === 'POST')
  await templateRegion(page).getByRole('button', { name, exact: true }).click()
  expect((await saved).status()).toBe(status)
}
export async function rehearseNativeTemplates(page: Page, fixture: NativeTemplateFixture, foreignOrganizationId: string) {
  const clientPath = `/workspaces/organizations/${fixture.organization_id}/documentation`
  const clientApi = `/api/v1/workspaces/organizations/${fixture.organization_id}/content-graph`
  await page.goto(`/documentation?repository=${fixture.source_id}`)
  await page.getByRole('button', { name: 'Template settings and updates', exact: true }).click()
  await page.getByLabel('Use as a template', { exact: true }).check()
  await page.getByLabel('Offer in the client template library', { exact: true }).check()
  for (const mode of modes) await templateRegion(page).getByLabel(fixture.fragments[mode].title, { exact: true }).check()
  await mutation(page, 'Save template settings')
  await page.goto(clientPath)
  await page.getByRole('button', { name: 'Templates from your MSP', exact: true }).click()
  const library = page.getByRole('region', { name: 'Git-backed templates', exact: true })
  await library.getByLabel('Search Git-backed templates', { exact: true }).fill('Native browser template')
  await library.getByRole('button', { name: 'Use Git-backed template', exact: true }).click()
  await library.getByLabel('Document title', { exact: true }).fill('Native browser enrolled document')
  for (const mode of modes) await library.getByLabel(`Behavior for ${fixture.fragments[mode].title}`, { exact: true }).selectOption(mode)
  const created = page.waitForResponse(response => response.url().endsWith('/template-enrollments') && response.request().method() === 'POST')
  const enrolled = created.then(async response => ({ response, document: await response.json() as RepositorySource }))
  const sourceRead = page.waitForResponse(async candidate => {
    const pathname = new URL(candidate.url()).pathname
    if (candidate.request().method() !== 'GET' || !pathname.startsWith(`${clientApi}/authoring/`)) return false
    return pathname === `${clientApi}/authoring/${(await enrolled).document.content_id}`
  })
  await library.getByRole('button', { name: 'Create Git-backed document', exact: true }).click()
  const { response, document: enrolledDocument } = await enrolled
  expect(response.status()).toBe(201)
  const documentPath = `${clientPath}?repository=${enrolledDocument.content_id}`
  await expect(page).toHaveURL(new RegExp(`[?&]repository=${enrolledDocument.content_id}(?:&|$)`))
  const openedSource = await sourceRead
  expect(openedSource.status()).toBe(200)
  expect((await openedSource.json() as RepositorySource).content_id).toBe(enrolledDocument.content_id)
  await expect(page.getByLabel('Markdown body', { exact: true })).toHaveValue('Native template introduction.\n')
  await edit(page, documentPath, 'Native enrolled local introduction.\n')
  const listing = await page.request.get(`${clientApi}/documents?q=${encodeURIComponent(fixture.fragments.copy.title)}`)
  expect(listing.status()).toBe(200)
  const copies = await listing.json() as { results: { id: string; title: string; kind: string }[] }
  const local = copies.results.find(row => row.kind === 'fragment' && row.title === fixture.fragments.copy.title)
  expect(local).toBeDefined()
  await edit(page, `${clientPath}?repository=${local!.id}`, 'Native copied local edit.\n')
  for (const mode of modes) await edit(page, `/documentation?repository=${fixture.fragments[mode].id}`, `Native ${mode} updated.\n`)
  async function rendered() {
    const result = await page.request.get(`${clientApi}/documents/${enrolledDocument.content_id}`)
    expect(result.status()).toBe(200)
    return (await result.json() as { sanitized_html: string }).sanitized_html
  }
  const current = await rendered()
  expect(current).toContain('Native enrolled local introduction.')
  expect(current).toContain('Native copied local edit.')
  expect(current).toContain('Native live updated.')
  expect(current).toContain('Native pinned original.')
  expect(current).not.toContain('Native copy updated.')
  await page.goto(documentPath)
  await page.getByRole('button', { name: 'Template settings and updates', exact: true }).click()
  await templateRegion(page).getByLabel(`Behavior for ${fixture.fragments.pinned.title}`, { exact: true }).selectOption('pinned')
  await templateRegion(page).getByLabel(`Behavior for ${fixture.fragments.copy.title}`, { exact: true }).selectOption('keep')
  const editor = await page.context().newPage()
  try { await edit(editor, `/documentation?repository=${fixture.fragments.pinned.id}`, 'Native pinned newest.\n') } finally { await editor.close() }
  await mutation(page, 'Apply reviewed update', 409)
  await expect(templateRegion(page).getByRole('alert')).toContainText('Template or client document changed; review it again')
  await templateRegion(page).getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Discard changes', exact: true }).click()
  await page.getByRole('button', { name: 'Template settings and updates', exact: true }).click()
  await templateRegion(page).getByLabel(`Behavior for ${fixture.fragments.pinned.title}`, { exact: true }).selectOption('pinned')
  await templateRegion(page).getByLabel(`Behavior for ${fixture.fragments.copy.title}`, { exact: true }).selectOption('keep')
  await mutation(page, 'Apply reviewed update')
  expect(await rendered()).toContain('Native pinned newest.')
  expect(await rendered()).toContain('Native copied local edit.')
  await page.getByRole('button', { name: 'Template settings and updates', exact: true }).click()
  await mutation(page, `Make ${fixture.fragments.live.title} a local copy`)
  await edit(page, `/documentation?repository=${fixture.fragments.live.id}`, 'Native live after detach.\n')
  expect(await rendered()).toContain('Native live updated.')
  expect(await rendered()).not.toContain('Native live after detach.')
  expect((await page.request.get(`/api/v1/workspaces/organizations/${foreignOrganizationId}/content-graph/authoring/${enrolledDocument.content_id}/template`)).status()).toBe(404)
  await page.goto(documentPath)
  await page.getByRole('button', { name: 'Template settings and updates', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(templateRegion(page).getByRole('button', { name: `Make ${fixture.fragments.live.title} a local copy`, exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Markdown body', { exact: true })).toHaveValue('Native enrolled local introduction.\n')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.setViewportSize({ width: 1280, height: 900 })
  return { id: enrolledDocument.content_id, path: documentPath }
}
