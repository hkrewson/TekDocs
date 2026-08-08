import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { AccessControl } from './AccessControl'
import type { AccessControlClient } from './api'

const owner = { id: 'owner', display_name: 'Primary Owner', email: 'owner@example.com', role: 'owner' as const, is_owner: true, joined_at: '2026-08-08T12:00:00Z' }
const technician = { id: 'member', display_name: 'Morgan Ellis', email: 'morgan@example.com', role: 'read_only' as const, is_owner: false, joined_at: '2026-08-08T13:00:00Z' }
const clientOrganization = { id: 'organization', name: 'Acme Dental', access_mode: 'all_authorized' as const }
const catalog = {
  permissions: [{ key: 'people.view', label: 'View people', category: 'People', requires_mfa: false }],
  roles: [
    { value: 'owner' as const, label: 'Owner', description: 'Installation owner.', assignable_scope: 'installation' as const, permissions: ['people.view'] },
    { value: 'administrator' as const, label: 'Administrator', description: 'Administrator.', assignable_scope: 'tenant' as const, permissions: ['people.view'] },
    { value: 'technician' as const, label: 'Technician', description: 'Technician.', assignable_scope: 'tenant' as const, permissions: ['people.view'] },
    { value: 'contributor' as const, label: 'Contributor', description: 'Contributor.', assignable_scope: 'tenant' as const, permissions: ['people.view'] },
    { value: 'read_only' as const, label: 'Read-only', description: 'Read-only.', assignable_scope: 'tenant' as const, permissions: ['people.view'] },
    { value: 'client_administrator' as const, label: 'Client Administrator', description: 'Client administrator.', assignable_scope: 'organization' as const, permissions: ['people.view'] },
    { value: 'client_user' as const, label: 'Client User', description: 'Client user.', assignable_scope: 'organization' as const, permissions: ['people.view'] },
  ],
}

function client(overrides: Partial<AccessControlClient> = {}): AccessControlClient {
  return {
    catalog: vi.fn().mockResolvedValue(catalog),
    members: vi.fn().mockResolvedValue([owner, technician]),
    organizations: vi.fn().mockResolvedValue([clientOrganization]),
    assignRole: vi.fn().mockResolvedValue({ ...technician, role: 'technician' }),
    changeAccessMode: vi.fn().mockResolvedValue({ ...clientOrganization, access_mode: 'assigned_only' }),
    ...overrides,
  }
}

describe('access control', () => {
  it('reviews and confirms a member role without making the owner editable', async () => {
    const user = userEvent.setup()
    const assignRole = vi.fn().mockResolvedValue({ ...technician, role: 'technician' })
    render(<AccessControl client={client({ assignRole })} />)

    expect(await screen.findByText('Primary Owner')).toBeInTheDocument()
    expect(screen.getByText('Client Administrator')).toBeInTheDocument()
    expect(screen.getAllByText('Organization-scoped role')).toHaveLength(2)
    expect(screen.getByText('Bootstrap identity')).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Role for Morgan Ellis' }), 'technician')
    await user.click(screen.getAllByRole('button', { name: 'Review change' })[0])
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Change Morgan Ellis from Read-only to Technician')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))

    await waitFor(() => expect(assignRole).toHaveBeenCalledWith('member', 'technician'))
    expect(await screen.findByRole('status')).toHaveTextContent("Morgan Ellis's role was updated")
  })

  it('warns that assigned-only remains owner-only before changing the mode', async () => {
    const user = userEvent.setup()
    const changeAccessMode = vi.fn().mockResolvedValue({ ...clientOrganization, access_mode: 'assigned_only' })
    render(<AccessControl client={client({ changeAccessMode })} />)

    await screen.findByText('Acme Dental')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Access mode for Acme Dental' }), 'assigned_only')
    await user.click(screen.getAllByRole('button', { name: 'Review change' })[1])
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Only the owner will retain access')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))

    await waitFor(() => expect(changeAccessMode).toHaveBeenCalledWith('organization', 'assigned_only'))
  })

  it('shows one denial state without retaining stale rows', async () => {
    render(<AccessControl client={client({ catalog: vi.fn().mockRejectedValue(new Error('Access denied.')) })} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
    expect(screen.queryByText('Morgan Ellis')).not.toBeInTheDocument()
  })
})
