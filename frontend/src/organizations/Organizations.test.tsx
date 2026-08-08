import { render, screen } from '@testing-library/react'
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
  classifications: ['client', 'partner'],
  created_at: '2026-08-08T12:00:00Z',
  updated_at: '2026-08-08T12:00:00Z',
}

function client(overrides: Partial<OrganizationClient> = {}): OrganizationClient {
  return {
    list: vi.fn().mockResolvedValue([acme]),
    create: vi.fn().mockResolvedValue({ ...acme, id: '00000000-0000-4000-8000-000000000011' }),
    update: vi.fn().mockResolvedValue({ ...acme, name: 'Acme Health' }),
    archive: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

function renderOrganizations(organizationClient: OrganizationClient) {
  return render(<MemoryRouter><Organizations client={organizationClient} /></MemoryRouter>)
}

describe('Organizations', () => {
  it('loads, filters, and exposes organization details accessibly', async () => {
    const user = userEvent.setup()
    renderOrganizations(client())

    expect(await screen.findByRole('button', { name: 'Edit Acme Dental' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Acme Dental' })).toHaveAttribute('href', `/workspaces/organizations/${acme.id}/overview`)
    expect(screen.getByText('Client, Partner')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Visit site' })).toHaveAttribute('href', 'https://acme.example.com')

    await user.selectOptions(screen.getByLabelText('Show'), 'vendor')
    expect(screen.getByText('No vendor organizations found.')).toBeInTheDocument()
  })

  it('creates a multi-classification organization', async () => {
    const user = userEvent.setup()
    const create = vi.fn().mockResolvedValue({ ...acme, id: '00000000-0000-4000-8000-000000000011' })
    const organizationClient = client({ list: vi.fn().mockResolvedValue([]), create })
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
    expect(await screen.findByRole('status')).toHaveTextContent('Organization added.')
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
    expect(await screen.findByRole('status')).toHaveTextContent('Organization updated.')

    await user.click(screen.getByRole('button', { name: 'Archive Acme Health' }))
    expect(screen.getByRole('alertdialog', { name: 'Archive Acme Health?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Archive organization' }))
    expect(archive).toHaveBeenCalledWith(acme.id)
    expect(await screen.findByRole('status')).toHaveTextContent('Organization archived.')
  })

  it('keeps the form open and reports server denial', async () => {
    const user = userEvent.setup()
    const organizationClient = client({
      list: vi.fn().mockResolvedValue([]),
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
})
