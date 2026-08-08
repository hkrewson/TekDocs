import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { WorkspaceOverview } from './WorkspaceOverview'
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

it('identifies organization scope and the areas that will inherit it', () => {
  render(<MemoryRouter><WorkspaceOverview workspace={workspace} /></MemoryRouter>)

  expect(screen.getByRole('heading', { name: 'Acme Dental' })).toBeInTheDocument()
  expect(screen.getByText('Client · Vendor workspace')).toBeInTheDocument()
  expect(screen.getByText('Acme Dental Associates, LLC')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Return to MSP organizations' })).toHaveAttribute('href', '/organizations')
  expect(screen.getByText('Products')).toBeInTheDocument()
})
