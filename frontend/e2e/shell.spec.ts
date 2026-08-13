import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const wcag22Tags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

const context = {
  user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
}
const documentBlockId = crypto.randomUUID()
const documentRevisionId = crypto.randomUUID()
const documentPlacementId = crypto.randomUUID()

const document = {
  id: crypto.randomUUID(),
  title: 'UniFi Network Setup Guide',
  owner_kind: 'msp',
  owner_organization_id: null,
  owner_organization_name: null,
  is_reference: false,
  category: 'guide',
  is_template: false,
  markdown: '# UniFi Network Setup Guide\n\nUse **approved** access.\n',
  block_id: documentBlockId,
  current_revision_id: documentRevisionId,
  revision_number: 1,
  checksum: '4c5543b28d58a32c3140a9f59050c48d862576dd71b031a825cfb4d8aa3fd4a4',
  resolved_markdown: '# UniFi Network Setup Guide\n\nUse **approved** access.\n',
  placements: [{ id: documentPlacementId, parent_id: null, block_id: documentBlockId, block_name: 'UniFi Network Setup Guide — content', position: 0, depth: 0, resolution_mode: 'live', pinned_revision_id: null, resolved_revision_id: documentRevisionId, resolved_revision_number: 1, resolved_checksum: '4c5543b28d58a32c3140a9f59050c48d862576dd71b031a825cfb4d8aa3fd4a4', is_primary: true }],
  placement_count: 1,
  attachments: [],
  attachment_count: 0,
  publications: [],
  publication_count: 0,
  created_at: '2026-08-09T12:00:00Z',
  updated_at: '2026-08-09T12:00:00Z',
}

async function mockAuthenticated(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 200,
    json: { status: 200, meta: { is_authenticated: true }, data: { user: context.user } },
  }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))
  const documentsRoute = (route: Route) => {
    if (route.request().url().includes('/revisions')) {
      if (new URL(route.request().url()).pathname.endsWith(documentRevisionId)) {
        return route.fulfill({ json: { id: documentRevisionId, parent_id: null, revision_number: 1, checksum: document.checksum, created_by: 'Primary Owner', created_at: document.created_at, is_current: true, markdown: document.markdown, diff_from_parent: '+# UniFi Network Setup Guide' } })
      }
      return route.fulfill({ json: { results: [{ id: documentRevisionId, parent_id: null, revision_number: 1, checksum: document.checksum, created_by: 'Primary Owner', created_at: document.created_at, is_current: true }], count: 51, page: 1, page_size: 50, has_more: true } })
    }
    return route.fulfill({ json: { results: [document], count: 1 } })
  }
  await page.route('**/api/v1/documents/**', documentsRoute)
  await page.route('**/api/v1/documents*', documentsRoute)
}

test('authenticated application shell exposes primary navigation and backend health', async ({ page, request }) => {
  const health = await request.get('/api/v1/health/ready')
  expect(health.ok()).toBeTruthy()
  await mockAuthenticated(page)

  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expect(page.getByText('Example MSP', { exact: true })).toBeVisible()
  const skipLink = page.getByRole('link', { name: 'Skip to main content' })
  await page.keyboard.press('Tab')
  await expect(skipLink).toBeFocused()
  await expect(skipLink).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.locator('main')).toBeFocused()
  await page.getByRole('link', { name: 'Documentation' }).click()
  await expect(page.getByRole('heading', { name: 'Documentation' })).toBeVisible()
  await expect(page.locator('main')).toBeFocused()
  await expect(page.getByRole('button', { name: 'UniFi Network Setup Guide' })).toBeVisible()
})

