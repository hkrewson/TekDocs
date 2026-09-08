import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const credentialId = crypto.randomUUID()

test('credential links explain the 1Password boundary without unnecessary controls', async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Primary Owner' },
    tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
    role: 'owner',
    permissions: ['credential_references.view', 'credential_references.manage', 'credential_references.open'],
  } }))
  await page.route('**/api/v1/credential-references?**', (route) => route.fulfill({ json: {
    results: [{
      id: credentialId,
      title: 'Firewall administrator',
      provider: 'onepassword',
      provider_label: '1Password',
      updated_at: '2026-09-05T12:00:00Z',
      can_manage: true,
      can_open: true,
    }],
    page: 1,
    page_size: 50,
    count: 1,
    has_more: false,
    can_manage: true,
  } }))

  await page.setViewportSize({ width: 320, height: 720 })
  await page.goto('/credentials')
  await expect(page.getByRole('heading', { name: 'Credential links' })).toBeVisible()
  await expect(page.getByText('Credentials stay in 1Password')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open in 1Password' })).toHaveAttribute('href', new RegExp(`${credentialId}/open$`))

  await page.getByRole('button', { name: 'New link' }).click()
  const editor = page.getByRole('heading', { name: 'New credential link' }).locator('..').locator('..').locator('..')
  await expect(page.getByRole('heading', { name: 'New credential link' })).toBeVisible()
  await expect(page.getByLabel('Title')).toBeVisible()
  await expect(page.getByLabel('Title')).toBeFocused()
  await expect(page.getByLabel('1Password Private Link')).toBeVisible()
  await expect(page.getByLabel('Provider')).toHaveCount(0)
  expect(await editor.evaluate((element) => Boolean(element.compareDocumentPosition(document.querySelector('.credential-reference-section')) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true)
  expect(await page.locator('main').evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)

  await page.getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('button', { name: 'Archive Firewall administrator' }).click()
  await expect(page.getByRole('alertdialog')).toContainText('The item and its access in 1Password will not change.')
  expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
})
