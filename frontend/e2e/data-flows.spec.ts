import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const wcag22Tags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

const choices = {
  endpoint_kinds: [{ value: 'internal', label: 'Internal record' }, { value: 'external', label: 'External party' }],
  directions: [{ value: 'one_way', label: 'One way' }, { value: 'bidirectional', label: 'Bidirectional' }],
  transfer_mechanisms: [{ value: 'api', label: 'API' }, { value: 'email', label: 'Email' }],
  data_classifications: [{ value: 'internal', label: 'Internal' }, { value: 'personal_data', label: 'Personal data' }],
  protections: [{ value: 'unknown', label: 'Unknown' }, { value: 'in_transit', label: 'Encrypted in transit' }],
  provenance_states: [
    { value: 'recorded_fact', label: 'Recorded fact' },
    { value: 'imported_observation', label: 'Imported observation' },
    { value: 'unverified_draft', label: 'Unverified draft' },
  ],
}

function revision(overrides: Record<string, unknown> = {}) {
  return {
    id: crypto.randomUUID(),
    revision_number: 1,
    source_kind: 'external',
    source_entity_id: null,
    source_display_name: 'Practice vendor',
    source_label: 'Practice vendor',
    destination_kind: 'external',
    destination_entity_id: null,
    destination_display_name: 'Payment processor',
    destination_label: 'Payment processor',
    direction: 'one_way',
    transfer_mechanism: 'api',
    data_classification: 'personal_data',
    purpose: 'Settle patient billing.',
    crosses_trust_boundary: true,
    protection: 'in_transit',
    owner_entity_id: null,
    owner_display_name: '',
    review_due_on: null,
    provenance: 'recorded_fact',
    content_digest: 'a'.repeat(64),
    created_at: '2026-08-20T12:00:00Z',
    ...overrides,
  }
}

test.beforeEach(async ({ page, baseURL }) => {
  const tenantId = crypto.randomUUID()
  await page.context().addCookies([{ name: 'csrftoken', value: crypto.randomUUID().replaceAll('-', ''), url: baseURL }])
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({ json: { meta: { is_authenticated: true } } }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: {
    user: { id: crypto.randomUUID(), email: 'owner@example.com', display_name: 'Primary Owner' },
    tenant: { id: tenantId, name: 'Example MSP' },
    permissions: ['data_flows.view', 'data_flows.edit', 'compliance.view'],
  } }))
  await page.route('**/compliance/frameworks**', (route) => route.fulfill({ json: { results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true } }))
  await page.route('**/compliance/evidence**', (route) => route.fulfill({ json: { results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true } }))
  // The risks payload carries a summary the page reads unconditionally; omitting it
  // throws during render and takes the whole subtree, including this section, with it.
  await page.route('**/compliance/risks**', (route) => route.fulfill({ json: {
    results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true,
    owner_choices: [], summary: { total: 0, by_status: {}, by_band: {}, overdue: 0 },
  } }))
  // `bundles` returns a bare array, not the usual envelope.
  await page.route('**/compliance/bundles**', (route) => route.fulfill({ json: [] }))
  await page.route(/\/compliance\/data-flows\/choices$/, (route) => route.fulfill({ json: choices }))
})

test('a recorded flow and an unverified draft are told apart without relying on colour', async ({ page }) => {
  await page.route(/\/compliance\/data-flows(\?|$)/, (route) => route.fulfill({ json: {
    results: [
      { id: crypto.randomUUID(), name: 'Billing export', revision_count: 1, current_revision: revision(), created_at: '2026-08-20T12:00:00Z', updated_at: '2026-08-20T12:00:00Z' },
      { id: crypto.randomUUID(), name: 'Proposed telemetry', revision_count: 1, current_revision: revision({ provenance: 'unverified_draft' }), created_at: '2026-08-20T12:00:00Z', updated_at: '2026-08-20T12:00:00Z' },
    ],
    page: 1, page_size: 50, count: 2, has_more: false, can_manage: true,
  } }))

  await page.goto('/compliance')
  await expect(page.getByRole('heading', { name: 'Data flows' })).toBeVisible()

  // The distinction has to survive the loss of colour entirely, because that is what a
  // screen reader, a printed page, and forced-colours mode all amount to.
  await expect(page.getByText(/Unverified draft/)).toContainText('not evidence')
  await expect(page.getByText('Recorded fact')).not.toContainText('not evidence')

  await expect(new AxeBuilder({ page }).include('.compliance-data-flows').withTags(wcag22Tags).analyze())
    .resolves.toMatchObject({ violations: [] })

  // Forced colours replace the palette entirely, so anything still legible here is
  // carried by text rather than by colour. Run it last: contrast rules are not
  // meaningful once the browser has overridden the colours.
  await page.emulateMedia({ forcedColors: 'active' })
  await expect(page.getByText(/Unverified draft/)).toContainText('not evidence')
  await expect(page.getByText('Recorded fact')).not.toContainText('not evidence')
})

test('the flow table and its authoring form are reachable and operable by keyboard', async ({ page }) => {
  const created: Record<string, unknown>[] = []
  await page.route(/\/compliance\/data-flows(\?|$)/, (route) => route.fulfill({ json: {
    results: [{ id: crypto.randomUUID(), name: 'Billing export', revision_count: 1, current_revision: revision(), created_at: '2026-08-20T12:00:00Z', updated_at: '2026-08-20T12:00:00Z' }],
    page: 1, page_size: 50, count: 1, has_more: false, can_manage: true,
  } }))
  await page.route(/\/compliance\/data-flows$/, (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    created.push(route.request().postDataJSON() as Record<string, unknown>)
    return route.fulfill({ status: 201, json: { id: crypto.randomUUID(), name: 'Keyboard flow', revision_count: 1, current_revision: revision(), created_at: '2026-08-20T12:00:00Z', updated_at: '2026-08-20T12:00:00Z' } })
  })

  await page.goto('/compliance')
  const scrollRegion = page.getByRole('group', { name: 'Data flows' })
  await expect(scrollRegion).toBeVisible()
  // A scrollable region must be focusable, or a keyboard user cannot scroll it at all.
  await scrollRegion.focus()
  await expect(scrollRegion).toBeFocused()

  await page.getByRole('button', { name: 'Declare data flow' }).click()
  await page.getByLabel('Name').fill('Keyboard flow')
  await page.getByLabel('Purpose').fill('Declared without a mouse.')
  await page.getByLabel('Source').fill('Origin')
  await page.getByLabel('Destination').fill('Target')
  await page.getByRole('button', { name: 'Save data flow' }).press('Enter')

  await expect.poll(() => created.length).toBe(1)
  await expect(new AxeBuilder({ page }).include('.compliance-data-flows').withTags(wcag22Tags).analyze())
    .resolves.toMatchObject({ violations: [] })
})

test('a member who may not read data flows sees no trace of the section', async ({ page }) => {
  await page.route(/\/compliance\/data-flows(\?|$)/, (route) => route.fulfill({ status: 403, json: { error: { code: 'permission_denied' } } }))

  await page.goto('/compliance')
  await expect(page.getByRole('heading', { name: 'Compliance' })).toBeVisible()

  // A refused section renders nothing rather than an error, because the refusal is a
  // statement about scope, not a failure the reader can act on.
  await expect(page.getByRole('heading', { name: 'Data flows' })).toHaveCount(0)
  await expect(page.getByText(/not evidence/)).toHaveCount(0)
})
