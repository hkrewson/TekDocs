import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, expect, test, vi } from 'vitest'
import { ApplicationError } from './ApplicationError'

afterEach(() => vi.restoreAllMocks())

function failRoute(error: unknown) {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
  const router = createMemoryRouter([{
    path: '*', loader: () => { throw error }, element: <p>Loaded</p>, errorElement: <ApplicationError />,
  }], { initialEntries: ['/assets?search=test#detail'] })
  render(<RouterProvider router={router} />)
}

test.each([
  'Failed to fetch dynamically imported module: https://example.invalid/assets/Assets-old.js',
  'error loading dynamically imported module: https://example.invalid/assets/Assets-old.js',
  'Importing a module script failed.',
  'Loading chunk assets-old failed.',
])('module failure offers explicit recovery: %s', async message => {
  failRoute(new TypeError(message))
  const heading = await screen.findByRole('heading', { name: 'Reload TekDocs to continue' })
  expect(heading).toHaveFocus()
  expect(screen.queryByText(message)).not.toBeInTheDocument()
  const button = screen.getByRole('button', { name: 'Reload TekDocs' })
  expect(button).toBeDisabled()
  expect(screen.getByText(/cannot recover an interrupted draft/)).toBeVisible()
  await userEvent.click(screen.getByRole('checkbox'))
  expect(button).toBeEnabled()
  await userEvent.click(screen.getByRole('checkbox'))
  expect(button).toBeDisabled()
})

test.each([new Error('Failed to fetch'), new Error('private backend diagnostic'), { message: 'untrusted details' }, null])(
  'unrelated failures do not claim an update or disclose diagnostics: %s', async error => {
    failRoute(error)
    expect(await screen.findByRole('heading', { name: 'This page could not open' })).toBeVisible()
    expect(screen.queryByText(/may have been updated/)).not.toBeInTheDocument()
    expect(screen.queryByText(/private backend diagnostic|untrusted details/)).not.toBeInTheDocument()
  },
)
