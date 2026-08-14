import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import { AuthRequestError } from '../auth/api'
import type { Member } from '../access-control/api'
import type { StaffAdministrationClient, StaffInvitation } from './api'
import { StaffAdministration } from './StaffAdministration'

const owner: Member = { id: 'owner', display_name: 'Primary Owner', email: 'owner@example.com', role: 'owner', is_owner: true, joined_at: null }
const invitation: StaffInvitation = {
  id: 'invitation', email: 'technician@example.com', role: 'read_only', organization: null, state: 'pending',
  expires_at: '2026-08-20T12:00:00Z', last_sent_at: '2026-08-13T12:00:00Z', last_delivery_failed_at: null,
  delivery_attempts: 1, send_count: 1, created_at: '2026-08-13T12:00:00Z', updated_at: '2026-08-13T12:00:00Z',
}

function client(overrides: Partial<StaffAdministrationClient> = {}): StaffAdministrationClient {
  return {
    members: vi.fn().mockResolvedValue([owner]),
    invitations: vi.fn().mockResolvedValue([invitation]),
    issue: vi.fn().mockResolvedValue({ ...invitation, id: 'new', email: 'new@example.com' }),
    resend: vi.fn().mockResolvedValue({ ...invitation, delivery_attempts: 2, send_count: 2 }),
    revoke: vi.fn().mockResolvedValue({ ...invitation, state: 'revoked' }),
    ...overrides,
  }
}

describe('staff administration', () => {
  it('lists MSP members separately from invitation history and links to access control', async () => {
    render(<MemoryRouter><StaffAdministration client={client()} /></MemoryRouter>)

    expect(await screen.findByRole('heading', { name: 'Staff & invitations' })).toBeInTheDocument()
    expect(await screen.findByText('Primary Owner')).toBeInTheDocument()
    expect(screen.getByText('technician@example.com')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open access control/ })).toHaveAttribute('href', '/access-control')
  })

  it('issues a read-only invitation without handling its token', async () => {
    const issue = vi.fn().mockResolvedValue({ ...invitation, id: 'new', email: 'new@example.com' })
    const user = userEvent.setup()
    render(<MemoryRouter><StaffAdministration client={client({ issue })} /></MemoryRouter>)

    await screen.findByText('Primary Owner')
    await user.type(screen.getByRole('textbox', { name: 'Email address' }), 'new@example.com')
    await user.click(screen.getByRole('button', { name: 'Send invitation' }))

    await waitFor(() => expect(issue).toHaveBeenCalledWith('new@example.com'))
    expect(screen.getByRole('status')).toHaveTextContent('begin with Read-only access')
    expect(screen.getByText('new@example.com')).toBeInTheDocument()
  })

  it('reviews resend and revoke before changing an invitation', async () => {
    const resend = vi.fn().mockResolvedValue({ ...invitation, delivery_attempts: 2, send_count: 2 })
    const revoke = vi.fn().mockResolvedValue({ ...invitation, state: 'revoked' })
    const user = userEvent.setup()
    render(<MemoryRouter><StaffAdministration client={client({ resend, revoke })} /></MemoryRouter>)

    const history = await screen.findByRole('table', { name: 'MSP staff invitation history' })
    await user.click(within(history).getByRole('button', { name: 'Resend' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('prior link will stop working')
    await user.click(screen.getByRole('button', { name: 'Send replacement' }))
    await waitFor(() => expect(resend).toHaveBeenCalledWith(invitation.id))

    await user.click(within(history).getByRole('button', { name: 'Revoke' }))
    await user.click(screen.getByRole('button', { name: 'Revoke invitation' }))
    await waitFor(() => expect(revoke).toHaveBeenCalledWith(invitation.id))
    expect(within(history).getByText('Revoked')).toBeInTheDocument()
  })

  it('reloads retained state after an SMTP delivery failure', async () => {
    const failed = { ...invitation, last_sent_at: null, last_delivery_failed_at: '2026-08-13T12:01:00Z', send_count: 0 }
    const invitations = vi.fn().mockResolvedValueOnce([]).mockResolvedValueOnce([failed])
    const issue = vi.fn().mockRejectedValue(new AuthRequestError('The invitation was retained, but email delivery failed.', 503))
    const user = userEvent.setup()
    render(<MemoryRouter><StaffAdministration client={client({ invitations, issue })} /></MemoryRouter>)

    await screen.findByText('Primary Owner')
    await user.type(screen.getByRole('textbox', { name: 'Email address' }), invitation.email)
    await user.click(screen.getByRole('button', { name: 'Send invitation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('retained, but email delivery failed')
    expect(within(await screen.findByRole('table', { name: 'MSP staff invitation history' })).getByText('Delivery failed')).toBeInTheDocument()
  })

  it('paginates the bounded invitation history and resets the page when filtering', async () => {
    const records = Array.from({ length: 26 }, (_, index) => ({
      ...invitation,
      id: `invitation-${index}`,
      email: `staff-${String(index).padStart(2, '0')}@example.com`,
    }))
    const user = userEvent.setup()
    render(<MemoryRouter><StaffAdministration client={client({ invitations: vi.fn().mockResolvedValue(records) })} /></MemoryRouter>)

    await screen.findByText('staff-00@example.com')
    expect(screen.queryByText('staff-25@example.com')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('staff-25@example.com')).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('Search email'), 'staff-00')
    expect(await screen.findByText('staff-00@example.com')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
  })
})
