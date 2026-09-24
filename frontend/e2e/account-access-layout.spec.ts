import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const members = [
  { id: 'owner', display_name: 'Layout Owner', email: 'layout@example.invalid', role: 'owner', is_owner: true, joined_at: null },
  { id: 'technician', display_name: 'Morgan Ellis with a deliberately long operational name', email: 'morgan.ellis.with-a-long-address@example.invalid', role: 'technician', is_owner: false, joined_at: '2026-09-01T12:00:00Z' },
]
const organizations = Array.from({ length: 8 }, (_, index) => ({
  id: `organization-${index}`, name: `Client ${index + 1} with a long service location name`, access_mode: index % 2 ? 'assigned_only' : 'all_authorized',
  assigned_staff: index % 2 ? [{ ...members[1], role: 'technician' }] : [],
}))
const invitations = Array.from({ length: 31 }, (_, index) => ({
  id: `invitation-${index}`, email: `technician-${String(index + 1).padStart(2, '0')}.with-a-long-address@example.invalid`, role: 'read_only', organization: null,
  state: index % 4 === 0 ? 'accepted' : 'pending', expires_at: '2026-10-20T12:00:00Z', last_sent_at: '2026-09-20T12:00:00Z',
  last_delivery_failed_at: null, delivery_attempts: index + 1, send_count: index + 1, created_at: '2026-09-20T12:00:00Z', updated_at: '2026-09-20T12:00:00Z',
}))

async function fixtures(page: Page) {
  await page.context().addCookies([{ name: 'csrftoken', value: 'account-layout-csrf', url: 'http://localhost:3200' }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: members[0], tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', surface: 'msp', organization: null, mfa_enrollment_required: false,
    permissions: ['staff_invitations.view', 'memberships.view', 'memberships.assign_role', 'organizations.manage_access', 'organizations.assign_staff', 'integrations.manage'],
  } }))
  await page.route('**/_allauth/browser/v1/auth/sessions', (route) => route.fulfill({ json: { data: [
    { id: 1, user_agent: 'Chrome/150.0 Macintosh', ip: '192.0.2.10', created_at: 1_790_000_000, last_seen_at: 1_790_003_600, is_current: true },
    { id: 2, user_agent: 'Firefox/150.0 Windows', ip: '2001:db8:85a3::8a2e:370:7334', created_at: 1_789_000_000, last_seen_at: 1_789_003_600, is_current: false },
  ] } }))
  await page.route('**/_allauth/browser/v1/account/authenticators', (route) => route.fulfill({ json: { data: [] } }))
  await page.route('**/api/v1/auth/api-tokens', (route) => route.fulfill({ json: { tokens: [], permissions: [{ key: 'documents.view', label: 'View documentation', category: 'Documentation', requires_mfa: false, service_eligible: true }] } }))
  await page.route('**/api/v1/invitations', (route) => route.fulfill({ json: invitations }))
  await page.route('**/api/v1/access-control/catalog', (route) => route.fulfill({ json: {
    permissions: [], custom_assignable_permissions: [], roles: [
      { value: 'owner', label: 'Owner', description: 'Installation owner.', assignable_scope: 'installation', permissions: [] },
      { value: 'administrator', label: 'Administrator', description: 'All MSP administration.', assignable_scope: 'tenant', permissions: [] },
      { value: 'technician', label: 'Technician', description: 'Operational work.', assignable_scope: 'tenant', permissions: [] },
      { value: 'contributor', label: 'Contributor', description: 'Contributes records.', assignable_scope: 'tenant', permissions: [] },
      { value: 'read_only', label: 'Read-only', description: 'Reads records.', assignable_scope: 'tenant', permissions: [] },
      { value: 'client_administrator', label: 'Client Administrator', description: 'Client administration.', assignable_scope: 'organization', permissions: [] },
      { value: 'client_user', label: 'Client User', description: 'Client reading.', assignable_scope: 'organization', permissions: [] },
    ],
  } }))
  await page.route('**/api/v1/access-control/members', (route) => route.fulfill({ json: members }))
  await page.route('**/api/v1/access-control/organizations', (route) => route.fulfill({ json: organizations }))
}

async function expectContained(page: Page) {
  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: innerWidth,
    offenders: [...document.querySelectorAll<HTMLElement>('body *')]
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 5)
      .map((element) => ({ tag: element.tagName, className: element.className, right: Math.round(element.getBoundingClientRect().right), width: element.scrollWidth })),
  }))
  expect(overflow, JSON.stringify(overflow)).toMatchObject({ documentWidth: overflow.viewportWidth })
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`account and access administration fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 560 : 700 })
    await fixtures(page)

    await page.goto('/settings?section=sessions')
    await expect(page.getByRole('heading', { name: 'Active sessions' })).toBeVisible()
    await expect(page.getByText('Firefox on Windows')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Profile' })).toHaveCount(0)
    await expectContained(page)

    await page.goto('/settings?section=api-tokens')
    await page.getByRole('button', { name: 'New token' }).click()
    const tokenEditor = page.getByRole('dialog', { name: 'New token' })
    await expect(tokenEditor).toBeVisible()
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    await tokenEditor.getByRole('button', { name: 'Cancel' }).click()
    await expect(tokenEditor).toHaveCount(0)

    await page.goto('/staff?section=invitations')
    await expect(page.getByRole('list', { name: 'Staff invitation history' })).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    await page.getByPlaceholder('Search email').fill('technician-31')
    await expect(page).toHaveURL(/q=technician-31/)
    await expect(page).not.toHaveURL(/page=2/)
    await page.getByRole('button', { name: 'Invite staff' }).click()
    const inviteEditor = page.getByRole('dialog', { name: 'Invite staff' })
    await expect(inviteEditor).toBeVisible()
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    await inviteEditor.getByRole('button', { name: 'Cancel' }).click()
    await expectContained(page)

    await page.goto('/access-control?section=assignments')
    await expect(page.getByRole('heading', { name: 'Staff assignments' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Built-in roles' })).toHaveCount(0)
    await expectContained(page)

    if (width === 390) expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([])
  })
}
