import { rehearseNativeTemplates, type NativeTemplateFixture } from './native-template-live-journey'
import AxeBuilder from '@axe-core/playwright'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import type { DocumentPrimaryFile, DocumentPublicationDetail, RepositoryDocumentRead } from '../src/documentation/api'
import { attachPublicationDiagnostics } from './publicationDiagnostics.ts'
import { rehearseRepositoryContent } from './repository-live-journey'

type TemplateState = { organization_id: string; source_fragment_id: string; documents: { copy: string; live: string; pinned: string }; pin_original_publication: string; pin_original_pdf_sha256: string; files: { filename: string; sha256: string }[] }
type AddressedState = { source_msp?: boolean; organization_id: string; document_id: string; content_id: string; fragment_id: string; original_id: string; original_pdf_sha256: string; edited_markdown: string; observation_id?: string; files: { filename: string; sha256: string }[] }
type ClientPublicationState = { organization_id: string; document_id: string; content_id: string; original_id: string; original_pdf_filename: string; original_pdf_sha256: string; review_on: string; companion_publication_id: string; sessions: { approver: string; client: string }; files: { filename: string; sha256: string }[] }
type State = { native_templates: NativeTemplateFixture; native_sites: { staff: { id: string; title: string }; client: { id: string; title: string } }; native_approval_password: string; cross_workspace: AddressedState; repeated: AddressedState; client_publication: ClientPublicationState; monitored: AddressedState; diagrams: AddressedState; addressed: AddressedState; content_keys: AddressedState; template: TemplateState; document_id: string; content_id: string; fragment_id: string; shared_live_fragment_id: string; shared_pin_fragment_id: string; original_id: string; original_pdf_sha256: string; session_name: string; sessions: { owner: string; viewer: string }; files: { filename: string; sha256: string }[] }
const stateDirectory = process.env.TEKDOCS_PUBLICATION_ACCEPTANCE_DIRECTORY!
const diagnostics = new WeakMap<Page, ReturnType<typeof attachPublicationDiagnostics>>()
const additionalDiagnostics = new WeakMap<Page, ReturnType<typeof attachPublicationDiagnostics>[]>()

test.beforeEach(({ page }, info) => {
  const scenario = info.title.startsWith('new template documents') ? 'native_templates' : info.title.startsWith('new keyed documents') ? 'native_keys' : info.title.startsWith('new primary-file documents') ? 'native_primary_files' : info.title.startsWith('new staff documents') || info.title.startsWith('new client documents') ? 'native_publications' : info.title.startsWith('client publications') ? 'client_publications' : info.title.startsWith('template sources') ? 'templates' : (info.title.startsWith('migrated signed') || info.title.startsWith('repeated shared') || info.title.startsWith('cross-Workspace')) ? 'history_templates'
    : info.title.startsWith('field keys') ? 'field_keys'
      : info.title.startsWith('nested content') ? 'content_keys'
        : info.title.startsWith('diagram revisions') ? 'diagrams'
          : info.title.startsWith('monitored sources') ? 'monitored_sources' : 'unknown'
  diagnostics.set(page, attachPublicationDiagnostics(page, { scenario }))
})

test.afterEach(async ({ page }, info) => {
  const diagnostic = diagnostics.get(page)
  if (!diagnostic) return
  try {
    const visible: Record<string, unknown> = {}
    if (info.status !== 'passed' && info.status !== 'skipped' && !page.isClosed()) {
      try {
        const [prompts, creates, templates, pdfs, repositoryEditor, repositorySourceFailure, repositoryEmpty, nativeLibrary, applicationError] = await Promise.all([
          page.locator('dialog.unsaved-changes-dialog[open]').count(),
          page.getByRole('button', { name: 'Create document', exact: true }).count(),
          page.getByRole('button', { name: 'Use template', exact: true }).count(),
          page.getByRole('link', { name: 'Download PDF', exact: true }).or(page.getByRole('button', { name: 'Download retained PDF', exact: true })).count(),
          page.getByRole('region', { name: 'Markdown editor', exact: true }).count(),
          page.getByText('The selected source could not be opened.', { exact: true }).count(),
          page.getByText('Choose a file or create a new one.', { exact: true }).count(),
          page.getByRole('region', { name: 'Git-backed templates', exact: true }).count(),
          page.getByRole('heading', { name: 'This page could not open', exact: true }).count(),
        ])
        Object.assign(visible, { navigationPrompt: prompts > 0, createTemplate: creates > 0, useTemplate: templates > 0, pdfDownload: pdfs > 0, repositoryEditor: repositoryEditor > 0, repositorySourceFailure: repositorySourceFailure > 0, repositoryEmpty: repositoryEmpty > 0, nativeLibrary: nativeLibrary > 0, applicationError: applicationError > 0 })
      } catch {
        // A timed-out navigation may already have destroyed the page. Retain
        // request timings without replacing the original failure with a probe error.
      }
    }
    diagnostic.finish(info.status ?? 'unknown', visible)
  } finally {
    for (const extra of additionalDiagnostics.get(page) ?? []) { extra.finish(info.status ?? 'unknown'); extra.dispose() }
    additionalDiagnostics.delete(page)
    diagnostic.dispose(); diagnostics.delete(page)
  }
})

async function downloadPdf(page: Page) {
  diagnostics.get(page)?.mark('pdf_download')
  const promise = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download PDF', exact: true }).click()
  const download = await promise
  try {
    expect(await download.failure()).toBeNull()
    const bytes = await readFile(await download.path())
    expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
    return createHash('sha256').update(bytes).digest('hex')
  } finally { await download.delete() }
}

