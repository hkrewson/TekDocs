import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { App } from './App'
import type { AuthenticatedContext } from './auth/api'
import type { AuthClient } from './auth/api'
import type { WorkspaceClient } from './workspaces/api'

const authContext: AuthenticatedContext = {
  user: { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: '00000000-0000-4000-8000-000000000002', name: 'Example MSP' },
}

const authClient = {
  listSessions: vi.fn().mockResolvedValue([]),
  loadMfa: vi.fn().mockResolvedValue({ totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 }),
} as unknown as AuthClient
const loadOrganization = vi.fn().mockResolvedValue({
  kind: 'organization',
  id: '00000000-0000-4000-8000-000000000010',
  name: 'Acme Dental',
  classifications: ['client'],
  capabilities: ['overview', 'documentation', 'people', 'assets', 'networks', 'credentials'],
  organization: {
    id: '00000000-0000-4000-8000-000000000010',
    name: 'Acme Dental',
    legal_name: 'Acme Dental Associates, LLC',
    website: 'https://acme.example.com',
    classifications: ['client'],
    created_at: '2026-08-08T12:00:00Z',
    updated_at: '2026-08-08T12:00:00Z',
  },
})
const workspaceClient = {
  loadMsp: vi.fn(),
  loadOrganization,
} as unknown as WorkspaceClient
const app = (initialPath: string) => <App initialPath={initialPath} initialAuthContext={authContext} authClient={authClient} workspaceClient={workspaceClient} />

describe('application shell', () => {
  it('renders sectioned navigation and the active route', () => {
    render(app('/overview'))

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Documentation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Compliance' })).toBeInTheDocument()
  })

  it('provides profile routes through the account menu', async () => {
    const user = userEvent.setup()
    render(app('/overview'))

    await user.click(screen.getByRole('button', { name: /Account menu for Primary Owner/i }))
    expect(screen.getByRole('menuitem', { name: 'Settings' })).toHaveAttribute('href', '/settings')
    expect(screen.getByRole('menuitem', { name: 'Integrations' })).toHaveAttribute('href', '/integrations')
    await user.click(screen.getByRole('menuitem', { name: 'Settings' }))
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  it('collapses the desktop navigation without removing accessible links', async () => {
    const user = userEvent.setup()
    render(app('/organizations'))

    expect(screen.getByRole('heading', { name: 'Organizations' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Collapse navigation' }))
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument()
  })

  it('resolves a deep-linked organization route through the workspace boundary', async () => {
    render(app('/workspaces/organizations/00000000-0000-4000-8000-000000000010/overview'))

    expect(await screen.findByRole('heading', { name: 'Acme Dental' })).toBeInTheDocument()
    expect(loadOrganization).toHaveBeenCalledWith('00000000-0000-4000-8000-000000000010')
    expect(screen.getByText('client workspace')).toBeInTheDocument()
  })
})
