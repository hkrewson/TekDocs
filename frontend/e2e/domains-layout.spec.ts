import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const organizationId = '00000000-0000-4000-8000-000000000095'
const domains = Array.from({ length: 31 }, (_, index) => ({
  id: `95000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  name: index === 30 ? 'regional-emergency-continuity-services.example.invalid' : `managed-${String(index + 1).padStart(2, '0')}.example.invalid`,
  registrar_id: null, registrar: index === 30 ? 'Long Form Registrar and DNS Services Cooperative' : 'Example Registrar',
  registration_date: '2025-01-15', expiration_date: '2027-08-12', renewal_mode: 'auto', owner_id: null,
  owner: 'Layout owner', status: 'active', notes: index === 30 ? 'Primary continuity domain with delegated renewal review.' : '',
  review_state: 'current', observed_expiration_date: '2027-08-12', last_reviewed_at: '2026-09-25T12:00:00Z',
  monitoring_enabled: true, monitor_state: 'current', monitor_error_code: '', last_monitor_at: '2026-09-25T12:00:00Z',
  next_monitor_at: '2026-09-26T12:00:00Z', created_at: '2026-09-25T12:00:00Z',
}))
const endpoints = domains.map((domain, index) => ({
  id: `95100000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`, domain_id: domain.id, hostname_id: null,
  target_name: domain.name, protocol: 'https', port: 443, monitor_state: 'current', monitor_error_code: '',
  last_monitor_at: '2026-09-25T12:00:00Z', next_monitor_at: '2026-09-26T12:00:00Z', current_leaf_sha256: 'b'.repeat(64),
  current_not_after: '2027-01-28T12:00:00Z', current_hostname_valid: true, current_trust_valid: true,
}))

async function fixtures(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: 'owner', email: 'layout@example.invalid', display_name: 'Layout owner' },
    tenant: { id: 'installation', name: 'Synthetic MSP' }, role: 'owner', permissions: [], surface: 'msp', organization: null, mfa_enrollment_required: false,
  } }))
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}`, (route) => route.fulfill({ json: {
    kind: 'organization', id: organizationId, name: 'Regional Clinical Technology Group', classifications: ['client'], capabilities: ['overview', 'domains', 'certificates'],
    organization: { id: organizationId, name: 'Regional Clinical Technology Group', legal_name: '', website: '', classifications: ['client'], access_mode: 'assigned_only', created_at: '2026-09-25T12:00:00Z', updated_at: '2026-09-25T12:00:00Z' },
  } }))
  await page.route('**/api/v1/workspaces/msp/domains**', domainResponse)
  await page.route(`**/api/v1/workspaces/organizations/${organizationId}/domains**`, domainResponse)
}

async function domainResponse(route: Route) {
  const request = route.request()
  const url = new URL(request.url())
  if (/\/certificates\/[^/]+\/monitoring$/.test(url.pathname)) {
    const id = url.pathname.split('/').at(-2)
    const endpoint = endpoints.find((item) => item.id === id)
    if (!endpoint) return route.fulfill({ status: 404, json: { detail: 'Unavailable.' } })
    return route.fulfill({ json: {
      endpoint, alerts: [], runs: [{ id: 'certificate-run-1', trigger: 'scheduled', state: 'succeeded', error_code: '', leaf_sha256: endpoint.current_leaf_sha256, chain_sha256: 'c'.repeat(64), chain_length: 2, subject_common_name: endpoint.target_name, issuer_common_name: 'Example Certificate Authority', san_count: 1, not_before: '2026-07-28T12:00:00Z', not_after: endpoint.current_not_after, hostname_valid: true, trust_valid: true, tls_version: 'TLSv1.3', cipher_name: 'TLS_AES_256_GCM_SHA384', evidence_digest: 'd'.repeat(64), created_at: '2026-09-25T12:00:00Z', finished_at: '2026-09-25T12:00:01Z' }],
    } })
  }
  if (url.pathname.endsWith('/certificates')) {
    const domainId = url.pathname.split('/').at(-2)
    return route.fulfill({ json: endpoints.filter((endpoint) => endpoint.domain_id === domainId) })
  }
  if (url.pathname.endsWith('/monitoring')) {
    const id = url.pathname.split('/').at(-2)
    const domain = domains.find((item) => item.id === id)
    if (!domain) return route.fulfill({ status: 404, json: { detail: 'Unavailable.' } })
    return route.fulfill({ json: {
      domain, hostnames: [], alerts: [{ id: 'alert-1', kind: 'dns_changed', observed_expiration_date: null, prior_expiration_date: null, created_at: '2026-09-25T12:00:00Z' }],
      runs: [{ id: 'run-1', trigger: 'scheduled', state: 'succeeded', error_code: '', rdap_source: 'rdap.example.invalid', observed_expiration_date: '2027-08-12', observed_registrar: domain.registrar, dns_source: 'doh.example.invalid', dnssec_validated: true, dns_record_count: 8, caa_record_count: 1, evidence_digest: 'a'.repeat(64), created_at: '2026-09-25T12:00:00Z', finished_at: '2026-09-25T12:00:01Z' }],
    } })
  }
  const query = (url.searchParams.get('q') ?? '').toLowerCase()
  const status = url.searchParams.get('status') ?? ''
  const page = Number(url.searchParams.get('page') ?? 1)
  const pageSize = Number(url.searchParams.get('page_size') ?? 25)
  const filtered = domains.filter((domain) => domain.name.includes(query) && (!status || domain.status === status))
  const results = filtered.slice((page - 1) * pageSize, page * pageSize)
  return route.fulfill({ json: { results, page, page_size: pageSize, count: filtered.length, has_more: page * pageSize < filtered.length, can_manage: true } })
}

async function expectContained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`domains remain focused and usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 600 : 760 })
    await fixtures(page)
    await page.goto('/domains')

    await expect(page.getByRole('heading', { name: 'Domains' })).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    const longRecord = page.getByRole('button', { name: domains[30].name })
    await expect(longRecord).toBeVisible()
    await longRecord.click()

    const drawer = page.getByRole('dialog', { name: domains[30].name })
    await expect(drawer).toBeVisible()
    await expect(drawer.getByText('Primary continuity domain with delegated renewal review.')).toBeVisible()
    await expect(drawer.getByRole('button', { name: 'Check now' })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`domain=${domains[30].id}`))
    await expect(page.evaluate(() => document.body.style.overflow)).resolves.toBe('hidden')
    if (width < 768) expect((await drawer.boundingBox())?.width).toBe(width)
    await expectContained(page)
    if (width === 390) expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(drawer).toHaveCount(0)
    await expect(page).toHaveURL(/page=2/)
    await expect(page).not.toHaveURL(/domain=/)
  })
}

test('organization direct domain links load off-page records and protect creation drafts', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 650 })
  await fixtures(page)
  await page.goto(`/workspaces/organizations/${organizationId}/domains?domain=${domains[30].id}`)

  await expect(page.getByRole('dialog', { name: domains[30].name })).toBeVisible()
  await page.goto(`/workspaces/organizations/${organizationId}/domains`)
  await page.getByRole('button', { name: 'Add domain' }).click()
  const drawer = page.getByRole('dialog', { name: 'New registered domain' })
  await drawer.getByLabel('Domain name').fill('draft.example.invalid')
  await drawer.getByRole('link', { name: 'Back to domains' }).click()
  await expect(page.getByRole('dialog', { name: 'Unsaved changes' })).toBeVisible()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByLabel('Domain name')).toHaveValue('draft.example.invalid')
  await drawer.getByRole('link', { name: 'Back to domains' }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(drawer).toHaveCount(0)
  await expect(page).not.toHaveURL(/domain=/)
})

for (const width of [320, 390, 768, 1024, 1280, 1440]) {
  test(`certificates remain focused and usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 768 ? 600 : 760 })
    await fixtures(page)
    await page.goto('/certificates')

    await expect(page.getByRole('heading', { name: 'Certificates' })).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(/page=2/)
    await page.getByRole('button', { name: domains[30].name }).click()
    const drawer = page.getByRole('dialog', { name: `Certificates · ${domains[30].name}` })
    await expect(drawer).toBeVisible()
    await drawer.getByRole('button', { name: `${domains[30].name} HTTPS certificate` }).click()
    await expect(drawer.getByText(/Example Certificate Authority/)).toBeVisible()
    await expect(drawer.getByRole('button', { name: 'Check certificate' })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`endpoint=${endpoints[30].id}`))
    if (width < 768) expect((await drawer.boundingBox())?.width).toBe(width)
    await expectContained(page)
    if (width === 390) expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([])
    await page.keyboard.press('Escape')
    await expect(drawer).toHaveCount(0)
    await expect(page).toHaveURL(/page=2/)
    await expect(page).not.toHaveURL(/domain=|endpoint=/)
  })
}

test('organization direct certificate links restore evidence and protect endpoint drafts', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 650 })
  await fixtures(page)
  await page.goto(`/workspaces/organizations/${organizationId}/certificates?domain=${domains[30].id}&endpoint=${endpoints[30].id}`)

  const drawer = page.getByRole('dialog', { name: `Certificates · ${domains[30].name}` })
  await expect(drawer.getByText(/Example Certificate Authority/)).toBeVisible()
  await drawer.getByRole('button', { name: 'Add endpoint' }).click()
  await drawer.getByLabel('Protocol').selectOption('imaps')
  await drawer.getByRole('link', { name: 'Back to certificate domains' }).click()
  await expect(page.getByRole('dialog', { name: 'Unsaved changes' })).toBeVisible()
  await page.getByRole('button', { name: 'Keep editing' }).click()
  await expect(drawer.getByLabel('Protocol')).toHaveValue('imaps')
  await drawer.getByRole('link', { name: 'Back to certificate domains' }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await expect(drawer).toHaveCount(0)
  await expect(page).not.toHaveURL(/domain=|endpoint=/)
})
