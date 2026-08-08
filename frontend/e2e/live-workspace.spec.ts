import { randomBytes, randomUUID } from 'node:crypto'
import * as OTPAuth from 'otpauth'
import { expect, test } from '@playwright/test'

test('real owner creates and enters a PostgreSQL-backed organization workspace', async ({ page }) => {
  const deploymentToken = process.env.TEKDOCS_E2E_BOOTSTRAP_TOKEN
  if (!deploymentToken) throw new Error('The isolated live test requires TEKDOCS_E2E_BOOTSTRAP_TOKEN.')

  const suffix = randomUUID()
  const email = `workspace-owner-${suffix}@example.invalid`
  const password = `${randomBytes(24).toString('base64url')}Aa7!`

  await page.goto('/')
  await page.getByLabel('Deployment token').fill(deploymentToken)
  await page.getByLabel('MSP name').fill('Live Workspace MSP')
  await page.getByLabel('Your name').fill('Live Workspace Owner')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await page.getByRole('button', { name: 'Create workspace' }).click()
  const bootstrapAlert = page.getByRole('alert')
  await Promise.race([
    page.getByRole('heading', { name: 'Overview' }).waitFor(),
    bootstrapAlert.waitFor(),
  ])
  if (await bootstrapAlert.isVisible()) {
    throw new Error(`Owner bootstrap failed in the live stack: ${await bootstrapAlert.textContent()}`)
  }
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

  await page.goto('/settings')
  await page.getByRole('button', { name: 'Set up authenticator' }).click()
  const currentPassword = page.getByLabel('Current password')
  const setupAddressDisclosure = page.getByText('Show setup address')
  await Promise.race([currentPassword.waitFor(), setupAddressDisclosure.waitFor()])
  if (await currentPassword.isVisible()) {
    await currentPassword.fill(password)
    await page.getByRole('button', { name: 'Confirm change' }).click()
  }
  await setupAddressDisclosure.click()
  const setupAddress = await page.locator('.mfa-manual-setup details code').textContent()
  if (!setupAddress) throw new Error('Authenticator setup address was unavailable.')
  const totp = OTPAuth.URI.parse(setupAddress)
  if (!(totp instanceof OTPAuth.TOTP)) throw new Error('Authenticator setup did not return a TOTP address.')
  await page.getByLabel('Authentication code').fill(totp.generate())
  await page.getByRole('button', { name: 'Enable two-factor authentication' }).click()
  await page.getByRole('button', { name: 'I saved these codes' }).click()

  await page.goto('/organizations')
  await page.getByRole('button', { name: 'New organization' }).click()
  await page.getByLabel('Display name').fill('Live Acme Client')
  await page.getByLabel(/Legal name/).fill('Live Acme Client, LLC')
  await page.getByLabel(/Website/).fill('https://live-acme.example.com')
  await page.getByRole('checkbox', { name: 'Vendor' }).check()
  await page.getByRole('button', { name: 'Save organization' }).click()
  await expect(page.getByRole('status')).toHaveText('Organization added.')

  await page.getByRole('link', { name: 'Live Acme Client' }).click()
  await expect(page).toHaveURL(/\/workspaces\/organizations\/[0-9a-f-]+\/overview$/)
  await expect(page.getByRole('heading', { name: 'Live Acme Client' })).toBeVisible()
  await expect(page.getByText('Live Acme Client, LLC')).toBeVisible()
  await expect(
    page.getByRole('main').getByText('Client · Vendor workspace', { exact: true }),
  ).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Live Acme Client' })).toBeVisible()

  await page.getByRole('button', { name: /Current workspace: Live Acme Client/ }).click()
  await page.getByRole('textbox', { name: 'Find a workspace' }).fill('Live Acme')
  await expect(page.getByRole('button', { name: 'Live Acme Client. Client · Vendor' })).toBeVisible()
  await page.getByRole('button', { name: 'Live Workspace MSP. MSP workspace' }).click()
  await expect(page).toHaveURL((url) => url.pathname === '/overview')
  await page.getByRole('button', { name: /Current workspace: Live Workspace MSP/ }).click()
  await page.getByRole('textbox', { name: 'Find a workspace' }).fill('Live Acme')
  await page.getByRole('button', { name: 'Live Acme Client. Client · Vendor' }).click()
  await expect(page).toHaveURL(/\/workspaces\/organizations\/[0-9a-f-]+\/overview$/)
})
