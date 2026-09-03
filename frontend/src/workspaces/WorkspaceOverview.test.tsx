import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import { WorkspaceOverview } from './WorkspaceOverview'
import type { RelationshipsClient } from '../relationships/api'
import type { IntegrationsClient } from '../integrations/providerApi'
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
  expect(screen.getByText('Products')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Organization relationships' })).toBeInTheDocument()
  expect(await screen.findByText('No relationships have been added.')).toBeInTheDocument()
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
})
