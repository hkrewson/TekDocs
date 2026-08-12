import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Domains } from './Domains'
import type { DomainsClient } from './api'

describe('Domains', () => {
  it('creates a workspace-owned registration record', async () => {
    const client: DomainsClient = {
      list: vi.fn().mockResolvedValue([]),
      create: vi.fn().mockResolvedValue({
        id: 'domain-1', name: 'example.com', registrar_id: null, registrar: null,
        registration_date: null, expiration_date: '2027-08-12', renewal_mode: 'auto',
        owner_id: null, owner: null, status: 'active', notes: '', created_at: '2026-08-12T00:00:00Z',
      }),
    }
    const user = userEvent.setup()
    render(<Domains workspace={null} client={client} />)

    await screen.findByText('No registered domains are recorded in this workspace.')
    await user.click(screen.getByRole('button', { name: 'Add domain' }))
    await user.type(screen.getByLabelText('Domain name'), 'example.com')
    await user.selectOptions(screen.getByLabelText('Renewal'), 'auto')
    await user.type(screen.getByLabelText('Expires on'), '2027-08-12')
    await user.click(screen.getByRole('button', { name: 'Save domain' }))

    await waitFor(() => expect(client.create).toHaveBeenCalledWith(null, expect.objectContaining({
      name: 'example.com', renewal_mode: 'auto', expiration_date: '2027-08-12',
    })))
    expect(await screen.findByText('example.com')).toBeInTheDocument()
  })
})