test('raw Markdown remains the editable canonical representation', async ({ page }) => {
  await mockAuthenticated(page)
  await page.goto('/documentation')
  await page.getByRole('button', { name: 'UniFi Network Setup Guide' }).click()
  const markdownTab = page.getByRole('tab', { name: 'Markdown' })
  await markdownTab.click()
  await expect(markdownTab).toBeFocused()
  await markdownTab.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Preview' })).toBeFocused()
  await expect(page.getByRole('tab', { name: 'Preview' })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('tab', { name: 'Preview' }).press('Home')
  await expect(page.getByRole('tab', { name: 'Editor' })).toBeFocused()
  const source = page.getByLabel('Markdown source')
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await expect(source).toHaveValue(/# UniFi Network Setup Guide/)
  await source.fill('# Updated procedure\n\nUse **approved** access.')
  await page.getByRole('tab', { name: 'Editor' }).click()
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await expect(source).toHaveValue('# Updated procedure\n\nUse **approved** access.\n')
})

test('technical Markdown has visual controls, semantic rendering, preview, and page help', async ({ page, baseURL }) => {
  await mockAuthenticated(page)
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/markdown/render', async (route) => {
    expect(route.request().method()).toBe('POST')
    expect(route.request().headers()['x-csrftoken']).toBeTruthy()
    const body: unknown = await route.request().postDataJSON()
    expect(body).toEqual(expect.objectContaining({ markdown: expect.stringContaining('==VLAN 10==') }))
    await route.fulfill({ json: { html: '<p>Verify <mark>VLAN 10</mark>.</p><blockquote class="callout callout-warning" data-callout="warning"><strong class="callout-title">Warning</strong><br>Disconnects the site.</blockquote>' } })
  })

  await page.goto('/documentation')
  await page.getByRole('button', { name: 'UniFi Network Setup Guide' }).click()
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await page.getByLabel('Markdown source').fill('Verify ==VLAN 10==.')
  await page.getByRole('tab', { name: 'Editor' }).click()

  await expect(page.getByRole('toolbar', { name: 'Block formatting' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Text style' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Task list' })).toBeEnabled()
  await expect(page.locator('.milkdown-host mark')).toHaveText('VLAN 10')

  await page.getByRole('combobox', { name: 'Text style' }).selectOption('h2')
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await expect(page.getByLabel('Markdown source')).toHaveValue(/^## Verify ==VLAN 10==\./)

  await page.getByRole('tab', { name: 'Preview' }).click()
  await expect(page.locator('.markdown-preview mark')).toHaveText('VLAN 10')
  await expect(page.locator('.markdown-preview blockquote')).toHaveAttribute('data-callout', 'warning')
  expect((await new AxeBuilder({ page }).include('.editor-section').withTags(wcag22Tags).analyze()).violations).toEqual([])

  await page.getByRole('tab', { name: 'Formatting help' }).click()
  await expect(page.getByRole('heading', { name: 'TekDocs Markdown' })).toBeVisible()
  await expect(page.getByText('==verify this==')).toBeVisible()
  await expect(page.getByText(/Raw HTML, MDX, scripts/)).toBeVisible()
})

test('revision history pagination and diffs remain keyboard-accessible', async ({ page }) => {
  await mockAuthenticated(page)
  await page.goto('/documentation')
  await page.getByRole('button', { name: 'UniFi Network Setup Guide' }).click()
  await page.getByRole('button', { name: 'Revision history' }).click()
  await expect(page.getByText('Showing 1–50 of 51')).toBeVisible()
  await page.getByRole('button', { name: /Revision 1/ }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Revision 1 changes' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Newer revisions' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Older revisions' })).toBeEnabled()
  expect((await new AxeBuilder({ page }).include('.revision-history').withTags(wcag22Tags).analyze()).violations).toEqual([])
})

test('mobile authenticated navigation is operable', async ({ page }) => {
  await mockAuthenticated(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/overview')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('link', { name: 'Documentation' })).toBeVisible()
  await page.getByRole('button', { name: 'Close navigation' }).first().click()
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
})

test('first-owner browser setup enters the authenticated shell', async ({ page, baseURL }) => {
  const csrf = crypto.randomUUID().replaceAll('-', '')
  await page.context().addCookies([{ name: 'csrftoken', value: csrf, url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: true } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 401,
    json: { status: 401, meta: { is_authenticated: false }, data: { flows: [{ id: 'login' }] } },
  }))
  await page.route('**/api/v1/bootstrap/owner', (route) => route.fulfill({ status: 201, json: { tenant: {}, owner: {} } }))
  await page.route('**/_allauth/browser/v1/auth/login', (route) => route.fulfill({
    status: 200,
    json: { status: 200, meta: { is_authenticated: true }, data: { user: context.user } },
  }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: context }))

  await page.goto('/')
  expect((await new AxeBuilder({ page }).withTags(wcag22Tags).analyze()).violations).toEqual([])
  const password = `${crypto.randomUUID()}Aa7!`
  await page.getByLabel('Deployment token').fill(crypto.randomUUID())
  await page.getByLabel('MSP name').fill('Example MSP')
  await page.getByLabel('Your name').fill('Primary Owner')
  await page.getByLabel('Email address').fill('owner@example.com')
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await page.getByRole('button', { name: 'Create workspace' }).click()

  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

test('sign-in boundary has no detectable accessibility violations', async ({ page }) => {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 401,
    json: { status: 401, meta: { is_authenticated: false }, data: { flows: [{ id: 'login' }] } },
  }))

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  expect((await new AxeBuilder({ page }).withTags(wcag22Tags).analyze()).violations).toEqual([])
})

test('sign out removes the shell and returns to sign in', async ({ page, baseURL }) => {
  await mockAuthenticated(page)
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/_allauth/browser/v1/auth/session', (route) => {
    if (route.request().method() === 'DELETE') {
      return route.fulfill({ status: 401, json: { status: 401, meta: { is_authenticated: false } } })
    }
    return route.fallback()
  })

  await page.goto('/overview')
  await page.getByRole('button', { name: /Account menu for Primary Owner/ }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Overview' })).not.toBeVisible()
})

test('account menu closes with Escape and restores trigger focus', async ({ page }) => {
  await mockAuthenticated(page)
  await page.goto('/overview')
  const trigger = page.getByRole('button', { name: /Account menu for Primary Owner/ })
  await trigger.click()
  await expect(page.getByRole('menu')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('menu')).not.toBeVisible()
  await expect(trigger).toBeFocused()
})

test('contextual help follows the page without embedding unpublished Wiki content', async ({ page }) => {
  await mockAuthenticated(page)
  await page.goto('/documentation')
  const trigger = page.getByRole('button', { name: 'Help for Documentation' })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: 'Documentation help' })
  await expect(dialog).toContainText('reuse live or pinned blocks')
  await expect(dialog.getByRole('status')).toContainText('public Wiki guide has not been published')
  await expect(dialog.getByRole('link')).toHaveCount(0)
  expect((await new AxeBuilder({ page }).include('.context-help-popover').withTags(wcag22Tags).analyze()).violations).toEqual([])
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
})
