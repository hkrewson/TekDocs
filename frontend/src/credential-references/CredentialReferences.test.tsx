import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

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
    list: vi.fn().mockResolvedValue({ results: [reference], page: 1, page_size: 50, count: 1, has_more: false, can_manage: true }),
    create: vi.fn().mockResolvedValue(reference),
    update: vi.fn().mockResolvedValue(reference),
    archive: vi.fn().mockResolvedValue(undefined),
    openUrl: vi.fn().mockReturnValue('/api/v1/credential-references/reference-1/open'),
    ...overrides,
  }
}

describe('CredentialReferences', () => {
  it('explains that credentials stay in 1Password and uses the TekDocs open link', async () => {
    const api = client()
    render(<CredentialReferences workspace={null} client={api} />)
    expect(await screen.findByText('Firewall administrator')).toBeInTheDocument()
    expect(screen.getByText('Credentials stay in 1Password')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Open in 1Password/ })
    expect(link).toHaveAttribute('href', '/api/v1/credential-references/reference-1/open')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.queryByText(/Envelope encryption/)).not.toBeInTheDocument()
  })

  it('creates only a title, provider, and private-link pointer', async () => {
    const create = vi.fn().mockResolvedValue({ ...reference, id: 'reference-2' })
    const api = client({ create })
    const user = userEvent.setup()
    render(<CredentialReferences workspace={null} client={api} />)
    await user.click(await screen.findByRole('button', { name: 'New link' }))
    const form = screen.getByRole('heading', { name: 'New credential link' }).closest('section')!
    await user.type(within(form).getByLabelText('Title'), 'Firewall administrator')
    await user.type(within(form).getByPlaceholderText('https://start.1password.com/open/i?…'), 'https://start.1password.com/open/i?private')
    expect(within(form).getAllByRole('textbox')).toHaveLength(2)
    await user.click(within(form).getByRole('button', { name: 'Save link' }))
    await waitFor(() => expect(create).toHaveBeenCalledWith(null, {
      title: 'Firewall administrator',
      provider: 'onepassword',
      reference_url: 'https://start.1password.com/open/i?private',
    }))
  })

  it('keeps archive language explicit about leaving the provider item untouched', async () => {
    const api = client()
    const user = userEvent.setup()
    render(<CredentialReferences workspace={null} client={api} />)
    await user.click(await screen.findByRole('button', { name: 'Archive Firewall administrator' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('The item and its access in 1Password will not change')
  })

  it('explains broken links and changes pages through the bounded API', async () => {
    const list = vi.fn()
      .mockResolvedValueOnce({ results: [reference], page: 1, page_size: 50, count: 51, has_more: true, can_manage: true })
      .mockResolvedValueOnce({ results: [{ ...reference, id: 'reference-51', title: 'Last reference' }], page: 2, page_size: 50, count: 51, has_more: false, can_manage: true })
    const user = userEvent.setup()
    render(<CredentialReferences workspace={null} client={client({ list })} />)

    expect(await screen.findByText(/If a link stops working/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Last reference')).toBeInTheDocument()
    expect(list).toHaveBeenLastCalledWith(null, '', 2, expect.any(AbortSignal))
  })
})
