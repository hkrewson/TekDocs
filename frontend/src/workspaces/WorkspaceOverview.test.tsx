import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import { WorkspaceOverview } from './WorkspaceOverview'
import type { RelationshipsClient } from '../relationships/api'
import type { IntegrationsClient } from '../integrations/providerApi'
import type { OperationsClient } from '../operations/api'
import type { WorkspaceContext } from './api'

const workspace: WorkspaceContext = {
  kind: 'organization',
  id: '00000000-0000-4000-8000-000000000010',
  name: 'Acme Dental',
  classifications: ['client', 'vendor'],
  capabilities: ['overview', 'documentation', 'people', 'assets', 'networks', 'credentials', 'products'],
  organization: {
    id: '00000000-0000-4000-8000-000000000010',
    name: 'Acme Dental',
    legal_name: 'Acme Dental Associates, LLC',
    website: 'https://acme.example.com',
    billing_contact_name: '', billing_email: '', billing_phone: '', billing_address_line_1: '', billing_address_line_2: '', billing_city: '', billing_region: '', billing_postal_code: '', billing_country_code: '',
    access_mode: 'assigned_only',
    classifications: ['client', 'vendor'],
    created_at: '2026-08-08T12:00:00Z',
    updated_at: '2026-08-08T12:00:00Z',
  },
}

const relationshipsClient: RelationshipsClient = {
  linkTypes: () => Promise.resolve([]),
  search: () => Promise.resolve({ results: [], page: 1, page_size: 15, count: 0, has_more: false }),
  list: () => Promise.resolve([]),
  create: () => Promise.reject(new Error('not used')),
  archive: () => Promise.resolve(),
}

it('identifies organization scope and the areas that will inherit it', async () => {
  render(<MemoryRouter><WorkspaceOverview workspace={workspace} relationshipsClient={relationshipsClient} /></MemoryRouter>)

  expect(screen.getByRole('heading', { name: 'Acme Dental' })).toBeInTheDocument()
  expect(screen.getByText('Client · Vendor workspace')).toBeInTheDocument()
  expect(screen.getByText('Acme Dental Associates, LLC')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Return to MSP organizations' })).toHaveAttribute('href', '/organizations')
  expect(screen.queryByRole('heading', { name: 'Reminders' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Workspace areas' })).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Organization relationships' })).toBeInTheDocument()
  expect(await screen.findByText('No relationships have been added.')).toBeInTheDocument()
})

it('puts the authorized organization reminder agenda on Home with scoped actions', async () => {
  const reminderWorkspace: WorkspaceContext = { ...workspace, capabilities: [...workspace.capabilities, 'deadlines'] }
  const operationsClient = { reminders: vi.fn().mockResolvedValue([{
    id: 'reminder-1', source_entity_id: 'document-1', source: 'Backup procedure', domain: 'documentation', kind: 'review',
    title: 'Review backup procedure', due_on: '2026-11-30', lead_days: 30, recurrence: 'none', owner_id: null, owner: null,
    active: true, created_at: '2026-11-01T12:00:00Z',
  }]) } as unknown as OperationsClient

  render(<MemoryRouter><WorkspaceOverview workspace={reminderWorkspace} relationshipsClient={relationshipsClient} operationsClient={operationsClient} /></MemoryRouter>)

  expect(await screen.findByText('Review backup procedure')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'New reminder' })).toHaveAttribute('href', `/workspaces/organizations/${workspace.id}/deadlines?new=1`)
  expect(screen.getByRole('link', { name: 'View reminders' })).toHaveAttribute('href', `/workspaces/organizations/${workspace.id}/deadlines`)
  expect(screen.getByRole('heading', { name: 'Organization profile' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Activity/ })).not.toBeInTheDocument()
})

it('shows a scoped stale Halo ticket with a provider deep link', async () => {
  const haloWorkspace: WorkspaceContext = { ...workspace, capabilities: [...workspace.capabilities, 'integrations'] }
  const integrationsClient = {
    listHaloTickets: vi.fn().mockResolvedValue([{
      id: 'ticket-observation-1', number: '1042', title: 'Printer queue unavailable',
      status: 'In progress', priority: 'High', assigned_team: 'Service desk', assigned_agent: 'Taylor',
      respond_by: null, fix_by: null, opened_at: null, closed_at: null,
      source_updated_at: '2026-09-01T12:00:00Z', source_last_synced_at: '2026-09-01T12:00:00Z',
      stale: true, external_url: 'https://support.example.com/tickets?id=1042',
    }]),
  } as unknown as IntegrationsClient

  render(<MemoryRouter><WorkspaceOverview workspace={haloWorkspace} relationshipsClient={relationshipsClient} integrationsClient={integrationsClient} /></MemoryRouter>)

  expect(await screen.findByText('#1042 Printer queue unavailable')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Open in HaloPSA/i })).toHaveAttribute('href', 'https://support.example.com/tickets?id=1042')
  expect(screen.getByText(/Stale/i)).toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})

it('recovers a failed ticket summary without disturbing the organization overview', async () => {
  const haloWorkspace: WorkspaceContext = { ...workspace, capabilities: [...workspace.capabilities, 'integrations'] }
  const listHaloTickets = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue([])
  render(<MemoryRouter><WorkspaceOverview workspace={haloWorkspace} relationshipsClient={relationshipsClient} integrationsClient={{ listHaloTickets } as unknown as IntegrationsClient} /></MemoryRouter>)

  expect(await screen.findByText(/ticket references could not be loaded/i)).toBeInTheDocument()
  expect(screen.getByText('Acme Dental Associates, LLC')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

  expect(await screen.findByText(/No mapped HaloPSA tickets/i)).toBeInTheDocument()
  expect(listHaloTickets).toHaveBeenCalledTimes(2)
})
