import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('invitation activation removes the fragment and opens the member workspace', async ({ page, baseURL }) => {
  const token = `${crypto.randomUUID().replaceAll('-', '')}${crypto.randomUUID().replaceAll('-', '')}`
  const password = `${crypto.randomUUID()}Aa7!`
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/invitations/accept', async (route) => {
    const request = route.request()
    expect(request.postDataJSON()).toEqual({
      token,
      display_name: 'Invited Technician',
      password,
    })
    await route.fulfill({
      json: {
        user: { id: crypto.randomUUID(), email: 'invitee@example.com', display_name: 'Invited Technician' },
        tenant: { id: crypto.randomUUID(), name: 'Example MSP' },
      },
    })
  })

  await page.goto(`/auth/invitations/accept#token=${token}`)
  await expect(page).toHaveURL('/auth/invitations/accept')
  await page.getByLabel('Your name').fill('Invited Technician')
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
  await page.getByRole('button', { name: 'Activate account' }).click()

  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
})

test('missing invitation token has one accessible unavailable state', async ({ page }) => {
  await page.goto('/auth/invitations/accept')

  await expect(page.getByRole('heading', { name: 'Invitation unavailable' })).toBeVisible()
  await expect(page.getByText(/missing, expired, revoked, or has already been used/i)).toBeVisible()
  await expect(new AxeBuilder({ page }).analyze()).resolves.toMatchObject({ violations: [] })
})
