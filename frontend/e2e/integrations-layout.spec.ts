import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const pageResult = { results: [], page: 1, page_size: 50, count: 0, has_more: false }

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: [],
    surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route('**/workspaces/msp/integrations/providers', (route) => route.fulfill({ json: [{
    key: 'netbox', label: 'NetBox', version: '1.0', direction: 'read_only',
    credential_fields: [{ key: 'api_token', label: 'API token', secret: true, minimum_length: 8, input_type: 'password', help_text: '' }],
    capabilities: ['inventory_observations', 'reconciliation'], object_types: ['ipam.vlan'], pagination: 'opaque_cursor',
    minimum_sync_interval_minutes: 5, maximum_sync_interval_minutes: 10080,
    health_states: ['unknown', 'healthy', 'degraded', 'failing', 'paused'], observation_schema_version: 1,
    default_base_url: '', base_url_editable: true, setup_help_url: '',
  }] }))
  await page.route('**/workspaces/msp/integrations/connections', (route) => route.fulfill({ json: [] }))
  await page.route('**/workspaces/msp/integrations/jobs?*', (route) => route.fulfill({ json: pageResult }))
  await page.route('**/workspaces/msp/integrations/logs?*', (route) => route.fulfill({ json: pageResult }))
  await page.route('**/workspaces/msp/integrations/observations?*', (route) => route.fulfill({ json: pageResult }))
  await page.route('**/workspaces/msp/integrations/conflicts?*', (route) => route.fulfill({ json: pageResult }))
  await page.route('**/workspaces/msp/integrations/imports?*', (route) => route.fulfill({ json: { ...pageResult, page_size: 25 } }))
}

async function chooseSection(page: Page, section: 'imports', mobile: boolean) {
  if (mobile) await page.getByRole('combobox', { name: 'Sections' }).selectOption(section)
  else await page.getByRole('link', { name: 'Imports' }).click()
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`integration sections retain drafts and fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 })
    await fixtures(page)
    let exportReads = 0
    await page.route('**/workspaces/msp/integrations/git-exports', (route) => {
      exportReads += 1
      return route.fulfill({ json: [] })
    })
    await page.goto('/integrations')
    await expect(page.getByRole('heading', { name: 'Connections' })).toBeVisible()
    expect(exportReads).toBe(0)
    await page.getByRole('button', { name: 'New connection' }).click()
    await page.getByLabel('Name').fill('Draft NetBox')
    await chooseSection(page, 'imports', width < 768)
    await expect(page.getByRole('heading', { name: 'Unsaved changes' })).toBeVisible()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(page).toHaveURL(/\/integrations$/)
    await expect(page.getByLabel('Name')).toHaveValue('Draft NetBox')
    await chooseSection(page, 'imports', width < 768)
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page).toHaveURL(/section=imports/)
    await expect(page.getByRole('heading', { name: 'Preview an import' })).toBeVisible()
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('integration collections retry without reloading the page', async ({ page }) => {
  await fixtures(page)
  let attempts = 0
  await page.route('**/workspaces/msp/integrations/providers', (route) => {
    attempts += 1
    return attempts === 1 ? route.fulfill({ status: 503, json: {} }) : route.fulfill({ json: [] })
  })
  await page.goto('/integrations')
  await expect(page.getByRole('alert')).toContainText('Integrations could not be loaded.')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { name: 'Connections' })).toBeVisible()
  expect(attempts).toBe(2)
})
