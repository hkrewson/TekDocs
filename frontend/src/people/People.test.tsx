import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { People } from './People'
import type { PeopleClient, PersonRecord } from './api'
import type { WorkspaceContext } from '../workspaces/api'

const workspace: WorkspaceContext = {
  kind: 'organization',
  id: '00000000-0000-4000-8000-000000000010',
  name: 'Acme Dental',
  classifications: ['client'],
  capabilities: ['overview', 'people'],
  organization: {
    id: '00000000-0000-4000-8000-000000000010',
    name: 'Acme Dental',
    legal_name: '',
    website: '',
    classifications: ['client'],
    created_at: '2026-08-08T12:00:00Z',
    updated_at: '2026-08-08T12:00:00Z',
  },
}
const person: PersonRecord = {
  id: '00000000-0000-4000-8000-000000000020',
  association_id: '00000000-0000-4000-8000-000000000021',
  organization_id: workspace.id,
  full_name: 'Jordan Avery',
  preferred_name: 'Jordy',
  kind: 'employee',
  role: 'Systems Administrator',
  responsibility: 'Network operations',
  location: 'North Office',
  office: 'Desk 214',
  phone: '+1 555 010 0240',
  email: 'jordan@example.com',
  created_at: '2026-08-08T12:00:00Z',
  updated_at: '2026-08-08T12:00:00Z',
}

function peopleClient(overrides: Partial<PeopleClient> = {}): PeopleClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [person], page: 1, page_size: 25, count: 1, has_more: false }),
    create: vi.fn().mockResolvedValue(person),
    update: vi.fn().mockResolvedValue(person),
    archive: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('People', () => {
  beforeEach(() => window.localStorage.clear())

  async function settleDebounce() {
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 250)) })
  }

  it('shows the scoped directory and customizes visible columns', async () => {
    const user = userEvent.setup()
    render(<People workspace={workspace} client={peopleClient()} />)

    expect(await screen.findByRole('cell', { name: 'Jordan Avery' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'People' })).toBeInTheDocument()
    expect(screen.getByText('Employees and contacts associated with Acme Dental.')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Responsibility' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Choose visible columns' }))
    await user.click(screen.getByRole('checkbox', { name: 'Responsibility' }))
    expect(screen.getByRole('columnheader', { name: 'Responsibility' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Network operations' })).toBeInTheDocument()
    expect(window.localStorage.getItem('tekdocs.people.visible-columns.v1')).toContain('responsibility')
  })

  it('withholds prior-workspace people while the next workspace is loading', async () => {
    const list = vi.fn()
      .mockResolvedValueOnce({ results: [person], page: 1, page_size: 25, count: 1, has_more: false })
      .mockImplementationOnce(() => new Promise(() => undefined))
    const client = peopleClient({ list })
    const { rerender } = render(<People workspace={workspace} client={client} />)
    expect(await screen.findByRole('cell', { name: /^Jordan Avery$/ })).toBeInTheDocument()

    rerender(<People workspace={{ ...workspace, id: '00000000-0000-4000-8000-000000000030', name: 'Second Client' }} client={client} />)

    expect(screen.queryByRole('cell', { name: /^Jordan Avery$/ })).not.toBeInTheDocument()
    expect(screen.getByText('Loading people…')).toBeInTheDocument()
  })

  it('searches all fields, filters one field, and changes sorting', async () => {
    const user = userEvent.setup()
    const list = vi.fn().mockResolvedValue({ results: [person], page: 1, page_size: 25, count: 1, has_more: false })
    render(<People workspace={workspace} client={peopleClient({ list })} />)
    await screen.findByRole('cell', { name: 'Jordan Avery' })

    await user.type(screen.getByRole('searchbox', { name: 'Search all person fields' }), 'north')
    await settleDebounce()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Filter field' }), 'role')
    await user.type(screen.getByRole('textbox', { name: 'Filter value' }), 'admin')
    await settleDebounce()
    await user.click(screen.getByRole('button', { name: 'Full name' }))
    await settleDebounce()

    await vi.waitFor(() => expect(list).toHaveBeenLastCalledWith(
      { organizationId: workspace.id },
      expect.objectContaining({ q: 'north', filter_field: 'role', filter_value: 'admin', ordering: '-full_name' }),
      expect.any(AbortSignal),
    ))
  })

  it('creates, edits, and archives a person in the selected scope', async () => {
    const user = userEvent.setup()
    const create = vi.fn().mockResolvedValue(person)
    const update = vi.fn().mockResolvedValue({ ...person, preferred_name: 'Jordan' })
    const archive = vi.fn().mockResolvedValue(undefined)
    render(<People workspace={workspace} client={peopleClient({ create, update, archive })} />)
    await screen.findByRole('cell', { name: 'Jordan Avery' })

    await user.click(screen.getByRole('button', { name: 'New person' }))
    await user.type(screen.getByLabelText('Full name'), 'Morgan Ellis')
    await user.selectOptions(screen.getByLabelText('Relationship'), 'contact')
    await user.type(screen.getByLabelText(/Role/), 'Office Manager')
    await user.type(screen.getByLabelText(/Location/), 'Main Office')
    await user.type(screen.getByLabelText(/Office/), 'Room 4')
    await user.type(screen.getByLabelText(/Email/), 'morgan@example.com')
    await user.click(screen.getByRole('button', { name: 'Save person' }))
    expect(create).toHaveBeenCalledWith({ organizationId: workspace.id }, expect.objectContaining({ full_name: 'Morgan Ellis', role: 'Office Manager' }))
    expect(await screen.findByRole('status', { name: '' })).toHaveTextContent('Person added.')

    await user.click(screen.getByRole('button', { name: 'Edit Jordan Avery' }))
    const preferredName = screen.getByLabelText(/Preferred name/)
    await user.clear(preferredName)
    await user.type(preferredName, 'Jordan')
    await user.click(screen.getByRole('button', { name: 'Save person' }))
    expect(update).toHaveBeenCalledWith({ organizationId: workspace.id }, person.id, expect.objectContaining({ preferred_name: 'Jordan' }))

    await user.click(screen.getByRole('button', { name: 'Archive Jordan Avery' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Archive Jordan Avery?' })
    expect(within(dialog).getByText(/Other future associations/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Archive person' }))
    expect(archive).toHaveBeenCalledWith({ organizationId: workspace.id }, person.id)
  })

  it('keeps the form open when the server denies a change', async () => {
    const user = userEvent.setup()
    const create = vi.fn().mockRejectedValue(new Error('Your account is not authorized to manage people in this workspace.'))
    render(<People workspace={null} client={peopleClient({ list: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }), create })} />)
    await screen.findByText('No people have been added to this workspace.')

    await user.click(screen.getByRole('button', { name: 'New person' }))
    await user.type(screen.getByLabelText('Full name'), 'Denied Person')
    await user.click(screen.getByRole('button', { name: 'Save person' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('not authorized')
    expect(screen.getByLabelText('Full name')).toHaveValue('Denied Person')
  })
})
