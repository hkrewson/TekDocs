import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import type { WorkspaceContext } from '../workspaces/api'
import { Sites } from './Sites'
import type { SiteRecord, SitesClient } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization', id: '00000000-0000-4000-8000-000000000010', name: 'Acme Dental', classifications: ['client'], capabilities: ['overview', 'people', 'sites'],
  organization: { id: '00000000-0000-4000-8000-000000000010', name: 'Acme Dental', legal_name: '', website: '', classifications: ['client'], created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
}
const site: SiteRecord = {
  id: '00000000-0000-4000-8000-000000000020', organization_id: workspace.id, name: 'North Campus', code: 'NORTH', address_line_1: '100 Main Street', address_line_2: '', city: 'Madison', region: 'WI', postal_code: '53703', country_code: 'US', timezone: 'America/Chicago', phone: '', created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z',
  locations: [
    { id: '00000000-0000-4000-8000-000000000030', site_id: '00000000-0000-4000-8000-000000000020', parent_id: null, name: 'Building A', kind: 'building', code: 'A', created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
    { id: '00000000-0000-4000-8000-000000000031', site_id: '00000000-0000-4000-8000-000000000020', parent_id: '00000000-0000-4000-8000-000000000030', name: 'Office 214', kind: 'office', code: '214', created_at: '2026-08-08T12:00:00Z', updated_at: '2026-08-08T12:00:00Z' },
  ],
}

function sitesClient(overrides: Partial<SitesClient> = {}): SitesClient {
  return {
    list: vi.fn().mockResolvedValue({ results: [site], count: 1 }),
    create: vi.fn().mockResolvedValue(site),
    update: vi.fn().mockResolvedValue(site),
    archive: vi.fn().mockResolvedValue(undefined),
    createLocation: vi.fn().mockResolvedValue(site.locations[0]),
    updateLocation: vi.fn().mockResolvedValue(site.locations[1]),
    archiveLocation: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

async function settleDebounce() {
  await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 250)) })
}

describe('Sites', () => {
  it('shows the scoped site and nested location hierarchy', async () => {
    render(<Sites workspace={workspace} client={sitesClient()} />)

    expect(await screen.findByRole('heading', { name: 'North Campus' })).toBeInTheDocument()
    expect(screen.getByText('100 Main Street · Madison, WI, 53703 · US · NORTH')).toBeInTheDocument()
    expect(screen.getByText('Building A')).toBeInTheDocument()
    expect(screen.getByText('Office 214')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit location Office 214' })).toBeInTheDocument()
  })

  it('clears prior-workspace sites while a new scope loads', async () => {
    const list = vi.fn().mockResolvedValueOnce({ results: [site], count: 1 }).mockImplementationOnce(() => new Promise(() => undefined))
    const client = sitesClient({ list })
    const { rerender } = render(<Sites workspace={workspace} client={client} />)
    expect(await screen.findByRole('heading', { name: 'North Campus' })).toBeInTheDocument()

    rerender(<Sites workspace={{ ...workspace, id: '00000000-0000-4000-8000-000000000099', name: 'Second Client' }} client={client} />)

    expect(screen.queryByRole('heading', { name: 'North Campus' })).not.toBeInTheDocument()
    expect(screen.getByText('Loading sites…')).toBeInTheDocument()
  })

  it('searches and manages sites and nested locations in the selected workspace', async () => {
    const user = userEvent.setup()
    const list = vi.fn().mockResolvedValue({ results: [site], count: 1 })
    const create = vi.fn().mockResolvedValue(site)
    const createLocation = vi.fn().mockResolvedValue(site.locations[1])
    const archiveLocation = vi.fn().mockResolvedValue(undefined)
    render(<Sites workspace={workspace} client={sitesClient({ list, create, createLocation, archiveLocation })} />)
    await screen.findByRole('heading', { name: 'North Campus' })

    await user.type(screen.getByRole('searchbox', { name: 'Search sites and locations' }), 'office')
    await settleDebounce()
    expect(list).toHaveBeenLastCalledWith({ organizationId: workspace.id }, 'office', expect.any(AbortSignal))

    await user.click(screen.getByRole('button', { name: 'New site' }))
    await user.type(screen.getByLabelText('Site name'), 'South Campus')
    await user.type(screen.getByLabelText(/Code/), 'SOUTH')
    await user.click(screen.getByRole('button', { name: 'Save site' }))
    expect(create).toHaveBeenCalledWith({ organizationId: workspace.id }, expect.objectContaining({ name: 'South Campus', code: 'SOUTH' }))

    await user.click(screen.getByRole('button', { name: 'Add location to North Campus' }))
    await user.type(screen.getByLabelText('Name'), 'Desk 9')
    await user.selectOptions(screen.getByLabelText('Type'), 'desk')
    await user.selectOptions(screen.getByLabelText('Parent'), site.locations[1].id)
    await user.click(screen.getByRole('button', { name: 'Save location' }))
    expect(createLocation).toHaveBeenCalledWith({ organizationId: workspace.id }, site.id, expect.objectContaining({ name: 'Desk 9', kind: 'desk', parent_id: site.locations[1].id }))

    await user.click(screen.getByRole('button', { name: 'Archive location Office 214' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Archive Office 214?' })
    expect(within(dialog).getByText(/retain/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Archive' }))
    expect(archiveLocation).toHaveBeenCalledWith({ organizationId: workspace.id }, site.id, site.locations[1].id)
  })

  it('retains the form and reports a server denial', async () => {
    const user = userEvent.setup()
    const create = vi.fn().mockRejectedValue(new Error('Your account is not authorized to manage sites in this workspace.'))
    render(<Sites workspace={null} client={sitesClient({ list: vi.fn().mockResolvedValue({ results: [], count: 0 }), create })} />)
    await screen.findByText('No sites have been added to the MSP.')

    await user.click(screen.getByRole('button', { name: 'New site' }))
    await user.type(screen.getByLabelText('Site name'), 'Denied Site')
    await user.click(screen.getByRole('button', { name: 'Save site' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('not authorized')
    expect(screen.getByLabelText('Site name')).toHaveValue('Denied Site')
  })
})
