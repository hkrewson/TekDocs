import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { AccessControl } from './AccessControl'
import type { AccessControlClient } from './api'

const owner = { id: 'owner', display_name: 'Primary Owner', email: 'owner@example.com', role: 'owner' as const, is_owner: true, joined_at: '2026-08-08T12:00:00Z' }
const technician = { id: 'member', display_name: 'Morgan Ellis', email: 'morgan@example.com', role: 'read_only' as const, is_owner: false, joined_at: '2026-08-08T13:00:00Z' }
const clientOrganization = { id: 'organization', name: 'Acme Dental', access_mode: 'all_authorized' as const, assigned_staff: [] }
const customRole = { id: 'custom-role', name: 'Documentation lead', description: 'Publishes client documents.', scope: 'organization' as const, permissions: ['documents.edit'], assignment_count: 0, archived_at: null, created_at: '2026-08-08T13:00:00Z', updated_at: '2026-08-08T13:00:00Z' }
const accessCollection = { id: 'collection', name: 'Priority clients', description: 'Primary support group.', organizations: [{ id: clientOrganization.id, name: clientOrganization.name }], assignment_count: 0, archived_at: null, created_at: '2026-08-08T13:00:00Z', updated_at: '2026-08-08T13:00:00Z' }
const catalog = {
  permissions: [{ key: 'people.view', label: 'View people', category: 'People', requires_mfa: false }],
  custom_assignable_permissions: [{ key: 'documents.edit', label: 'Edit documentation', category: 'Documentation', requires_mfa: true }],
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
    customRoles: vi.fn().mockResolvedValue([]),
    scopedAssignments: vi.fn().mockResolvedValue([]),
    accessCollections: vi.fn().mockResolvedValue([]),
    assignRole: vi.fn().mockResolvedValue({ ...technician, role: 'technician' }),
    changeAccessMode: vi.fn().mockResolvedValue({ ...clientOrganization, access_mode: 'assigned_only' }),
    assignStaff: vi.fn().mockResolvedValue({ ...clientOrganization, assigned_staff: [{ id: technician.id, display_name: technician.display_name, email: technician.email, role: technician.role }] }),
    removeStaff: vi.fn().mockResolvedValue(clientOrganization),
    createCustomRole: vi.fn(),
    updateCustomRole: vi.fn(),
    archiveCustomRole: vi.fn(),
    createAccessCollection: vi.fn(),
    updateAccessCollection: vi.fn(),
    archiveAccessCollection: vi.fn(),
    createScopedAssignment: vi.fn(),
    removeScopedAssignment: vi.fn(),
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

  it('explains the assignment boundary before changing the mode', async () => {
    const user = userEvent.setup()
    const changeAccessMode = vi.fn().mockResolvedValue({ ...clientOrganization, access_mode: 'assigned_only' })
    render(<AccessControl client={client({ changeAccessMode })} />)

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Access mode for Acme Dental' }), 'assigned_only')
    await user.click(screen.getAllByRole('button', { name: 'Review change' })[1])
    expect(screen.getByRole('alertdialog')).toHaveTextContent('explicitly assigned MSP staff')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))

    await waitFor(() => expect(changeAccessMode).toHaveBeenCalledWith('organization', 'assigned_only'))
  })

  it('reviews staff assignment and removal without changing the tenant role', async () => {
    const user = userEvent.setup()
    const assignedOrganization = { ...clientOrganization, assigned_staff: [{ id: technician.id, display_name: technician.display_name, email: technician.email, role: technician.role }] }
    const assignStaff = vi.fn().mockResolvedValue(assignedOrganization)
    const removeStaff = vi.fn().mockResolvedValue(clientOrganization)
    render(<AccessControl client={client({ assignStaff, removeStaff })} />)

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Staff member for Acme Dental' }), technician.id)
    await user.click(screen.getByRole('button', { name: 'Review assignment' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Their MSP role still determines what they can do')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))
    await waitFor(() => expect(assignStaff).toHaveBeenCalledWith(clientOrganization.id, technician.id))

    await user.click(await screen.findByRole('button', { name: 'Remove' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('They will lose access if this organization is assigned-only')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))
    await waitFor(() => expect(removeStaff).toHaveBeenCalledWith(clientOrganization.id, technician.id))
  })

  it('shows one denial state without retaining stale rows', async () => {
    render(<AccessControl client={client({ catalog: vi.fn().mockRejectedValue(new Error('Access denied.')) })} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
    expect(screen.queryByText('Morgan Ellis')).not.toBeInTheDocument()
  })

  it('reviews custom role creation and exact-organization assignment', async () => {
    const user = userEvent.setup()
    const createCustomRole = vi.fn().mockResolvedValue(customRole)
    const createScopedAssignment = vi.fn().mockResolvedValue({ id: 'assignment', member_id: technician.id, member_name: technician.display_name, member_email: technician.email, role_id: customRole.id, role_name: customRole.name, role_scope: customRole.scope, organization_id: clientOrganization.id, organization_name: clientOrganization.name, collection_id: null, collection_name: null, created_at: '2026-08-08T14:00:00Z' })
    render(<AccessControl client={client({ customRoles: vi.fn().mockResolvedValue([]), createCustomRole, createScopedAssignment })} />)

    await user.type(await screen.findByRole('textbox', { name: 'Role name' }), 'Documentation lead')
    await user.click(screen.getByRole('checkbox', { name: /Edit documentation/ }))
    await user.click(screen.getByRole('button', { name: 'Review role' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('grants nothing until assigned')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))
    await waitFor(() => expect(createCustomRole).toHaveBeenCalledWith(expect.objectContaining({ name: 'Documentation lead' })))

    await user.selectOptions(screen.getByRole('combobox', { name: 'Custom role member' }), technician.id)
    await user.selectOptions(screen.getByRole('combobox', { name: 'Custom role definition' }), customRole.id)
    await user.selectOptions(screen.getByRole('combobox', { name: 'Custom role organization' }), clientOrganization.id)
    await user.click(screen.getByRole('button', { name: 'Review custom assignment' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('only for Acme Dental')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))
    await waitFor(() => expect(createScopedAssignment).toHaveBeenCalledWith({ user_id: technician.id, role_id: customRole.id, organization_id: clientOrganization.id, collection_id: null }))
  })

  it('reviews an access collection before applying membership', async () => {
    const user = userEvent.setup()
    const createAccessCollection = vi.fn().mockResolvedValue(accessCollection)
    render(<AccessControl client={client({ createAccessCollection })} />)

    const panel = (await screen.findByRole('heading', { name: 'Access collections' })).closest('section')
    if (!panel) throw new Error('Access collection panel was not rendered')
    await user.type(within(panel).getByRole('textbox', { name: 'Collection name' }), 'Priority clients')
    await user.type(within(panel).getByRole('textbox', { name: 'Description' }), 'Primary support group.')
    await user.click(within(panel).getByRole('checkbox', { name: 'Acme Dental' }))
    await user.click(within(panel).getByRole('button', { name: 'Review collection' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('grants nothing until a collection-scoped role is assigned')
    await user.click(screen.getByRole('button', { name: 'Confirm change' }))

    await waitFor(() => expect(createAccessCollection).toHaveBeenCalledWith({
      name: 'Priority clients',
      description: 'Primary support group.',
      organization_ids: [clientOrganization.id],
    }))
    expect(await screen.findByRole('status')).toHaveTextContent('Priority clients was created')
  })
})
