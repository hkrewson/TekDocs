import { expect, type Page } from '@playwright/test'

/** Await the selected Git read before spending the rendering assertion budget. */
export async function openRepositoryDocument(page: Page, pagePath: string, readPath: string) {
  const [response] = await Promise.all([
    page.waitForResponse(response => new URL(response.url()).pathname === readPath && response.request().method() === 'GET'),
    page.goto(pagePath),
  ])
  expect(response.status()).toBe(200)
  expect(await response.finished()).toBeNull()
}
