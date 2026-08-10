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
    list: vi.fn().mockResolvedValue({ results: [reference], can_manage: true }),
    create: vi.fn().mockResolvedValue(reference),
    update: vi.fn().mockResolvedValue(reference),
    archive: vi.fn().mockResolvedValue(undefined),
    openUrl: vi.fn().mockReturnValue('/api/v1/credential-references/reference-1/open'),
    ...overrides,
  }
}

describe('CredentialReferences', () => {
  it('explains external custody and opens only through the audited TekDocs handoff', async () => {
    const api = client()
    render(<CredentialReferences workspace={null} client={api} />)
    expect(await screen.findByText('Firewall administrator')).toBeInTheDocument()
    expect(screen.getByText(/1Password remains the security boundary/)).toBeInTheDocument()
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
    await user.click(await screen.findByRole('button', { name: 'New reference' }))
    const form = screen.getByRole('heading', { name: 'New credential reference' }).closest('section')!
    await user.type(within(form).getByLabelText('Title'), 'Firewall administrator')
    await user.type(within(form).getByPlaceholderText('https://start.1password.com/open/i?…'), 'https://start.1password.com/open/i?private')
    expect(within(form).getAllByRole('textbox')).toHaveLength(2)
    await user.click(within(form).getByRole('button', { name: 'Save reference' }))
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
    expect(screen.getByRole('alertdialog')).toHaveTextContent('The 1Password item and its access remain unchanged')
  })
})
