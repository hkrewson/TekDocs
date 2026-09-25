import { render as rawRender, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApplicationRouter } from '../navigation/ApplicationRouter'
import { CredentialReferences } from './CredentialReferences'
import type { CredentialReferencesClient } from './api'

const reference = {
  id: 'reference-1',
  title: 'Firewall administrator',
  provider: 'onepassword' as const,
  provider_label: '1Password',
  updated_at: '2026-08-09T12:00:00Z',
  can_manage: true,
  can_open: true,
}

function client(overrides: Partial<CredentialReferencesClient> = {}): CredentialReferencesClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [reference], page: 1, page_size: 25, count: 1, has_more: false, can_manage: true }),
    retrieve: vi.fn().mockResolvedValue(reference),
    create: vi.fn().mockResolvedValue(reference),
    update: vi.fn().mockResolvedValue(reference),
    archive: vi.fn().mockResolvedValue(undefined),
    openUrl: vi.fn().mockReturnValue('/api/v1/credential-references/reference-1/open'),
    ...overrides,
  }
}

function renderView(api: CredentialReferencesClient, path = '/credentials') {
  return rawRender(<ApplicationRouter initialPath={path}><CredentialReferences workspace={null} client={api} /></ApplicationRouter>)
}

describe('CredentialReferences', () => {
  it('opens a useful record drawer from the compact list', async () => {
    const api = client()
    const user = userEvent.setup()
    renderView(api)
    expect(await screen.findByText('Credentials stay in 1Password')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Firewall administrator/ }))

    const drawer = screen.getByRole('dialog', { name: 'Firewall administrator' })
    expect(within(drawer).getByText(/credential itself remains in 1Password/)).toBeInTheDocument()
    expect(within(drawer).getByText('Last updated')).toBeInTheDocument()
    const link = within(drawer).getByRole('link', { name: /Open in 1Password/ })
    expect(link).toHaveAttribute('href', '/api/v1/credential-references/reference-1/open')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.queryByText(/Envelope encryption/)).not.toBeInTheDocument()
  })

  it('creates only a title, provider, and private-link pointer in the drawer', async () => {
    const create = vi.fn().mockResolvedValue({ ...reference, id: 'reference-2' })
    const api = client({ create })
    const user = userEvent.setup()
    renderView(api)
    await user.click(await screen.findByRole('button', { name: 'New link' }))
    const drawer = screen.getByRole('dialog', { name: 'New credential link' })
    await user.type(within(drawer).getByLabelText('Title'), 'Firewall administrator')
    await user.type(within(drawer).getByPlaceholderText('https://start.1password.com/open/i?…'), 'https://start.1password.com/open/i?private')
    expect(within(drawer).getAllByRole('textbox')).toHaveLength(2)
    await user.click(within(drawer).getByRole('button', { name: 'Save link' }))
    await waitFor(() => expect(create).toHaveBeenCalledWith(null, {
      title: 'Firewall administrator',
      provider: 'onepassword',
      reference_url: 'https://start.1password.com/open/i?private',
    }))
    expect(await screen.findByRole('dialog', { name: 'Firewall administrator' })).toBeInTheDocument()
  })

  it('guards a dirty drawer and preserves the draft when the technician keeps editing', async () => {
    const user = userEvent.setup()
    renderView(client())
    await user.click(await screen.findByRole('button', { name: /Firewall administrator/ }))
    const drawer = screen.getByRole('dialog', { name: 'Firewall administrator' })
    await user.click(within(drawer).getByRole('button', { name: 'Edit' }))
    const title = within(drawer).getByLabelText('Title')
    await user.clear(title)
    await user.type(title, 'Core firewall administrator')
    await user.click(within(drawer).getByRole('link', { name: 'Back to credential links' }))
    const warning = (await screen.findByText('Unsaved changes')).closest('dialog') as HTMLElement
    await user.click(within(warning).getByRole('button', { name: 'Keep editing' }))
    expect(within(drawer).getByLabelText('Title')).toHaveValue('Core firewall administrator')
  })

  it('keeps archive language explicit about leaving the provider item untouched', async () => {
    const api = client()
    const user = userEvent.setup()
    renderView(api)
    await user.click(await screen.findByRole('button', { name: /Firewall administrator/ }))
    await user.click(within(screen.getByRole('dialog', { name: 'Firewall administrator' })).getByRole('button', { name: 'Archive' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('The item and its access in 1Password will not change')
  })

  it('uses URL paging and page-size state with the bounded API', async () => {
    const list = vi.fn().mockResolvedValue({ results: [{ ...reference, id: 'reference-51', title: 'Last reference' }], page: 2, page_size: 50, count: 51, has_more: false, can_manage: true })
    renderView(client({ list }), '/credentials?page=2&page_size=50&q=firewall')

    expect(await screen.findByText('Last reference')).toBeInTheDocument()
    expect(list).toHaveBeenLastCalledWith(null, 'firewall', 2, 50, expect.any(AbortSignal))
    expect(screen.getByRole('combobox', { name: 'Rows per page' })).toHaveValue('50')
  })

  it('loads a directly linked record outside the current page and retries unavailable details', async () => {
    const retrieve = vi.fn().mockRejectedValueOnce(new Error('missing')).mockResolvedValueOnce(reference)
    const api = client({
      list: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false, can_manage: true }),
      retrieve,
    })
    const user = userEvent.setup()
    renderView(api, '/credentials?credential=reference-1')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('unavailable or you no longer have access')
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('dialog', { name: 'Firewall administrator' })).toBeInTheDocument()
    expect(retrieve).toHaveBeenCalledTimes(2)
  })
})
