import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  expect(screen.getByRole('heading', { name: 'Reminders' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'New reminder' })).toHaveAttribute('href', '/deadlines?new=1')
  expect(screen.getByRole('link', { name: 'View reminders' })).toHaveAttribute('href', '/deadlines')
  expect(await screen.findByText('No active reminders.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Activity/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})

it('retires setup after the first organization and promotes reminder creation', async () => {
  const workspaceClient = { searchOrganizations: vi.fn().mockResolvedValue({ results: [{ id: 'organization-1' }], page: 1, page_size: 15, has_more: false }) } as unknown as WorkspaceClient
  const operationsClient = { reminders: vi.fn().mockResolvedValue([]) } as unknown as OperationsClient
  render(<MemoryRouter><Overview workspaceClient={workspaceClient} operationsClient={operationsClient} /></MemoryRouter>)

  const newReminder = screen.getByRole('link', { name: 'New reminder' })
  await waitFor(() => expect(newReminder).toHaveClass('primary-button'))
  expect(screen.queryByRole('heading', { name: 'Set up your workspace' })).not.toBeInTheDocument()
})

it('keeps setup available while a failed reminder agenda recovers independently', async () => {
  const workspaceClient = { searchOrganizations: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 15, has_more: false }) } as unknown as WorkspaceClient
  const reminders = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue([])
  const operationsClient = { reminders } as unknown as OperationsClient
  render(<MemoryRouter><Overview workspaceClient={workspaceClient} operationsClient={operationsClient} /></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Set up your workspace' })).toBeInTheDocument()
  expect(await screen.findByRole('alert')).toHaveTextContent('Reminders couldn’t be loaded.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

  expect(await screen.findByText('No active reminders.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Set up your workspace' })).toBeInTheDocument()
  expect(reminders).toHaveBeenCalledTimes(2)
})
