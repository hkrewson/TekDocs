import type { Page } from '@playwright/test'

export async function openDocumentMoreAction(page: Page, name: 'Document settings' | 'Export') {
  const action = page.getByRole('button', { name, exact: true })
  if (!await action.isVisible()) {
    await page.getByRole('button', { name: 'More', exact: true }).click()
  }
  await action.click()
}