async function templateJourney(page: Page, state: State) {
  diagnostics.get(page)?.mark('template')
  const fixture = state.template
  const path = `/workspaces/organizations/${fixture.organization_id}/documentation`
  await page.goto(`/documentation?repository=${fixture.source_fragment_id}`)
  await page.getByLabel('Markdown body').fill('Browser template procedure updated.\n')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Saved as one accepted Git commit.')
  for (const mode of ['copy', 'live', 'pinned'] as const) {
    await page.goto(`${path}?document=${fixture.documents[mode]}`)
    await expect(page.getByText(`Browser client ${mode} local introduction.`, { exact: true })).toBeVisible()
    await expect(page.getByText(mode === 'live' ? 'Browser template procedure updated.' : 'Browser template procedure original.', { exact: true })).toBeVisible()
  }
  await page.getByRole('button', { name: 'Check template updates' }).click()
  const applyStarted = performance.now()
  const applied = page.waitForResponse(response => response.url().endsWith('/template-rollouts/apply') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Apply update', exact: true }).click()
  expect((await applied).status()).toBe(200)
  console.info(`Template acceptance apply acknowledgement: ${Math.round(performance.now() - applyStarted)} ms`)
  await expect(page.getByText('Browser template procedure updated.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Publish document', exact: true }).click()
  await page.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Retain reviewed enrolled template')
  const publicationResponse = page.waitForResponse(r => r.url().endsWith('/publications') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  const response = await publicationResponse
  expect(response.status()).toBe(201)
  const publication = await response.json() as DocumentPublicationDetail
  expect(publication.manifest.format).toBe('tekdocs-static-publication/v8')
  expect(publication.verification.valid).toBe(true)
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  await downloadPdf(page)
  for (const file of fixture.files) {
    const promise = page.waitForEvent('download')
    await page.locator('.publication-artifacts').getByRole('link').filter({ hasText: file.filename }).click()
    const download = await promise
    try {
      expect(await download.failure()).toBeNull()
      expect(createHash('sha256').update(await readFile(await download.path())).digest('hex')).toBe(file.sha256)
    } finally { await download.delete() }
  }
  await page.goto(`${path}?document=${fixture.documents.pinned}&publication=${fixture.pin_original_publication}`)
  await expect(page.getByText('Browser template procedure original.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  expect(await downloadPdf(page)).toBe(fixture.pin_original_pdf_sha256)
  await page.goto(`${path}?document=${fixture.documents.live}`)
  await page.getByRole('button', { name: 'Check template updates' }).click()
  const detached = page.waitForResponse(response => /\/placements\/[^/]+\/detach$/.test(response.url()) && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Make Template procedure a local copy' }).click()
  expect((await detached).status()).toBe(200)
  await expect(page.getByRole('button', { name: 'Make Template procedure a local copy' })).toHaveCount(0)
  await expect(page.getByText('Browser template procedure updated.', { exact: true })).toBeVisible()
  await page.goto(path)
  await page.getByRole('button', { name: 'Templates from your MSP' }).click()
  await page.getByRole('button', { name: 'Use template' }).click()
  await page.getByLabel('Document title', { exact: true }).fill('Browser newly enrolled')
  const created = page.waitForResponse(response => response.url().endsWith('/from-template') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Create document', exact: true }).click()
  const createdResponse = await created
  expect(createdResponse.status()).toBe(201)
  const createdDocument = await createdResponse.json() as { id: string }
  await expect(page).toHaveURL(new RegExp(`[?&]document=${createdDocument.id}(?:&|$)`))
  await expect(page.getByText('Browser template procedure updated.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
}

test('native documents appear in the library and reopen through the repository editor', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  await rehearseRepositoryContent(page, state.template.organization_id)
})

async function nativePublicationDocument(page: Page, title: string, organizationId?: string, kind: 'document' | 'fragment' = 'document') {
  const scope = organizationId ? `/workspaces/organizations/${organizationId}` : ''
  await page.goto(`${scope}/documentation`)
  await page.getByRole('button', { name: 'Repository content', exact: true }).click()
  await page.getByRole('button', { name: 'New Markdown file' }).click()
  await page.getByLabel('Content type').selectOption(kind)
  await page.getByLabel('Title', { exact: true }).fill(title)
  await page.getByLabel('Markdown body').fill('Native publication original.\n')
  const saved = page.waitForResponse(response => response.url().endsWith('/content-graph/authoring') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(200)
  const source = await response.json() as { content_id: string }
  await expect(page.getByRole('button', { name: 'Save to Git', exact: true })).toBeDisabled()
  return { id: source.content_id, path: `${scope}/documentation?repository=${source.content_id}` }
}

async function retainNativeSnapshot(page: Page, clientVisible = false) {
  await page.getByRole('button', { name: 'Publish document', exact: true }).click()
  if (clientVisible) await page.getByLabel('Publication audience').selectOption('client_visible')
  const created = page.waitForResponse(response => response.url().endsWith('/repository-publication-evidence') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Retain snapshot', exact: true }).click()
  const response = await created
  expect(response.status()).toBe(201)
  return await response.json() as { id: string }
}

async function nativeDecision(page: Page, label: string, correction = false, password?: string) {
  const publishing = page.getByRole('region', { name: 'Publishing', exact: true })
  await publishing.getByRole('button', { name: label, exact: true }).click()
  const form = publishing.getByRole('form', { name: label, exact: true })
  const reason = form.getByLabel('Decision reason')
  if (await reason.count()) await reason.fill('Reviewed native browser decision')
  if (correction) await form.getByLabel('Replace the current publication as a correction').check()
  const response = page.waitForResponse(result => result.url().includes('/repository-publication-evidence/') && result.request().method() === 'POST')
  await form.getByRole('button', { name: 'Confirm decision' }).click()
  const decision = await response
  if (decision.status() === 403 && password) {
    expect((await decision.json() as { error: { code: string } }).error.code).toBe('recent_authentication_required')
    // Generated test credentials remain in private IPC; traces/screenshots are off.
    await test.step('Confirm the generated test password', async () => {
      await publishing.getByLabel('Current password', { exact: true }).fill(password)
      await publishing.getByRole('button', { name: 'Confirm password', exact: true }).click()
    }, { box: true })
    await expect(publishing.getByLabel('Current password', { exact: true })).toHaveCount(0)
    expect(await reason.inputValue()).toBe('Reviewed native browser decision')
    const retry = page.waitForResponse(result => result.url().includes('/repository-publication-evidence/') && result.request().method() === 'POST')
    await form.getByRole('button', { name: 'Confirm decision' }).click()
    expect((await retry).status()).toBe(201)
  } else expect(decision.status()).toBe(201)
  await expect(form).toHaveCount(0)
}

async function nativeRetainedPdf(page: Page) {
  const promise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download retained PDF', exact: true }).click()
  const download = await promise
  try {
    expect(await download.failure()).toBeNull()
    const bytes = await readFile(await download.path())
    expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
    return createHash('sha256').update(bytes).digest('hex')
  } finally { await download.delete() }
}

async function nativePrimaryPanel(page: Page) {
  const panel = page.getByRole('region', { name: 'Primary file versions', exact: true })
  const loaded = page.waitForResponse(response => response.url().endsWith('/primary-file?page=1') && response.request().method() === 'GET')
  if (await panel.count()) await panel.getByRole('button', { name: 'Refresh file versions' }).click()
  else await page.getByRole('button', { name: 'Primary file versions', exact: true }).click()
  expect((await loaded).status()).toBe(200)
  await expect(panel.getByLabel('Choose primary file')).toBeEnabled()
  return panel
}

async function appendNativePrimary(page: Page, filename: string, content: string, previous = 0) {
  const panel = await nativePrimaryPanel(page)
  await panel.getByLabel('Choose primary file').setInputFiles({ name: filename, mimeType: 'text/plain', buffer: Buffer.from(content) })
  if (previous) {
    await expect(panel.getByRole('button', { name: 'Replace primary file', exact: true })).toBeDisabled()
    await panel.getByLabel('Replace version ' + previous + '; keep all earlier versions').check()
  }
  const uploaded = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/primary-file') && response.request().method() === 'POST')
  await panel.getByRole('button', { name: previous ? 'Replace primary file' : 'Upload primary file', exact: true }).click()
  const response = await uploaded
  expect(response.status()).toBe(201)
  const version = await response.json() as DocumentPrimaryFile
  expect(version.version_number).toBe(previous + 1)
  await expect(panel.getByRole('button', { name: 'Download ' + filename + ', version ' + version.version_number })).toBeEnabled()
  await expect(panel.getByRole('button', { name: 'Refresh file versions' })).toBeEnabled()
  return version
}

async function downloadNativePrimary(page: Page, filename: string, version: number, expected: string) {
  const downloaded = page.waitForEvent('download')
  await page.getByRole('region', { name: 'Primary file versions', exact: true }).getByRole('button', { name: 'Download ' + filename + ', version ' + version }).click()
  const file = await downloaded
  try {
    expect(await file.failure()).toBeNull()
    expect(file.suggestedFilename()).toBe(filename)
    expect((await readFile(await file.path())).toString()).toBe(expected)
  } finally { await file.delete() }
}

async function configureNativeKeys(page: Page, fragment: { id: string; title: string }, site: { id: string; title: string }) {
  await page.getByRole('button', { name: 'Keys and references', exact: true }).click()
  const keys = page.getByRole('region', { name: 'Keys and references', exact: true })
  await keys.getByLabel('Binding name', { exact: true }).focus()
  await page.keyboard.press('Tab')
  await expect(keys.getByLabel('Find a record or reusable fragment')).toBeFocused()
  for (const [name, target] of [['site', site], ['steps', fragment]] as const) {
    await keys.getByLabel('Find a record or reusable fragment').fill(target.title)
    await expect(keys.getByRole('button', { name: 'Bind key to ' + target.title, exact: true })).toBeVisible()
    await keys.getByLabel('Binding name', { exact: true }).fill(name)
    await keys.getByRole('button', { name: 'Bind key to ' + target.title, exact: true }).click()
    await expect(keys.getByLabel('Binding name', { exact: true })).toHaveValue('')
    await expect(keys.getByLabel('Insert key for ' + name, { exact: true })).toBeEnabled()
    await keys.getByLabel('Insert key for ' + name, { exact: true }).selectOption(name === 'site' ? 'name' : 'content')
  }
  await keys.getByLabel('Find a record or reusable fragment').fill(site.title)
  await expect(keys.getByRole('button', { name: 'Insert reference to ' + site.title, exact: true })).toBeEnabled()
  await keys.getByRole('button', { name: 'Insert reference to ' + site.title, exact: true }).click()
  const saved = page.waitForResponse(response => response.url().endsWith('/content-graph/authoring') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  expect((await saved).status()).toBe(200)
  await expect(page.getByRole('button', { name: 'Save to Git', exact: true })).toBeDisabled()
}

test('new keyed documents freeze field values, fragment text and entity references independently of later edits', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  const fragment = await nativePublicationDocument(page, 'Native browser reusable steps', undefined, 'fragment')
  const native = await nativePublicationDocument(page, 'Native keyed browser guide')
  await configureNativeKeys(page, { ...fragment, title: 'Native browser reusable steps' }, state.native_sites.staff)
  const detail = await page.request.get('/api/v1/workspaces/msp/content-graph/documents/' + native.id)
  expect(detail.status()).toBe(200)
  expect((await detail.json() as { sanitized_html: string }).sanitized_html).toContain(state.native_sites.staff.title)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  const original = await retainNativeSnapshot(page)
  const evidenceUrl = '/api/v1/workspaces/msp/repository-publication-evidence/' + original.id
  const frozen = await page.request.get(evidenceUrl)
  expect(frozen.status()).toBe(200)
  const body = await frozen.json() as { verified: boolean }
  expect(body.verified).toBe(true)
  const rendered = await page.request.get(evidenceUrl + '/review/html')
  expect(rendered.status()).toBe(200)
  const originalHtml = await rendered.text()
  expect(originalHtml).toContain(state.native_sites.staff.title)
  expect(originalHtml).not.toContain('tekdocs://key/')
  await nativeDecision(page, 'Publish snapshot')
  const pdf = await nativeRetainedPdf(page)
  await page.goto(fragment.path)
  await page.getByLabel('Markdown body').fill('Native browser later fragment.\n')
  const saved = page.waitForResponse(response => response.url().endsWith('/content-graph/authoring') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  expect((await saved).status()).toBe(200)
  const later = await page.request.get('/api/v1/workspaces/msp/content-graph/documents/' + native.id)
  expect((await later.json() as { sanitized_html: string }).sanitized_html).toContain('Native browser later fragment.')
  expect(await (await page.request.get(evidenceUrl)).json()).toEqual(body)
  expect(await (await page.request.get(evidenceUrl + '/review/html')).text()).toBe(originalHtml)
  await page.goto(native.path)
  await page.getByRole('button', { name: 'Load publication history' }).click()
  await page.getByRole('region', { name: 'Repository publication history', exact: true }).getByRole('button', { name: /Native keyed browser guide/ }).click()
  expect(await nativeRetainedPdf(page)).toBe(pdf)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.app-body')).toHaveCSS('margin-left', '0px')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
})

test('new staff documents publish, correct and withdraw while retaining their original PDFs', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  await page.setViewportSize({ width: 390, height: 844 })
  const native = await nativePublicationDocument(page, 'Native staff browser guide')
  await appendNativePrimary(page, 'staff-primary-v1.txt', 'Staff primary version one.\n')
  const first = await retainNativeSnapshot(page)
  await nativeDecision(page, 'Publish snapshot')
  const originalPdf = await nativeRetainedPdf(page)
  await page.getByLabel('Markdown body').fill('Native publication corrected.\n')
  const save = page.waitForResponse(response => response.url().endsWith('/content-graph/authoring') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  expect((await save).status()).toBe(200)
  await expect(page.getByRole('button', { name: 'Save to Git', exact: true })).toBeDisabled()
  await appendNativePrimary(page, 'staff-primary-v2.txt', 'Staff primary version two.\n', 1)
  const second = await retainNativeSnapshot(page)
  expect(second.id).not.toBe(first.id)
  await nativeDecision(page, 'Publish snapshot', true)
  await nativeDecision(page, 'Withdraw publication')
  const publishing = page.getByRole('region', { name: 'Publishing', exact: true })
  await expect(publishing.getByRole('status')).toHaveText('Withdrawn')
  expect(await nativeRetainedPdf(page)).not.toBe(originalPdf)
  await appendNativePrimary(page, 'staff-primary-v3.txt', 'Staff primary after publication.\n', 2)
  await downloadNativePrimary(page, 'staff-primary-v1.txt', 1, 'Staff primary version one.\n')
  await downloadNativePrimary(page, 'staff-primary-v2.txt', 2, 'Staff primary version two.\n')
  await downloadNativePrimary(page, 'staff-primary-v3.txt', 3, 'Staff primary after publication.\n')
  await page.goto(native.path)
  await page.getByRole('button', { name: 'Load publication history' }).click()
  const history = page.getByRole('region', { name: 'Repository publication history', exact: true })
  await history.getByRole('button', { name: /Native staff browser guide/ }).last().click()
  await expect(publishing.getByRole('status')).toHaveText('Superseded')
  expect(await nativeRetainedPdf(page)).toBe(originalPdf)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
})

test('new client documents require independent approval and revoke portal access on correction and withdrawal', async ({ page, browser }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const organizationId = state.client_publication.organization_id
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  const approver = await browser.newContext({ baseURL: 'http://localhost:8080' })
  const portal = await browser.newContext({ baseURL: 'http://localhost:8080' })
  try {
    await approver.addCookies([{ name: state.session_name, value: state.client_publication.sessions.approver, url: 'http://localhost:8080' }])
    await portal.addCookies([{ name: state.session_name, value: state.client_publication.sessions.client, url: 'http://localhost:8080' }])
    const reviewer = await approver.newPage()
    const clientPage = await portal.newPage()
    additionalDiagnostics.set(page, [reviewer, clientPage].map(selected => attachPublicationDiagnostics(selected, { scenario: 'native_publications' })))
    const fragment = await nativePublicationDocument(page, 'Native client reusable steps', organizationId, 'fragment')
    const native = await nativePublicationDocument(page, 'Native client browser guide', organizationId)
    await configureNativeKeys(page, { ...fragment, title: 'Native client reusable steps' }, state.native_sites.client)
    const evidenceRoot = `/api/v1/workspaces/organizations/${organizationId}/repository-publication-evidence`
    const selectLatest = async (actor: Page) => {
      await actor.goto(native.path)
      await actor.getByRole('button', { name: 'Load publication history' }).click()
      await actor.getByRole('region', { name: 'Repository publication history', exact: true }).getByRole('button', { name: /Native client browser guide/ }).first().click()
    }
    let originalPublication = ''
    let originalPdf = ''
    let originalPrimaryUrl = ''
    for (let iteration = 0; iteration < 2; iteration++) {
      if (iteration) {
        await page.getByLabel('Markdown body').fill('Native client publication corrected.\n')
        const saved = page.waitForResponse(response => response.url().endsWith('/content-graph/authoring') && response.request().method() === 'POST')
        await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
        expect((await saved).status()).toBe(200)
        await expect(page.getByRole('button', { name: 'Save to Git', exact: true })).toBeDisabled()
      }
      const primary = await appendNativePrimary(page, 'client-primary-v' + (iteration + 1) + '.txt', 'Client primary version ' + (iteration + 1) + '.\n', iteration)
      if (iteration) {
        const retainedOriginal = await portal.request.get(originalPrimaryUrl)
        expect(retainedOriginal.status()).toBe(200)
        expect((await retainedOriginal.body()).toString()).toBe('Client primary version 1.\n')
      }
      const evidence = await retainNativeSnapshot(page, true)
      await expect(page.getByRole('region', { name: 'Publishing', exact: true }).getByRole('button', { name: 'Accept snapshot', exact: true })).toHaveCount(0)
      const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrftoken')?.value
      expect(csrf).toBeTruthy()
      expect((await page.request.post(`${evidenceRoot}/${evidence.id}/decision`, { headers: { 'X-CSRFToken': csrf! }, data: { outcome: 'accepted_for_packaging', reason: 'Self approval denied' } })).status()).toBe(409)
      await selectLatest(reviewer)
      await nativeDecision(reviewer, 'Accept snapshot')
      await nativeDecision(reviewer, 'Prepare publication package')
      await page.getByRole('button', { name: 'Refresh publication' }).click()
      await nativeDecision(page, 'Approve publication package')
      await nativeDecision(page, 'Create signed publication')
      const status = await (await page.request.get(`${evidenceRoot}/${evidence.id}/workflow`)).json() as { publication_id: string }
      expect((await portal.request.get(`/api/v1/portal/repository-publications/${status.publication_id}`)).status()).toBe(404)
      await reviewer.getByRole('button', { name: 'Refresh publication' }).click()
      await nativeDecision(reviewer, 'Release publication', iteration === 1)
      await nativeDecision(reviewer, 'Authorize client access', false, state.native_approval_password)
      const clientRecord = await portal.request.get(`/api/v1/portal/repository-publications/${status.publication_id}`)
      expect(clientRecord.status()).toBe(200)
      const portalBody = await clientRecord.json() as { rendered_html: string }
      expect(JSON.stringify(portalBody)).not.toContain('key_source')
      if (!iteration) expect(portalBody.rendered_html).toContain(state.native_sites.client.title)
      const retainedFiles = await clientRecord.json() as { primary_file: { selected_source_id: string; versions: { id: string; source_id: string; version_number: number }[] } }
      expect(retainedFiles.primary_file.selected_source_id).toBe(primary.id)
      expect(retainedFiles.primary_file.versions).toHaveLength(iteration + 1)
      for (const retained of retainedFiles.primary_file.versions) {
        const url = '/api/v1/portal/repository-publications/' + status.publication_id + '/attachments/' + retained.id
        const downloaded = await portal.request.get(url)
        expect(downloaded.status()).toBe(200)
        expect((await downloaded.body()).toString()).toBe('Client primary version ' + retained.version_number + '.\n')
        if (!iteration) originalPrimaryUrl = url
      }
      await clientPage.goto(`/portal?section=publications&publication=${status.publication_id}`)
      await expect(clientPage.getByText('Native client browser guide', { exact: true }).first()).toBeVisible()
      await expect(clientPage.locator('article')).toContainText(iteration ? 'Native client publication corrected.' : 'Native publication original.')
      const pdf = await portal.request.get(`/api/v1/portal/repository-publications/${status.publication_id}/pdf`)
      expect(pdf.status()).toBe(200)
      expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')
      if (!iteration) {
        originalPublication = status.publication_id
        originalPdf = createHash('sha256').update(await pdf.body()).digest('hex')
      } else {
        expect((await portal.request.get(`/api/v1/portal/repository-publications/${originalPublication}`)).status()).toBe(404)
        expect((await portal.request.get(originalPrimaryUrl)).status()).toBe(404)
        await nativeDecision(reviewer, 'Withdraw publication')
        expect((await portal.request.get(`/api/v1/portal/repository-publications/${status.publication_id}`)).status()).toBe(404)
        for (const retained of retainedFiles.primary_file.versions) expect((await portal.request.get('/api/v1/portal/repository-publications/' + status.publication_id + '/attachments/' + retained.id)).status()).toBe(404)
      }
    }
    await page.goto(native.path)
    await page.getByRole('button', { name: 'Load publication history' }).click()
    await page.getByRole('region', { name: 'Repository publication history', exact: true }).getByRole('button', { name: /Native client browser guide/ }).last().click()
    expect(await nativeRetainedPdf(page)).toBe(originalPdf)
    expect((await portal.request.get(`${evidenceRoot}`)).status()).toBe(403)
    expect((await portal.request.get('/api/v1/workspaces/organizations/' + organizationId + '/content-graph/authoring/' + native.id + '/keys')).status()).toBe(403)
    expect((await portal.request.get('/api/v1/workspaces/organizations/' + organizationId + '/content-graph/authoring/' + native.id + '/primary-file')).status()).toBe(403)
  } finally { await approver.close(); await portal.close() }
})

test('new primary-file documents retain every version and require review after concurrent replacement', async ({ page, browser }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const organizationId = state.client_publication.organization_id
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  const native = await nativePublicationDocument(page, 'Native primary-file browser guide', organizationId)
  const first = await appendNativePrimary(page, 'primary-v1.txt', 'Primary browser original.\n')
  const other = await page.context().newPage()
  const portal = await browser.newContext({ baseURL: 'http://localhost:8080' })
  try {
    additionalDiagnostics.set(page, [attachPublicationDiagnostics(other, { scenario: 'native_primary_files' })])
    await other.goto(native.path)
    await expect(other.getByLabel('Markdown body')).toHaveValue('Native publication original.\n')
    const files = await nativePrimaryPanel(other)
    await other.getByLabel('Markdown body').fill('Unsaved primary-file draft.\n')
    await files.getByLabel('Choose primary file').setInputFiles({ name: 'primary-v3.txt', mimeType: 'text/plain', buffer: Buffer.from('Primary browser reviewed retry.\n') })
    await files.getByLabel('Replace version 1; keep all earlier versions').check()
    await appendNativePrimary(page, 'primary-v2.txt', 'Primary browser concurrent replacement.\n', 1)
    const conflict = other.waitForResponse(response => new URL(response.url()).pathname.endsWith('/primary-file') && response.request().method() === 'POST')
    await files.getByRole('button', { name: 'Replace primary file', exact: true }).click()
    expect((await conflict).status()).toBe(409)
    await expect(files.getByRole('alert')).toContainText('Your selected file is kept here')
    await expect(files.getByText('Selected: primary-v3.txt', { exact: true })).toBeVisible()
    await expect(files.getByRole('button', { name: 'Replace primary file', exact: true })).toBeDisabled()
    await nativePrimaryPanel(other)
    const confirmation = files.getByLabel('Replace version 2; keep all earlier versions')
    await expect(confirmation).not.toBeChecked()
    await confirmation.focus(); await confirmation.press('Space')
    await expect(confirmation).toBeChecked()
    const replaced = other.waitForResponse(response => new URL(response.url()).pathname.endsWith('/primary-file') && response.request().method() === 'POST')
    await files.getByRole('button', { name: 'Replace primary file', exact: true }).click()
    expect((await replaced).status()).toBe(201)
    await expect(files.getByRole('button', { name: 'Download primary-v3.txt, version 3' })).toBeEnabled()
    await downloadNativePrimary(other, 'primary-v1.txt', 1, 'Primary browser original.\n')
    await downloadNativePrimary(other, 'primary-v2.txt', 2, 'Primary browser concurrent replacement.\n')
    await downloadNativePrimary(other, 'primary-v3.txt', 3, 'Primary browser reviewed retry.\n')
    await expect(other.getByLabel('Markdown body')).toHaveValue('Unsaved primary-file draft.\n')
    await other.getByRole('button', { name: 'Back to documentation' }).click()
    await other.getByRole('button', { name: 'Keep editing', exact: true }).click()
    const endpoint = '/api/v1/workspaces/organizations/' + organizationId + '/content-graph/authoring/' + native.id
    const stored = await page.request.get(endpoint)
    expect(stored.status()).toBe(200)
    expect((await stored.json() as { markdown: string }).markdown).toBe('Native publication original.\n')
    expect((await page.request.get('/api/v1/workspaces/msp/content-graph/authoring/' + native.id + '/primary-file')).status()).toBe(404)
    const downloadPath = '/api/v1/workspaces/organizations/' + organizationId + '/content-graph/documents/' + native.id + '/attachments/' + first.id + '/download'
    expect((await page.request.get(downloadPath.replace('/organizations/' + organizationId, '/msp'))).status()).toBe(404)
    await portal.addCookies([{ name: state.session_name, value: state.client_publication.sessions.client, url: 'http://localhost:8080' }])
    expect((await portal.request.get(endpoint + '/primary-file')).status()).toBe(403)
    expect((await portal.request.get(downloadPath)).status()).toBe(403)
    await page.goto(native.path)
    expect(new URL(page.url()).searchParams.get('repository') === native.id).toBe(true)
    await expect(page.getByLabel('Markdown body')).toHaveValue('Native publication original.\n')
    await page.reload()
    await nativePrimaryPanel(page)
    await expect(page.getByRole('button', { name: /^Download primary-v/ })).toHaveCount(3)
    await page.setViewportSize({ width: 390, height: 844 })
    // Match the existing repository journey: measure after the sidebar settles.
    await expect(page.locator('.app-body')).toHaveCSS('margin-left', '0px')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  } finally { await other.close(); await portal.close() }
})

test('migrated signed history survives real publishing, correction, withdrawal and PDF downloads', async ({ page, browser }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const path = `/documentation?document=${state.document_id}`
  const endpoint = `/api/v1/documents/${state.document_id}/publications`
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  page.on('dialog', dialog => void dialog.accept())
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(path)
  const diagnostics = await page.request.get('/api/v1/system/diagnostics')
  expect(diagnostics.status()).toBe(200)
  const expected = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8')) as { version: string }
  expect((await diagnostics.json() as { application_version: string }).application_version).toBe(expected.version)
  await expect(page.getByText('Current migrated browser instructions.', { exact: true })).toBeVisible()
  await expect(page.getByText('Shared live browser original.', { exact: true })).toBeVisible()
  await expect(page.getByText('Shared pinned browser original.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Publication history', exact: true }).click()
  await page.getByRole('region', { name: 'Publication history' }).getByRole('button').filter({ hasText: 'Migrated publication acceptance guide' }).click()
  await expect(page.getByText('Original signed browser instructions.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  expect(await downloadPdf(page)).toBe(state.original_pdf_sha256)
  const originalResponse = await page.request.get(`${endpoint}/${state.original_id}`)
  expect(originalResponse.status()).toBe(200)
  const original = await originalResponse.json() as DocumentPublicationDetail
  await page.goto(path)
  await page.getByRole('button', { name: 'Publish document', exact: true }).click()
  const form = page.locator('.publication-form')
  await form.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Retain the migrated Git source')
  const publishedResponse = page.waitForResponse(r => new URL(r.url()).pathname === endpoint && r.request().method() === 'POST')
  await form.getByRole('button', { name: 'Publish', exact: true }).click()
  const response = await publishedResponse
  expect(response.status()).toBe(201)
  const published = await response.json() as DocumentPublicationDetail
  expect(published.manifest.format).toBe('tekdocs-static-publication/v7')
  expect(published.canonical_markdown).toContain('Current migrated browser instructions.')
  expect(published.verification.valid).toBe(true)
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  for (const file of state.files) {
    const downloadPromise = page.waitForEvent('download')
    await page.locator('.publication-artifacts').getByRole('link').filter({ hasText: file.filename }).click()
    const download = await downloadPromise
    try {
      expect(await download.failure()).toBeNull()
      expect(createHash('sha256').update(await readFile(await download.path())).digest('hex')).toBe(file.sha256)
    } finally { await download.delete() }
  }

  for (const [fragment, body] of [
    [state.shared_live_fragment_id, 'Shared live browser updated.\n'],
    [state.shared_pin_fragment_id, 'Shared pinned source browser updated.\n'],
  ] as const) {
    await page.goto(`/documentation?repository=${fragment}`)
    await page.getByLabel('Markdown body').fill(body)
    await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
    await expect(page.getByRole('status')).toHaveText('Saved as one accepted Git commit.')
  }
  await page.goto(path)
  await expect(page.getByText('Shared live browser updated.', { exact: true })).toBeVisible()
  await expect(page.getByText('Shared pinned browser original.', { exact: true })).toBeVisible()
  await expect(page.getByText('Shared pinned source browser updated.', { exact: true })).toHaveCount(0)
  const frozen = await (await page.request.get(`${endpoint}/${published.id}`)).json() as DocumentPublicationDetail
  expect(frozen.canonical_markdown).toContain('Shared live browser original.')
  expect(frozen.signature).toBe(published.signature)
  expect(frozen.manifest).toEqual(published.manifest)

  // Edit the owned fragment through the real Git editor, then supersede the
  // original legacy snapshot from the ordinary retained-publication interface.
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`/documentation?repository=${state.fragment_id}`)
  await page.getByLabel('Markdown body').fill('Browser-corrected Git instructions.\n')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Saved as one accepted Git commit.')
  const current = await page.request.get(`/api/v1/workspaces/msp/content-graph/documents/${state.content_id}`)
  expect(current.status()).toBe(200)
  expect((await current.json() as RepositoryDocumentRead).sanitized_html).toContain('Browser-corrected Git instructions.')
  const filtered = await page.request.get('/api/v1/documents/search?q=unmatched-acceptance-filter')
  expect(filtered.status()).toBe(200)
  expect((await filtered.json() as { count: number }).count).toBe(0)
  await page.goto(`${path}&doc_q=unmatched-acceptance-filter&publication=${state.original_id}`)
  await expect(page.getByRole('button', { name: 'Publish correction', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Publish correction', exact: true }).click()
  await form.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Supersede the original legacy instructions')
  const legacyCorrectionResponse = page.waitForResponse(r => new URL(r.url()).pathname === endpoint && r.request().method() === 'POST')
  await form.getByRole('button', { name: 'Publish correction', exact: true }).click()
  const legacyCorrection = await legacyCorrectionResponse
  expect(legacyCorrection.status()).toBe(201)
  expect((await legacyCorrection.json() as DocumentPublicationDetail).supersedes_id).toBe(state.original_id)
  // Also correct a Git snapshot and withdraw that successor.
  await page.goto(`${path}&publication=${published.id}`)
  await page.getByRole('button', { name: 'Publish correction', exact: true }).click()
  await form.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Correct the retained instructions')
  const correctedResponse = page.waitForResponse(r => new URL(r.url()).pathname === endpoint && r.request().method() === 'POST')
  await form.getByRole('button', { name: 'Publish correction', exact: true }).click()
  const correctionResponse = await correctedResponse
  expect(correctionResponse.status()).toBe(201)
  const correction = await correctionResponse.json() as DocumentPublicationDetail
  expect(correction.supersedes_id).toBe(published.id)
  expect(correction.canonical_markdown).toContain('Browser-corrected Git instructions.')
  await page.getByRole('button', { name: 'Withdraw publication' }).click()
  await page.getByRole('textbox', { name: 'Decision reason' }).fill('Retain for staff history only')
  await page.getByRole('button', { name: 'Withdraw', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Published version withdrawn')
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await expect(page.getByText('Retain for staff history only', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  await downloadPdf(page)

  const viewer = await browser.newContext()
  try {
    await viewer.addCookies([{ name: state.session_name, value: state.sessions.viewer, url: 'http://localhost:8080' }])
    const readerPage = await viewer.newPage()
    readerPage.on('dialog', dialog => void dialog.accept())
    await readerPage.goto(path)
    await readerPage.getByRole('button', { name: 'Publish document', exact: true }).click()
    await readerPage.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Keep this denied draft')
    const denialResponse = readerPage.waitForResponse(r => new URL(r.url()).pathname === endpoint && r.request().method() === 'POST')
    await readerPage.getByRole('button', { name: 'Publish', exact: true }).click()
    const denied = await denialResponse
    expect(denied.status()).toBe(403)
    const denial = await denied.json() as { error: { code: string; detail: { detail: string } } }
    expect(denial.error.code).toBe('permission_denied')
    expect(denial.error.detail.detail).toBe('Your account is not authorized for this action.')
    await expect(readerPage.getByRole('alert')).toHaveText('Your account is not authorized to change documentation in this workspace.')
    await expect(readerPage.getByRole('textbox')).toHaveValue('Keep this denied draft')
    const retainedPdf = await readerPage.request.get(`${endpoint}/${state.original_id}/export?export_format=pdf`)
    expect(retainedPdf.status()).toBe(200)
    expect(createHash('sha256').update(await retainedPdf.body()).digest('hex')).toBe(state.original_pdf_sha256)
  } finally { await viewer.close() }
  const anonymous = await browser.newContext()
  try { expect((await anonymous.request.get(`http://localhost:8080${endpoint}/${state.original_id}/export?export_format=pdf`)).status()).toBe(403) }
  finally { await anonymous.close() }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${path}&document_view=publications`)
  await expect(page.getByRole('region', { name: 'Publication history' }).getByRole('listitem')).toHaveCount(4)
  const retained = await (await page.request.get(`${endpoint}/${state.original_id}`)).json() as DocumentPublicationDetail
  expect(retained.signature).toBe(original.signature)
  expect(retained.manifest).toEqual(original.manifest)
  expect(retained.canonical_markdown).toBe(original.canonical_markdown)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
})

test('template sources retain copy, live and pinned enrollments through publication and rollback', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  page.on('dialog', dialog => void dialog.accept())
  await page.setViewportSize({ width: 390, height: 844 })
  await templateJourney(page, state)
})

async function runKeyPublicationJourney(page: Page, state: State, fixture: AddressedState, expected: { initial: string; retained: string; current: string; format: string; keys: string[] }) {
  diagnostics.get(page)?.mark(fixture.observation_id ? 'monitored' : 'keyed')
  page.on('dialog', dialog => void dialog.accept())
  const path = `/workspaces/organizations/${fixture.organization_id}/documentation`
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  await page.setViewportSize({ width: 390, height: 844 })
  const readPath = `/api/v1/workspaces/organizations/${fixture.organization_id}/content-graph/documents/${fixture.content_id}`
  const openCurrentDocument = async () => {
    const [response] = await Promise.all([
      page.waitForResponse(response => new URL(response.url()).pathname === readPath && response.request().method() === 'GET'),
      page.goto(`${path}?document=${fixture.document_id}`),
    ])
    expect(response.status()).toBe(200)
    expect(await response.finished()).toBeNull()
  }
  await openCurrentDocument()
  await expect(page.locator('article')).toContainText(expected.initial)
  await page.goto(`${path}?document=${fixture.document_id}&publication=${fixture.original_id}`)
  await expect(page.getByText(expected.retained, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  expect(await downloadPdf(page)).toBe(fixture.original_pdf_sha256)

  if (fixture.observation_id) {
    await page.goto(`${path}?document=${fixture.document_id}`)
    await page.getByRole('button', { name: 'Web source', exact: true }).click()
    const change = page.locator('.remote-observations li').first()
    await expect(change).toContainText(expected.current)
    await expect(change.getByRole('button', { name: 'Apply reviewed change' })).toBeDisabled()
    await expect(change.getByRole('status')).toContainText('Local edits are preserved.')
    await expect(page.getByText('Applying this source also updates documents that follow this section. Pinned versions and signed publications stay unchanged.')).toBeVisible()
    await expect(page.locator('article')).toContainText('Local recovery note must survive.')
    await page.getByRole('button', { name: 'Close web source' }).click()
  }

  await page.goto(`${fixture.source_msp ? "/documentation" : path}?repository=${fixture.fragment_id}`)
  await page.getByLabel('Markdown body').fill(fixture.edited_markdown)
  const saved = page.waitForResponse(response => response.url().endsWith('/content-graph/authoring') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save to Git', exact: true }).click()
  expect((await saved).status()).toBe(200)
  await expect(page.getByRole('status')).toHaveText('Saved as one accepted Git commit.')
  await openCurrentDocument()
  await expect(page.locator('article')).toContainText(expected.current)
  if (fixture.observation_id) {
    await page.getByRole('button', { name: 'Web source', exact: true }).click()
    const change = page.locator('.remote-observations li').first()
    const sourceInterval = page.getByLabel('Check every (minutes)')
    await sourceInterval.fill('240')
    const settingsSaved = page.waitForResponse(response => response.url().endsWith('/remote-source') && response.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Save source', exact: true }).click()
    expect((await settingsSaved).status()).toBe(201)
    await expect(page.getByRole('button', { name: 'Save source', exact: true })).toBeEnabled()
    await expect(page.getByRole('status')).toHaveText('Web source saved.')
    const refused = page.waitForResponse(response => response.url().endsWith(`/observations/${fixture.observation_id}/apply`))
    await change.getByRole('button', { name: 'Apply reviewed change' }).click()
    expect((await refused).status()).toBe(409)
    await expect(sourceInterval).toHaveValue('240')
    await expect(page.getByRole('alert')).toContainText('changed after review')
    await sourceInterval.fill('180')
    const settingsRestored = page.waitForResponse(response => response.url().endsWith('/remote-source') && response.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Save source', exact: true }).click()
    expect((await settingsRestored).status()).toBe(201)
    await expect(page.getByRole('button', { name: 'Save source', exact: true })).toBeEnabled()
    await expect(page.getByRole('status')).toHaveText('Web source saved.')
    await page.getByRole('button', { name: 'Close web source' }).click()
    await page.getByRole('button', { name: 'Web source', exact: true }).click()
    const applied = page.waitForResponse(response => response.url().endsWith(`/observations/${fixture.observation_id}/apply`))
    await change.getByRole('button', { name: 'Apply reviewed change' }).click()
    expect((await applied).status()).toBe(200)
    await expect(page.getByRole('status')).toHaveText('Reviewed source change applied.')
    await expect(page.locator('article')).toContainText('Local recovery note must survive.')
  }
  if (expected.keys.length) {
    await page.getByRole('button', { name: /^Keys/ }).click()
    const report = page.getByRole('group', { name: 'Keys used in this document' })
    for (const key of expected.keys) {
      await expect(report.getByText(key, { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: `Retire ${key.split('.')[0]}` })).toHaveCount(0)
    }
    await expect(page.getByRole('textbox', { name: 'Declare', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Close keys' }).click()
  }

  await page.getByRole('button', { name: 'Publish document', exact: true }).click()
  await page.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Retain current resolved instructions')
  const published = page.waitForResponse(response => response.url().endsWith('/publications') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Publish', exact: true }).click()
  const response = await published
  expect(response.status()).toBe(201)
  const publication = await response.json() as DocumentPublicationDetail
  expect(publication.manifest.format).toBe(expected.format)
  expect(publication.verification.valid).toBe(true)
  await expect(page.getByText(expected.current, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  await downloadPdf(page)
  for (const file of fixture.files) {
    const promise = page.waitForEvent('download')
    await page.locator('.publication-artifacts').getByRole('link').filter({ hasText: file.filename }).click()
    const download = await promise
    try {
      expect(await download.failure()).toBeNull()
      expect(createHash('sha256').update(await readFile(await download.path())).digest('hex')).toBe(file.sha256)
    } finally { await download.delete() }
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  return publication
}


test('field keys and entity references retain signed values, files and PDF history', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  await runKeyPublicationJourney(page, state, state.addressed, {
    initial: 'Visit Current addressed site.', retained: 'Visit Original addressed site.',
    current: 'Visit Current addressed site with code OPS.', format: 'tekdocs-static-publication/v9',
    keys: ['subject.code', 'subject.name'],
  })
})

test('nested content keys retain signed substitutions, file versions and PDF history', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const publication = await runKeyPublicationJourney(page, state, state.content_keys, {
    initial: 'Original reusable recovery instructions.', retained: 'Original reusable recovery instructions.',
    current: 'Current accepted reusable recovery instructions.', format: 'tekdocs-static-publication/v10',
    keys: ['procedure.content'],
  })
  await correctAndWithdraw(page, publication, 'tekdocs-static-publication/v10')
})


async function correctAndWithdraw(page: Page, publication: DocumentPublicationDetail, format: string) {
  await page.getByRole('button', { name: 'Publish correction', exact: true }).click()
  const form = page.locator('.publication-form')
  await form.getByRole('textbox', { name: 'Why are you publishing this?' }).fill('Correct retained content substitutions')
  const corrected = page.waitForResponse(response => response.url().endsWith('/publications') && response.request().method() === 'POST')
  await form.getByRole('button', { name: 'Publish correction', exact: true }).click()
  const response = await corrected
  expect(response.status()).toBe(201)
  const correction = await response.json() as DocumentPublicationDetail
  expect(correction.supersedes_id).toBe(publication.id)
  expect(correction.manifest.format).toBe(format)
  expect(correction.verification.valid).toBe(true)
  await page.getByRole('button', { name: 'Withdraw publication' }).click()
  await page.getByRole('textbox', { name: 'Decision reason' }).fill('Retain withdrawn content-key history')
  await page.getByRole('button', { name: 'Withdraw', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Published version withdrawn')
  await page.getByRole('button', { name: 'History', exact: true }).click()
  await expect(page.getByText('Retain withdrawn content-key history', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  await downloadPdf(page)
}


test('diagram revisions retain graphics, signed PDFs and file versions after migration', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const publication = await runKeyPublicationJourney(page, state, state.diagrams, {
    initial: 'Original diagram recovery instructions.', retained: 'Original diagram recovery instructions.',
    current: 'Current diagram recovery instructions.', format: 'tekdocs-static-publication/v11', keys: [],
  })
  await page.getByRole('button', { name: 'Content', exact: true }).click()
  const diagram = page.locator('.mermaid-diagram-export').getByRole('img', { name: 'Recovery route' })
  await expect(diagram).toBeVisible()
  await expect.poll(() => diagram.evaluate((node) => (node as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  expect(publication.manifest.diagrams).toHaveLength(1)
  const graphics = publication.artifacts.filter(item => item.kind === 'diagram_svg' || item.kind === 'diagram_png')
  expect(graphics).toHaveLength(2)
  await page.getByRole('button', { name: 'Downloads', exact: true }).click()
  for (const graphic of graphics) {
    const promise = page.waitForEvent('download')
    await page.locator('.publication-artifacts').getByRole('link').filter({ hasText: graphic.filename }).click()
    const download = await promise
    try {
      expect(await download.failure()).toBeNull()
      expect(createHash('sha256').update(await readFile(await download.path())).digest('hex')).toBe(graphic.checksum)
    } finally { await download.delete() }
  }
  await correctAndWithdraw(page, publication, 'tekdocs-static-publication/v11')
})


test('monitored sources preserve local edits, require a fresh review and retain signed files and PDFs', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const publication = await runKeyPublicationJourney(page, state, state.monitored, {
    initial: 'Original monitored recovery instructions.', retained: 'Original monitored recovery instructions.',
    current: 'Current monitored recovery instructions.', format: 'tekdocs-static-publication/v6', keys: [],
  })
  expect(publication.canonical_markdown).toContain('Local recovery note must survive.')
  await correctAndWithdraw(page, publication, 'tekdocs-static-publication/v6')
})


test('client publications retain portal access, independent approval, audience files and withdrawal', async ({ page, browser }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const fixture = state.client_publication
  const path = `/workspaces/organizations/${fixture.organization_id}/documentation?document=${fixture.document_id}`
  const endpoint = `/api/v1/workspaces/organizations/${fixture.organization_id}/documents/${fixture.document_id}/publications`
  const portal = '/api/v1/portal/documents'
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  page.on('dialog', dialog => void dialog.accept())
  await page.setViewportSize({ width: 390, height: 844 })
  const client = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const approver = await browser.newContext({ viewport: { width: 390, height: 844 } })
  try {
    await client.addCookies([{ name: state.session_name, value: fixture.sessions.client, url: 'http://localhost:8080' }])
    await approver.addCookies([{ name: state.session_name, value: fixture.sessions.approver, url: 'http://localhost:8080' }])
    const clientPage = await client.newPage(), approverPage = await approver.newPage()
    approverPage.on('dialog', dialog => void dialog.accept())
    additionalDiagnostics.set(page, [clientPage, approverPage].map(selected => attachPublicationDiagnostics(selected, { scenario: 'client_publications' })))
    await clientPage.goto(`/portal?section=documents&document=${fixture.original_id}`)
    await expect(clientPage.getByRole('heading', { name: 'Client publication migration acceptance guide', exact: true })).toBeVisible()
    await expect(clientPage.getByText('Retained shared client instructions.', { exact: true })).toBeVisible()
    await expect(clientPage.getByText('MSP-only migration instructions.', { exact: true })).toHaveCount(0)
    const downloadFile = async (filename: string, checksum: string) => {
      const waiting = clientPage.waitForEvent('download')
      await clientPage.getByRole('link', { name: filename, exact: true }).click()
      const download = await waiting
      try {
        expect(await download.failure()).toBeNull()
        expect(createHash('sha256').update(await readFile(await download.path())).digest('hex')).toBe(checksum)
      } finally { await download.delete() }
    }
    await downloadFile(fixture.original_pdf_filename, fixture.original_pdf_sha256)
    await page.goto(`${path}&publication=${fixture.original_id}`)
    await page.getByRole('button', { name: 'Publish correction', exact: true }).click()
    await page.getByLabel('Why are you publishing this?').fill('Client browser correction')
    await expect(page.getByLabel('Who can see it?')).toHaveValue('client_visible')
    await page.getByLabel('How long should it be kept?').selectOption('review_on')
    await page.getByLabel('Review date', { exact: true }).fill(fixture.review_on)
    await expect(page.getByRole('button', { name: 'Publish correction', exact: true })).toBeEnabled()
    const creating = page.waitForResponse(response => new URL(response.url()).pathname === endpoint && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Publish correction', exact: true }).click()
    const created = await creating
    expect(created.status()).toBe(201)
    const publication = await created.json() as DocumentPublicationDetail
    expect(publication.lifecycle_state).toBe('pending_approval')
    expect(publication.verification.valid).toBe(true)
    expect((await clientPage.request.get(`${portal}/${publication.id}`)).status()).toBe(404)
    expect((await clientPage.request.get(`${portal}/${fixture.original_id}`)).status()).toBe(200)
    await approverPage.goto(`${path}&publication=${publication.id}`)
    await approverPage.getByRole('button', { name: 'History', exact: true }).click()
    await approverPage.getByRole('button', { name: 'Approve publication', exact: true }).click()
    await approverPage.getByLabel('Decision reason').fill('Independent client browser approval')
    const approving = approverPage.waitForResponse(response => response.url().endsWith(`/publications/${publication.id}/approve`) && response.request().method() === 'POST')
    await approverPage.getByRole('button', { name: 'Approve', exact: true }).click()
    expect((await approving).status()).toBe(200)
    await clientPage.goto(`/portal?section=documents&document=${publication.id}`)
    await expect(clientPage.getByText('Current shared client instructions.', { exact: true })).toBeVisible()
    await expect(clientPage.getByText('Client-only migration instructions.', { exact: true })).toBeVisible()
    expect(await clientPage.locator('body').innerText()).not.toContain('Staff publication fixture site')
    await expect(clientPage.getByRole('link', { name: 'staff-checklist.txt', exact: true })).toHaveCount(0)
    for (const file of fixture.files) await downloadFile(file.filename, file.sha256)
    const pdf = publication.artifacts.find(item => item.kind === 'pdf')
    if (!pdf) throw new Error('The signed publication PDF descriptor is missing')
    await downloadFile(pdf.filename, pdf.checksum)
    expect((await clientPage.request.get(`${portal}/${fixture.original_id}`)).status()).toBe(404)
    expect(await clientPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
    await approverPage.getByRole('button', { name: 'History', exact: true }).click()
    await approverPage.getByRole('button', { name: 'Withdraw publication', exact: true }).click()
    await approverPage.getByLabel('Decision reason').fill('Client browser withdrawal')
    const withdrawing = approverPage.waitForResponse(response => response.url().endsWith(`/publications/${publication.id}/withdraw`) && response.request().method() === 'POST')
    await approverPage.getByRole('button', { name: 'Withdraw', exact: true }).click()
    expect((await withdrawing).status()).toBe(200)
    expect((await clientPage.request.get(`${portal}/${publication.id}`)).status()).toBe(404)
    expect((await clientPage.request.get(`${portal}/${publication.id}/artifacts/${pdf.id}/download`)).status()).toBe(404)
    expect((await clientPage.request.get(`${portal}/${fixture.original_id}`)).status()).toBe(404)
    await clientPage.goto('/portal?section=documents')
    await expect(clientPage.getByRole('button', { name: /^Client publication recovery companion / })).toBeVisible()
    await expect(clientPage.getByRole('button', { name: /^Client publication migration acceptance guide / })).toHaveCount(0)
  } finally { await client.close(); await approver.close() }
})


test('repeated shared blocks retain distinct pins, live updates, file versions and signed PDFs', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const publication = await runKeyPublicationJourney(page, state, state.repeated, {
    initial: 'First pinned shared edition.', retained: 'First pinned shared edition.',
    current: 'Updated live shared edition.', format: 'tekdocs-static-publication/v12', keys: [],
  })
  for (const text of ['First pinned shared edition.', 'Second pinned shared edition.', 'Updated live shared edition.']) {
    expect(publication.canonical_markdown.split(text)).toHaveLength(2)
  }
  expect(publication.canonical_markdown).not.toContain('Current live shared edition.')
  await correctAndWithdraw(page, publication, 'tekdocs-static-publication/v12')
})


test('cross-Workspace reuse retains distinct pins, live updates, file versions and signed PDFs', async ({ page }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  const readPath = `/api/v1/workspaces/organizations/${state.cross_workspace.organization_id}/content-graph/documents/${state.cross_workspace.content_id}`
  await page.route(url => url.pathname === readPath, async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    await expect(page.locator('article')).toContainText('Loading Git-backed document…')
    // Keep a valid read in flight beyond the DOM assertion's default budget.
    // The workflow must synchronize with the scoped response before rendering.
    await new Promise(resolve => setTimeout(resolve, 6000))
    await route.fulfill({ response })
  }, { times: 1 })
  const publication = await runKeyPublicationJourney(page, state, state.cross_workspace, {
    initial: 'First retained library edition.', retained: 'First retained library edition.',
    current: 'Updated live library edition.', format: 'tekdocs-static-publication/v13', keys: [],
  })
  for (const text of ['First retained library edition.', 'Second retained library edition.', 'Updated live library edition.']) {
    expect(publication.canonical_markdown.split(text)).toHaveLength(2)
  }
  expect(publication.canonical_markdown).not.toContain('Private MSP child')
  expect(publication.canonical_markdown).not.toContain('Current live library edition.')
  await correctAndWithdraw(page, publication, 'tekdocs-static-publication/v13')
})


test('new template documents preserve copy live and pinned sections through reviewed updates and detach', async ({ page, browser }) => {
  const state = JSON.parse(await readFile(`${stateDirectory}/ready.json`, 'utf8')) as State
  await page.context().addCookies([{ name: state.session_name, value: state.sessions.owner, url: 'http://localhost:8080' }])
  const document = await rehearseNativeTemplates(page, state.native_templates, state.template.organization_id)
  const viewer = await browser.newContext()
  let failed = false
  let primaryError: unknown
  try {
    await viewer.addCookies([{ name: state.session_name, value: state.sessions.viewer, url: 'http://localhost:8080' }])
    const reader = await viewer.newPage()
    additionalDiagnostics.set(page, [attachPublicationDiagnostics(reader, { scenario: 'native_templates' })])
    const boundary = (path: string) => {
      const pending = reader.waitForResponse(response => response.request().method() === 'GET' && new URL(response.url()).pathname === path)
      // Later boundaries may never run after an earlier denial; teardown still owns their listeners.
      void pending.catch(() => undefined)
      return pending
    }
    const session = boundary('/_allauth/browser/v1/auth/session')
    const auth = boundary('/api/v1/auth/context')
    const workspacePath = '/api/v1/workspaces/organizations/' + state.native_templates.organization_id
    const workspace = boundary(workspacePath)
    const source = boundary(workspacePath + '/content-graph/authoring/' + document.id)
    await reader.goto(document.path)
    expect((await session).status()).toBe(200)
    const authenticated = await auth
    expect(authenticated.status()).toBe(200)
    expect((await authenticated.json() as { role: string }).role).toBe('read_only')
    expect((await workspace).status()).toBe(200)
    expect((await source).status()).toBe(200)
    const settings = reader.getByRole('button', { name: 'Template settings and updates', exact: true })
    await expect(settings).toBeVisible()
    await expect(settings).toBeEnabled()
    const review = boundary(workspacePath + '/content-graph/authoring/' + document.id + '/template')
    await settings.click()
    const reviewed = await review
    expect(reviewed.status()).toBe(200)
    expect((await reviewed.json() as { read_only: boolean }).read_only).toBe(true)
    await expect(reader.getByText('Template changes are not permitted for this document.', { exact: true })).toBeVisible()
    await expect(reader.getByRole('button', { name: 'Apply reviewed update', exact: true })).toBeDisabled()
  } catch (error) { failed = true; primaryError = error }
  try { await viewer.close() } catch (error) { if (!failed) throw error }
  if (failed) throw primaryError
})
