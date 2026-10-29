import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import type { DocumentPublicationDetail, RepositoryDocumentRead } from '../src/documentation/api'

type State = { document_id: string; content_id: string; fragment_id: string; original_id: string; original_pdf_sha256: string; session_name: string; sessions: { owner: string; viewer: string }; files: { filename: string; sha256: string }[] }
const stateDirectory = process.env.TEKDOCS_PUBLICATION_ACCEPTANCE_DIRECTORY!

async function downloadPdf(page: Page) {
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

test('migrated signed history survives real publishing, correction, withdrawal and PDF downloads', async ({ page, browser }) => {
  try {
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
    expect(published.manifest.format).toBe('tekdocs-static-publication/v6')
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
    await writeFile(`${stateDirectory}/browser-finished.json`, JSON.stringify({ status: 'passed' }), { mode: 0o640 })
  } catch (error) {
    await writeFile(`${stateDirectory}/browser-finished.json`, JSON.stringify({ status: 'failed' }), { mode: 0o640 })
    throw error
  }
})
