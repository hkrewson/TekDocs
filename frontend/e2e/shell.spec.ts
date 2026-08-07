import { expect, test } from '@playwright/test'

test('application shell exposes primary navigation and backend health', async ({ page, request }) => {
  const health = await request.get('/api/v1/health/ready')
  expect(health.ok()).toBeTruthy()

  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await page.getByRole('link', { name: 'Documentation' }).click()
  await expect(page.getByRole('heading', { name: 'Documentation' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Editor' })).toBeVisible()
})

test('raw Markdown remains the editable canonical representation', async ({ page }) => {
  await page.goto('/documentation')
  await page.getByRole('tab', { name: 'Markdown' }).click()
  const source = page.getByLabel('Markdown source')
  await expect(source).toHaveValue(/# Firewall replacement/)
  await source.fill('# Updated procedure\n\nUse **approved** access.')
  await page.getByRole('tab', { name: 'Editor' }).click()
  await page.getByRole('tab', { name: 'Markdown' }).click()
  await expect(source).toHaveValue('# Updated procedure\n\nUse **approved** access.')
})

test('mobile navigation is operable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/overview')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('link', { name: 'Documentation' })).toBeVisible()
  await page.getByRole('button', { name: 'Close navigation' }).first().click()
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
})
