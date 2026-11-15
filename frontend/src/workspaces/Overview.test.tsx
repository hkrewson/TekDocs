import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import Overview from './Overview'
import type { WorkspaceClient } from './api'
import type { OperationsClient } from '../operations/api'

it('shows setup only before an organization exists and keeps admin activity out of Home', async () => {
  const workspaceClient = { searchOrganizations: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 15, has_more: false }) } as unknown as WorkspaceClient
  const operationsClient = { reminders: vi.fn().mockResolvedValue([]) } as unknown as OperationsClient
  render(<MemoryRouter><Overview workspaceClient={workspaceClient} operationsClient={operationsClient} /></MemoryRouter>)

  expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Set up your workspace' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Add organization' })).toHaveAttribute('href', '/organizations')
  expect(screen.getByRole('heading', { name: 'Needs attention' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'View reminders' })).toHaveAttribute('href', '/deadlines')
  expect(screen.queryByRole('link', { name: /Activity/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})
