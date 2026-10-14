import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('an old open tab recovers a missing route module only after an explicit reload', async ({ page }) => {
  await page.route('**/api/v1/bootstrap/status', route => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', route => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', route => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Recovery Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Recovery MSP' }, role: 'owner',
    permissions: ['assets.view'], surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/api/v1/workspaces/msp/assets/collection?*', route => route.fulfill({ json: {
    results: [], page: 1, page_size: 25, count: 0, total_pages: 1,
  } }))
  // Model an actual deployment: the open tab has an old entry bundle naming
  // a removed route hash; a full reload receives today's HTML and new hashes.
  await page.route('**/overview', async route => {
    if (!route.request().isNavigationRequest()) return route.continue()
    const response = await route.fetch()
    const html = await response.text()
    const entry = html.match(/src="(\/assets\/index-[^"/]+\.js)"/)
    if (!entry) throw new Error('Deployment recovery must run against production bundles')
    return route.fulfill({ response, body: html.replaceAll(/(\/assets\/[^"/]+\.js)(")/g, '$1?deployment=old$2') })
  })
  await page.route('**/assets/*.js?deployment=old', async route => {
    const current = new URL(route.request().url())
    current.search = ''
    const response = await route.fetch({ url: current.href })
    const source = await response.text()
    // Version the whole old module graph, including shared chunks that import
    // the entry bundle. Fresh HTML must load distinct module URLs after reload.
    return route.fulfill({ response, body: source.replaceAll(/([\w./-]+\.js)(["'`])/g, '$1?deployment=old$2') })
  })
  let missingRequests = 0
  let documentRequests = 0
  page.on('request', request => {
    if (request.isNavigationRequest() && request.frame() === page.mainFrame()) documentRequests += 1
  })
  await page.route('**/assets/Assets-*.js?deployment=old', route => {
    missingRequests += 1
    return route.fulfill({ status: 404, contentType: 'text/html', body: 'Not found' })
  })
  await page.goto('/overview')
  await page.getByRole('link', { name: 'Assets', exact: true }).click()
  await expect.poll(() => missingRequests).toBeGreaterThan(0)
  await expect(page.getByRole('heading', { name: 'Reload TekDocs to continue' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Reload TekDocs to continue' })).toBeFocused()
  expect(documentRequests).toBe(1)
  await expect(page.getByText('Unexpected Application Error!')).toHaveCount(0)
  const reload = page.getByRole('button', { name: 'Reload TekDocs', exact: true })
  await expect(reload).toBeDisabled()
  await page.setViewportSize({ width: 390, height: 700 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.keyboard.press('Tab')
  const acknowledgment = page.getByRole('checkbox', { name: 'I understand that reloading may discard unsaved changes.' })
  await expect(acknowledgment).toBeFocused()
  await page.keyboard.press('Space')
  await expect(acknowledgment).toBeChecked()
  await page.keyboard.press('Tab')
  await expect(reload).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Assets', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/assets$/)
  expect(documentRequests).toBe(2)
})
