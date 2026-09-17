import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import { Organizations } from './Organizations'
import type { Organization, OrganizationClient } from './api'

const acme: Organization = {
  id: '00000000-0000-4000-8000-000000000010',
  name: 'Acme Dental',
  legal_name: 'Acme Dental Associates, LLC',
  website: 'https://acme.example.com',
  access_mode: 'assigned_only',
  classifications: ['client', 'partner'],
  created_at: '2026-08-08T12:00:00Z',
  updated_at: '2026-08-08T12:00:00Z',
}

function client(overrides: Partial<OrganizationClient> = {}): OrganizationClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [acme], page: 1, page_size: 25, count: 1, has_more: false }),
    retrieve: vi.fn().mockResolvedValue(acme),
    create: vi.fn().mockResolvedValue({ ...acme, id: '00000000-0000-4000-8000-000000000011' }),
    update: vi.fn().mockResolvedValue({ ...acme, name: 'Acme Health' }),
    archive: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

function renderOrganizations(organizationClient: OrganizationClient, initialEntry = '/organizations') {
  return render(<MemoryRouter initialEntries={[initialEntry]}><Organizations client={organizationClient} /></MemoryRouter>)
}

async function settleDebounce() {
  await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 250)) })
}

describe('Organizations', () => {
  it('loads, filters, and exposes organization details accessibly', async () => {
    const user = userEvent.setup()
    const list = vi.fn().mockResolvedValueOnce({ results: [acme], page: 1, page_size: 25, count: 1, has_more: false }).mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false })
    renderOrganizations(client({ list }))

    expect(await screen.findByRole('button', { name: 'Edit Acme Dental' })).toBeInTheDocument()
    expect(screen.getByText('Client, Partner')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Acme Dental' }))
    const drawer = screen.getByRole('dialog', { name: 'Acme Dental' })
    expect(within(drawer).getByRole('link', { name: 'Open workspace' })).toHaveAttribute('href', `/workspaces/organizations/${acme.id}/overview`)
    expect(within(drawer).getByRole('link', { name: 'https://acme.example.com' })).toHaveAttribute('href', 'https://acme.example.com')
    expect(within(drawer).getByText('Assigned staff only')).toBeInTheDocument()
    fireEvent(drawer, new Event('cancel', { cancelable: true }))

    await user.click(screen.getByRole('button', { name: 'Filters' }))
    await user.click(screen.getByText('Show type'))
    await user.click(screen.getByRole('radio', { name: 'Vendor' }))
    await settleDebounce()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ classification: 'vendor', page: 1 }), expect.any(AbortSignal))
    expect(screen.getByText('No organizations match these filters.')).toBeInTheDocument()
  })

  it('creates a multi-classification organization', async () => {
    const user = userEvent.setup()
    const create = vi.fn().mockResolvedValue({ ...acme, id: '00000000-0000-4000-8000-000000000011' })
    const organizationClient = client({ list: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }), create })
    renderOrganizations(organizationClient)

    await screen.findByText('No organizations have been added.')
    await user.click(screen.getByRole('button', { name: 'New organization' }))
    await user.type(screen.getByLabelText('Display name'), 'Acme Dental')
    await user.type(screen.getByLabelText(/Legal name/), 'Acme Dental Associates, LLC')
    await user.type(screen.getByLabelText(/Website/), 'https://acme.example.com')
    await user.click(screen.getByLabelText('Partner'))
    await user.click(screen.getByRole('button', { name: 'Save organization' }))

    expect(create).toHaveBeenCalledWith({
      name: 'Acme Dental',
      legal_name: 'Acme Dental Associates, LLC',
      website: 'https://acme.example.com',
      classifications: ['client', 'partner'],
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Acme Dental was added.')
  })

  it('updates and archives with an explicit confirmation', async () => {
    const user = userEvent.setup()
    const update = vi.fn().mockResolvedValue({ ...acme, name: 'Acme Health' })
    const archive = vi.fn().mockResolvedValue(undefined)
    const organizationClient = client({ update, archive })
    renderOrganizations(organizationClient)
    await screen.findByRole('button', { name: 'Edit Acme Dental' })

    await user.click(screen.getByRole('button', { name: 'Edit Acme Dental' }))
    const name = screen.getByLabelText('Display name')
    await user.clear(name)
    await user.type(name, 'Acme Health')
    await user.click(screen.getByRole('button', { name: 'Save organization' }))
    expect(update).toHaveBeenCalledWith(acme.id, expect.objectContaining({ name: 'Acme Health' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Acme Health was updated.')

    await user.click(screen.getByRole('button', { name: 'Archive' }))
    expect(screen.getByRole('alertdialog', { name: 'Archive Acme Health?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Archive organization' }))
    expect(archive).toHaveBeenCalledWith(acme.id)
    expect(await screen.findByRole('status')).toHaveTextContent('Acme Health was moved to the recycle bin.')
  })

  it('keeps the form open and reports server denial', async () => {
    const user = userEvent.setup()
    const organizationClient = client({
      list: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }),
      create: vi.fn().mockRejectedValue(new Error('Your account is not authorized for organization administration.')),
    })
    renderOrganizations(organizationClient)
    await screen.findByText('No organizations have been added.')

    await user.click(screen.getByRole('button', { name: 'New organization' }))
    await user.type(screen.getByLabelText('Display name'), 'Denied Client')
    await user.click(screen.getByRole('button', { name: 'Save organization' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('not authorized')
    expect(screen.getByLabelText('Display name')).toHaveValue('Denied Client')
  })

  it('keeps long organization names available to links and row actions', async () => {
    const longName = 'North Central Regional Healthcare and Community Services Cooperative'.repeat(3)
    renderOrganizations(client({ list: vi.fn().mockResolvedValue({ results: [{ ...acme, name: longName }], page: 1, page_size: 25, count: 1, has_more: false }) }))

    expect(await screen.findByRole('button', { name: longName })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: `Edit ${longName}` })).toBeInTheDocument()
  })

  it('loads an off-page record from its URL and guards unfinished edits', async () => {
    const user = userEvent.setup()
    const retrieve = vi.fn().mockResolvedValue(acme)
    renderOrganizations(client({ list: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false }), retrieve }), `/organizations?organization=${acme.id}`)

    const drawer = await screen.findByRole('dialog', { name: 'Acme Dental' })
    expect(retrieve).toHaveBeenCalledWith(acme.id, expect.any(AbortSignal))
    await user.click(within(drawer).getByRole('button', { name: 'Edit details' }))
    await user.type(within(drawer).getByLabelText('Display name'), ' revised')
    fireEvent(drawer, new Event('cancel', { cancelable: true }))
    expect(screen.getByRole('alertdialog', { name: 'Unsaved changes' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(within(drawer).getByLabelText('Display name')).toHaveValue('Acme Dental revised')
  })
})
