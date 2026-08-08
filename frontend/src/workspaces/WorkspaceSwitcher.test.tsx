import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router'
import { vi } from 'vitest'
import { WorkspaceSwitcher } from './WorkspaceSwitcher'
import type { WorkspaceClient, WorkspaceContext, WorkspaceOption } from './api'

const acme: WorkspaceContext = {
  kind: 'organization',
  id: '00000000-0000-4000-8000-000000000010',
  name: 'Acme Dental',
  classifications: ['client'],
  capabilities: ['overview', 'people', 'documentation', 'files', 'assets', 'licenses', 'networks', 'domains', 'certificates', 'credentials', 'services', 'tickets', 'vendors'],
  organization: null,
}

const northwind: WorkspaceOption = {
  id: '00000000-0000-4000-8000-000000000011',
  name: 'Northwind Clinic',
  classifications: ['client', 'vendor'],
  capabilities: ['overview', 'people', 'documentation', 'files', 'assets', 'licenses', 'networks', 'domains', 'certificates', 'credentials', 'services', 'tickets', 'vendors', 'products'],
}

function Location() {
  return <output aria-label="Current route">{useLocation().pathname}</output>
}

function renderSwitcher(client: WorkspaceClient) {
  return render(
    <MemoryRouter initialEntries={[`/workspaces/organizations/${acme.id}/documentation`]}>
      <WorkspaceSwitcher tenant={{ id: 'tenant', name: 'Example MSP' }} activeWorkspace={acme} activeArea="documentation" client={client} collapsed={false} workspaceLoading={false} onNavigate={() => undefined} />
      <Location />
    </MemoryRouter>,
  )
}

describe('WorkspaceSwitcher', () => {
  it('searches authorized workspaces and preserves the current area', async () => {
    const user = userEvent.setup()
    const searchOrganizations = vi.fn().mockResolvedValue({ results: [northwind], page: 1, page_size: 15, has_more: false })
    renderSwitcher({ searchOrganizations } as unknown as WorkspaceClient)

    await user.click(screen.getByRole('button', { name: /Current workspace: Acme Dental/ }))
    const search = screen.getByRole('textbox', { name: 'Find a client' })
    await user.type(search, 'north')
    expect(await screen.findByRole('button', { name: 'Northwind Clinic. Client · Vendor' })).toBeInTheDocument()
    await waitFor(() => expect(searchOrganizations).toHaveBeenLastCalledWith('north', 1, expect.any(AbortSignal), 'client'))
    await user.click(screen.getByRole('button', { name: 'Northwind Clinic. Client · Vendor' }))

    expect(screen.getByRole('status', { name: 'Current route' })).toHaveTextContent(`/workspaces/organizations/${northwind.id}/documentation`)
  })

  it('keeps the MSP entry available and supports keyboard entry and dismissal', async () => {
    const user = userEvent.setup()
    renderSwitcher({ searchOrganizations: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 15, has_more: false }) } as unknown as WorkspaceClient)

    await user.click(screen.getByRole('button', { name: /Current workspace: Acme Dental/ }))
    const search = screen.getByRole('textbox', { name: 'Find a client' })
    await user.type(search, '{ArrowDown}')
    expect(screen.getByRole('button', { name: 'Back to Example MSP. MSP workspace' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Switch workspace' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Current workspace: Acme Dental/ }))
    await user.click(screen.getByRole('button', { name: 'Back to Example MSP. MSP workspace' }))
    expect(screen.getByRole('status', { name: 'Current route' })).toHaveTextContent('/documentation')
  })

  it('shows safe loading, empty, and denial states', async () => {
    const user = userEvent.setup()
    const searchOrganizations = vi.fn()
      .mockRejectedValueOnce(new Error('private response details'))
      .mockResolvedValueOnce({ results: [], page: 1, page_size: 15, has_more: false })
    renderSwitcher({ searchOrganizations } as unknown as WorkspaceClient)

    await user.click(screen.getByRole('button', { name: /Current workspace: Acme Dental/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Workspaces could not be loaded.')
    await user.type(screen.getByRole('textbox', { name: 'Find a client' }), 'none')
    expect(await screen.findByText('No matching clients.')).toBeInTheDocument()
    expect(screen.queryByText('private response details')).not.toBeInTheDocument()
  })

  it('ignores a late response from a previous search', async () => {
    const user = userEvent.setup()
    let resolveOld!: (value: { results: WorkspaceOption[]; page: number; page_size: number; has_more: boolean }) => void
    let resolveNew!: (value: { results: WorkspaceOption[]; page: number; page_size: number; has_more: boolean }) => void
    const oldResult = { ...northwind, id: '00000000-0000-4000-8000-000000000099', name: 'Old Result' }
    const oldRequest = new Promise<{ results: WorkspaceOption[]; page: number; page_size: number; has_more: boolean }>((resolve) => { resolveOld = resolve })
    const newRequest = new Promise<{ results: WorkspaceOption[]; page: number; page_size: number; has_more: boolean }>((resolve) => { resolveNew = resolve })
    const searchOrganizations = vi.fn((query: string) => query ? newRequest : oldRequest)
    renderSwitcher({ searchOrganizations } as unknown as WorkspaceClient)

    await user.click(screen.getByRole('button', { name: /Current workspace: Acme Dental/ }))
    await waitFor(() => expect(searchOrganizations).toHaveBeenCalledWith('', 1, expect.any(AbortSignal), 'client'))
    await user.type(screen.getByRole('textbox', { name: 'Find a client' }), 'north')
    await waitFor(() => expect(searchOrganizations).toHaveBeenCalledWith('north', 1, expect.any(AbortSignal), 'client'))
    resolveNew({ results: [northwind], page: 1, page_size: 15, has_more: false })
    expect(await screen.findByText('Northwind Clinic')).toBeInTheDocument()
    resolveOld({ results: [oldResult], page: 1, page_size: 15, has_more: false })
    await waitFor(() => expect(screen.queryByText('Old Result')).not.toBeInTheDocument())
  })
})
