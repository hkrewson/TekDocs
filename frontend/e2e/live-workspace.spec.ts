import { randomBytes, randomUUID } from 'node:crypto'
import * as OTPAuth from 'otpauth'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function invitationTokenFromMailpit(page: Page) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const messagesResponse = await page.request.get('http://mailpit:8025/api/v1/messages')
    expect(messagesResponse.ok()).toBe(true)
    const messages = await messagesResponse.json() as { messages?: Array<{ ID?: string }> }
    const messageId = messages.messages?.[0]?.ID
    if (messageId) {
      const messageResponse = await page.request.get(`http://mailpit:8025/api/v1/message/${messageId}`)
      expect(messageResponse.ok()).toBe(true)
      const match = JSON.stringify(await messageResponse.json()).match(/#token=([A-Za-z0-9_-]+)/)
      if (match) return match[1]
    }
    await page.waitForTimeout(250)
  }
  throw new Error('The staff invitation did not arrive in Mailpit.')
}

test('real owner creates and enters a PostgreSQL-backed organization workspace', async ({ browser, page }) => {
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

  const clientLink = page.getByRole('link', { name: 'Live Acme Client' })
  const clientHref = await clientLink.getAttribute('href')
  const clientId = clientHref?.match(/organizations\/([0-9a-f-]+)/)?.[1]
  if (!clientId) throw new Error('The created client did not expose its stable organization identifier.')

  const staffEmail = `live-technician-${suffix}@example.invalid`
  const csrfCookie = (await page.context().cookies()).find((cookie) => cookie.name === 'csrftoken')
  if (!csrfCookie) throw new Error('The owner session did not expose a CSRF cookie.')
  const invitationResponse = await page.request.post('/api/v1/invitations', {
    data: { email: staffEmail },
    headers: { 'X-CSRFToken': csrfCookie.value },
  })
  expect(invitationResponse.status()).toBe(201)
  const invitationToken = await invitationTokenFromMailpit(page)

  const staffContext = await browser.newContext()
  const staffPage = await staffContext.newPage()
  const staffPassword = `${randomBytes(24).toString('base64url')}Bb8!`
  await staffPage.goto(`/auth/invitations/accept#token=${invitationToken}`)
  await staffPage.getByLabel('Your name').fill('Live Assigned Technician')
  await staffPage.getByLabel('Password', { exact: true }).fill(staffPassword)
  await staffPage.getByLabel('Confirm password').fill(staffPassword)
  await staffPage.getByRole('button', { name: 'Activate account' }).click()
  await expect(staffPage.getByRole('heading', { name: 'Overview' })).toBeVisible()

  await page.getByRole('button', { name: /Account menu for Live Workspace Owner/ }).click()
  await page.getByRole('menuitem', { name: 'Access control' }).click()
  await expect(page.getByRole('heading', { name: 'Access control' })).toBeVisible()
  await page.getByRole('combobox', { name: 'Staff member for Live Acme Client' }).selectOption({ label: 'Live Assigned Technician · Read-only' })
  await page.getByRole('button', { name: 'Review assignment' }).click()
  await expect(page.getByRole('alertdialog')).toContainText('Their MSP role still determines what they can do')
  await page.getByRole('button', { name: 'Confirm change' }).click()
  await expect(page.getByRole('status')).toContainText('Live Assigned Technician was assigned to Live Acme Client')
  await page.getByRole('combobox', { name: 'Access mode for Live Acme Client' }).selectOption('assigned_only')
  await page.getByRole('table', { name: 'Organization access modes' }).getByRole('button', { name: 'Review change' }).click()
  await expect(page.getByRole('alertdialog')).toContainText('The owner retains break-glass access')
  await page.getByRole('button', { name: 'Confirm change' }).click()
  await expect(page.getByRole('status')).toContainText("Live Acme Client's access mode was updated")

  const assignedWorkspace = await staffPage.request.get(`/api/v1/workspaces/organizations/${clientId}`)
  expect(assignedWorkspace.status()).toBe(200)
  await staffPage.goto(clientHref)
  await expect(staffPage.getByRole('heading', { name: 'Live Acme Client' })).toBeVisible()

  await page.goto('/organizations')

  await page.getByRole('link', { name: 'Live Acme Client' }).click()
  await expect(page).toHaveURL(/\/workspaces\/organizations\/[0-9a-f-]+\/overview$/)
  await expect(page.getByRole('heading', { name: 'Live Acme Client' })).toBeVisible()
  await expect(page.getByText('Live Acme Client, LLC')).toBeVisible()
  await expect(
    page.getByRole('main').getByText('Client · Vendor workspace', { exact: true }),
  ).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Live Acme Client' })).toBeVisible()

  await page.getByRole('link', { name: 'Return to MSP organizations' }).click()
  await page.getByRole('button', { name: 'New organization' }).click()
  await page.getByLabel('Display name').fill('Live Northwind Vendor')
  await page.getByRole('checkbox', { name: 'Client' }).uncheck()
  await page.getByRole('checkbox', { name: 'Vendor' }).check()
  await page.getByRole('button', { name: 'Save organization' }).click()
  await expect(page.getByRole('status')).toHaveText('Organization added.')
  await page.getByRole('link', { name: 'Live Acme Client' }).click()
  await page.getByRole('button', { name: 'Add relationship' }).click()
  await page.getByLabel('Relationship type').selectOption('supplied_by')
  await page.getByRole('searchbox', { name: 'Related organization' }).fill('Northwind')
  await page.getByRole('radio', { name: /Live Northwind Vendor/ }).check()
  await page.getByRole('button', { name: 'Add supplied by' }).click()
  await expect(page.getByText('Relationship added.')).toBeVisible()
  await expect(page.getByText('Supplied by')).toBeVisible()
  await page.getByRole('link', { name: 'Live Northwind Vendor' }).click()
  await expect(page.getByText('Supplies')).toBeVisible()
  await expect(page.getByText('Backlink')).toBeVisible()
  await page.getByRole('link', { name: 'Live Acme Client' }).click()

  await page.getByRole('button', { name: /Current workspace: Live Acme Client/ }).click()
  await page.getByRole('textbox', { name: 'Find a client' }).fill('Live Acme')
  await expect(page.getByRole('button', { name: 'Live Acme Client. Client · Vendor' })).toBeVisible()
  await page.getByRole('button', { name: 'Back to Live Workspace MSP. MSP workspace' }).click()
  await expect(page).toHaveURL((url) => url.pathname === '/overview')
  await page.getByRole('button', { name: /Current workspace: Live Workspace MSP/ }).click()
  await page.getByRole('textbox', { name: 'Find an organization' }).fill('Live Acme')
  await page.getByRole('button', { name: 'Live Acme Client. Client · Vendor' }).click()
  await expect(page).toHaveURL(/\/workspaces\/organizations\/[0-9a-f-]+\/overview$/)

  await page.getByRole('link', { name: 'Custom fields' }).click()
  await expect(page).toHaveURL(/\/workspaces\/organizations\/[0-9a-f-]+\/custom_fields$/)
  await page.getByRole('button', { name: /New field/ }).click()
  await page.getByLabel('Label').fill('Support tier')
  await page.getByLabel('Stable key').fill('support_tier')
  await page.getByLabel('Field type').selectOption('choice')
  await page.getByLabel(/Choices/).fill('Standard\nPriority')
  await page.getByRole('button', { name: 'Add field' }).click()
  await expect(page.getByText('Support tier', { exact: true })).toBeVisible()

  await page.getByRole('link', { name: 'Sites' }).click()
  await expect(page).toHaveURL(/\/workspaces\/organizations\/[0-9a-f-]+\/sites$/)
  await page.getByRole('button', { name: 'New site' }).click()
  await page.getByLabel('Site name').fill('Live Main Campus')
  await page.getByLabel(/Code/).fill('MAIN')
  await page.getByLabel('Address', { exact: true }).fill('100 Main Street')
  await page.getByLabel('City').fill('Madison')
  await page.getByLabel('State or region').fill('WI')
  await page.getByLabel('Postal code').fill('53703')
  await page.getByLabel(/Country code/).fill('US')
  await page.getByLabel(/Timezone/).fill('America/Chicago')
  await page.getByRole('button', { name: 'Save site' }).click()
  await expect(page.getByText('Site added.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Add location to Live Main Campus' }).click()
  await page.getByLabel('Name').fill('Building A')
  await page.getByLabel('Type').selectOption('building')
  await page.getByRole('button', { name: 'Save location' }).click()
  await expect(page.getByText('Location added.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Add location to Live Main Campus' }).click()
  await page.getByLabel('Name').fill('Office 214')
  await page.getByLabel('Type').selectOption('office')
  await page.getByLabel('Parent').selectOption({ label: 'Building A (Building)' })
  await page.getByRole('button', { name: 'Save location' }).click()
  await expect(page.getByText('Location added.', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Office 214', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Custom fields for site Live Main Campus' }).click()
  await page.getByLabel('Support tier').selectOption('Priority')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByLabel('Support tier')).toHaveValue('Priority')

  await page.getByRole('link', { name: 'People' }).click()
  await expect(page).toHaveURL(/\/workspaces\/organizations\/[0-9a-f-]+\/people$/)
  await page.getByRole('button', { name: 'New person' }).click()
  await page.getByLabel('Full name').fill('Live Morgan Ellis')
  await page.getByLabel(/Preferred name/).fill('Morgan')
  await page.getByRole('combobox', { name: 'Relationship', exact: true }).selectOption('contact')
  await page.getByLabel(/Role/).fill('Office Manager')
  await page.getByLabel(/Responsibility/).fill('Office operations and vendor coordination')
  await page.getByLabel(/Structured site/).selectOption({ label: 'Live Main Campus' })
  await page.getByLabel(/Structured location/).selectOption({ label: 'Office 214' })
  await page.getByLabel(/Phone/).fill('+1 555 010 0299')
  await page.getByLabel(/Email/).fill('live-morgan@example.invalid')
  await page.getByRole('button', { name: 'Save person' }).click()
  await expect(page.getByText('Person added.', { exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Live Morgan Ellis', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Live Main Campus', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Office 214', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Choose visible columns' }).click()
  await page.getByRole('checkbox', { name: 'Responsibility' }).check()
  await expect(page.getByRole('cell', { name: 'Office operations and vendor coordination' })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search all person fields' }).fill('vendor coordination')
  await expect(page.getByRole('cell', { name: 'Live Morgan Ellis', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('cell', { name: 'Live Morgan Ellis', exact: true })).toBeVisible()

  await page.getByRole('link', { name: 'Documentation' }).click()
  await page.getByRole('button', { name: 'New document' }).click()
  await page.getByLabel('Document title').fill('Live Acme onboarding')
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await page.getByRole('textbox', { name: 'Markdown source' }).fill('# Acme onboarding\n\nClient-owned canonical Markdown.')
  await page.getByRole('button', { name: 'Save document' }).click()
  await expect(page.getByRole('status')).toHaveText('Document saved as revision 1.')
  await page.reload()
  await page.getByRole('button', { name: 'Live Acme onboarding' }).click()
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await page.getByRole('textbox', { name: 'Markdown source' }).fill('# Acme onboarding\n\nRevision two is retained.')
  await page.getByRole('button', { name: 'Save document' }).click()
  await expect(page.getByRole('status')).toHaveText('Document saved as revision 2.')
  await page.getByRole('button', { name: 'Revision history' }).click()
  await expect(page.getByRole('button', { name: /Revision 2.*Current/ })).toBeVisible()
  await page.getByRole('button', { name: /Revision 1/ }).click()
  await expect(page.locator('.revision-diff pre')).toContainText('# Acme onboarding')

  await page.getByRole('button', { name: /Current workspace: Live Acme Client/ }).click()
  await page.getByRole('button', { name: 'Back to Live Workspace MSP. MSP workspace' }).click()
  await page.getByRole('link', { name: 'Documentation' }).click()
  await page.getByRole('button', { name: 'New document' }).click()
  await page.getByLabel('Document title').fill('Live shared response')
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await page.getByRole('textbox', { name: 'Markdown source' }).fill('One MSP-owned block.')
  await page.getByRole('button', { name: 'Save document' }).click()
  await page.getByRole('searchbox', { name: 'Find client organization' }).fill('Live Acme')
  await page.getByRole('button', { name: /Live Acme Client/ }).click()
  await expect(page.getByRole('status')).toHaveText('Reference added to Live Acme Client.')
  await page.goto(`/workspaces/organizations/${clientId}/documentation`)
  await expect(page.getByRole('button', { name: /Live shared response.*MSP reference/ })).toBeVisible()
  await staffContext.close()
})
