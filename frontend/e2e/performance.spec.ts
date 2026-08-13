import { expect, test } from '@playwright/test'
import type { Browser, Page } from '@playwright/test'

const enabled = process.env.TEKDOCS_PERFORMANCE_REHEARSAL === 'true'
const authContext = {
  user: { id: crypto.randomUUID(), email: 'owner@example.invalid', display_name: 'Capacity Owner' },
  tenant: { id: crypto.randomUUID(), name: 'Capacity MSP' },
}
const documentRecord = {
  id: crypto.randomUUID(),
  title: 'Capacity Runbook',
  owner_kind: 'msp',
  owner_organization_id: null,
  owner_organization_name: null,
  is_reference: false,
  category: 'guide',
  is_template: false,
  markdown: '# Capacity Runbook\n\nUse **approved** access.\n',
  block_id: crypto.randomUUID(),
  current_revision_id: crypto.randomUUID(),
  revision_number: 1,
  checksum: '0'.repeat(64),
  resolved_markdown: '# Capacity Runbook\n\nUse **approved** access.\n',
  placements: [],
  placement_count: 0,
  attachments: [],
  attachment_count: 0,
  publications: [],
  publication_count: 0,
  created_at: '2026-08-13T12:00:00Z',
  updated_at: '2026-08-13T12:00:00Z',
}

async function mockAuthenticated(page: Page) {
  await page.route('**/api/v1/bootstrap/status', (route) => route.fulfill({ json: { bootstrap_required: false } }))
  await page.route('**/_allauth/browser/v1/auth/session', (route) => route.fulfill({
    status: 200,
    json: { status: 200, meta: { is_authenticated: true }, data: { user: authContext.user } },
  }))
  await page.route('**/api/v1/auth/context', (route) => route.fulfill({ json: authContext }))
  await page.route('**/api/v1/documents*', (route) => route.fulfill({ json: { results: [documentRecord], count: 1 } }))
}

type ResourceMetric = { name: string; initiatorType: string; decodedBodySize: number; transferSize: number }

async function resources(page: Page): Promise<ResourceMetric[]> {
  return page.evaluate(() => performance.getEntriesByType('resource').map((entry) => {
    const resource = entry as unknown as ResourceMetric
    return {
      name: resource.name,
      initiatorType: resource.initiatorType,
      decodedBodySize: resource.decodedBodySize,
      transferSize: resource.transferSize,
    }
  }))
}

async function measureProfile(
  browser: Browser,
  profile: { name: string; width: number; height: number; cpuRate: number; latency: number; download: number },
) {
  const context = await browser.newContext({ viewport: { width: profile.width, height: profile.height } })
  const page = await context.newPage()
  const session = await context.newCDPSession(page)
  await session.send('Emulation.setCPUThrottlingRate', { rate: profile.cpuRate })
  await session.send('Network.enable')
  await session.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: profile.latency,
    downloadThroughput: profile.download,
    uploadThroughput: 750 * 1024 / 8,
    connectionType: 'cellular4g',
  })
  await mockAuthenticated(page)

  const shellStarted = Date.now()
  await page.goto('/documentation')
  await expect(page.getByRole('heading', { name: 'Documentation' })).toBeVisible()
  const shellReadyMs = Date.now() - shellStarted
  const beforeEditor = await resources(page)
  expect(beforeEditor.some((entry) => entry.name.includes('EditorSpike-'))).toBe(false)

  const editorStarted = Date.now()
  await page.getByRole('button', { name: 'Capacity Runbook' }).click()
  await expect(page.locator('.milkdown-host [contenteditable="true"]')).toBeVisible({ timeout: 12_000 })
  const editorReadyMs = Date.now() - editorStarted
  const afterEditor = await resources(page)
  const initialJavaScript = beforeEditor
    .filter((entry) => entry.initiatorType === 'script')
    .reduce((total, entry) => total + entry.decodedBodySize, 0)
  const editorJavaScript = afterEditor
    .filter((entry) => entry.initiatorType === 'script' && !beforeEditor.some((before) => before.name === entry.name))
    .reduce((total, entry) => total + entry.decodedBodySize, 0)

  expect(shellReadyMs, `${profile.name} shell ready time`).toBeLessThan(8_000)
  expect(editorReadyMs, `${profile.name} editor ready time`).toBeLessThan(12_000)
  expect(initialJavaScript, `${profile.name} initial decoded JavaScript`).toBeLessThan(900 * 1024)
  expect(editorJavaScript, `${profile.name} editor decoded JavaScript`).toBeLessThan(1_500 * 1024)
  expect(afterEditor.some((entry) => entry.name.includes('EditorSpike-'))).toBe(true)
  await context.close()
  return { ...profile, shellReadyMs, editorReadyMs, initialJavaScript, editorJavaScript }
}

test('constrained desktop and mobile profiles keep the editor out of the shell path', async ({ browser }, testInfo) => {
  test.skip(!enabled, 'Run through make test-public-beta-performance.')
  test.skip(testInfo.project.name !== 'chromium', 'Deterministic CPU/network emulation is Chromium-only.')

  const measurements = []
  measurements.push(await measureProfile(browser, {
    name: 'constrained desktop', width: 1440, height: 900, cpuRate: 4, latency: 80, download: 2_000 * 1024 / 8,
  }))
  measurements.push(await measureProfile(browser, {
    name: 'constrained mobile', width: 390, height: 844, cpuRate: 6, latency: 120, download: 1_600 * 1024 / 8,
  }))
  console.log(JSON.stringify({ measurements }))
  await testInfo.attach('performance-metrics.json', {
    body: Buffer.from(JSON.stringify({ measurements }, null, 2)),
    contentType: 'application/json',
  })
})
