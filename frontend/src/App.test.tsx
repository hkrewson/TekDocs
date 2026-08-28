import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { App } from './App'
import type { AuthenticatedContext } from './auth/api'
import type { AuthClient } from './auth/api'
import type { WorkspaceClient } from './workspaces/api'
import type { PeopleClient } from './people/api'
import type { SitesClient } from './sites/api'
import type { InventoryClient } from './inventory/api'
import type { StaffAdministrationClient } from './staff/api'

const authContext: AuthenticatedContext = {
  user: { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', display_name: 'Primary Owner' },
  tenant: { id: '00000000-0000-4000-8000-000000000002', name: 'Example MSP' },
  role: 'owner',
  permissions: ['staff_invitations.view', 'memberships.view', 'memberships.assign_role', 'organizations.manage_access'],
  surface: 'msp',
  organization: null,
  mfa_enrollment_required: false,
}

const authClient = {
  listSessions: vi.fn().mockResolvedValue([]),
  loadMfa: vi.fn().mockResolvedValue({ totpEnabled: false, recoveryCodeTotal: 0, recoveryCodeUnused: 0 }),
  listApiTokens: vi.fn().mockResolvedValue({ tokens: [], permissions: [] }),
} as unknown as AuthClient

const portalContext: AuthenticatedContext = {
  ...authContext,
  user: { ...authContext.user, email: 'client@example.com', display_name: 'Client User' },
  role: 'client_user',
  permissions: ['workspaces.view', 'documents.view'],
  surface: 'client_portal',
  organization: { id: '00000000-0000-4000-8000-000000000010', name: 'Acme Dental' },
}
const loadOrganization = vi.fn().mockResolvedValue({
  kind: 'organization',
  id: '00000000-0000-4000-8000-000000000010',
  name: 'Acme Dental',
  classifications: ['client'],
  capabilities: ['overview', 'people', 'sites', 'documentation', 'files', 'assets', 'licenses', 'networks', 'domains', 'certificates', 'credentials', 'services', 'tickets', 'vendors', 'recycle_bin'],
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
  searchOrganizations: vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 15, has_more: false }),
} as unknown as WorkspaceClient
const listPeople = vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 25, count: 0, has_more: false })
const peopleClient = {
  list: listPeople,
  create: vi.fn(),
  update: vi.fn(),
  archive: vi.fn(),
} as unknown as PeopleClient
const listSites = vi.fn().mockResolvedValue({ results: [], count: 0 })
const sitesClient = {
  list: listSites,
  create: vi.fn(),
  update: vi.fn(),
  archive: vi.fn(),
  createLocation: vi.fn(),
  updateLocation: vi.fn(),
  archiveLocation: vi.fn(),
} as unknown as SitesClient
const listAssets = vi.fn().mockResolvedValue({ results: [], page: 1, page_size: 50, count: 0, has_more: false, can_manage: true })
const inventoryClient = {
  listAssets,
  listModelChoices: vi.fn().mockResolvedValue({ results: [] }),
  assetCsvExportUrl: vi.fn().mockReturnValue('/assets.csv'),
  assetCsvTemplateUrl: vi.fn().mockReturnValue('/assets-template.csv'),
} as unknown as InventoryClient
const staffAdministrationClient = {
  members: vi.fn().mockResolvedValue([]),
  invitations: vi.fn().mockResolvedValue([]),
} as unknown as StaffAdministrationClient
const app = (initialPath: string) => <App initialPath={initialPath} initialAuthContext={authContext} authClient={authClient} staffAdministrationClient={staffAdministrationClient} workspaceClient={workspaceClient} peopleClient={peopleClient} sitesClient={sitesClient} inventoryClient={inventoryClient} />

describe('application shell', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps a client account inside the dedicated portal surface', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify({ count: 0, results: [] }), { status: 200 }))
    render(<App initialPath="/overview" initialAuthContext={portalContext} authClient={authClient} />)

    expect(await screen.findByRole('heading', { name: 'Acme Dental' })).toBeInTheDocument()
    expect(screen.getByText('Only approved, current client-visible STATIC publications appear here.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Organizations' })).not.toBeInTheDocument()
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(await screen.findByText(/no documentation has been published/i)).toBeInTheDocument()
  })

  it('renders sectioned navigation and the active route', () => {
    render(app('/overview'))

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Documentation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Compliance' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Files' })).toHaveAttribute('href', '/files')
    expect(screen.getByRole('link', { name: 'Certificates' })).toHaveAttribute('href', '/certificates')
    expect(screen.queryByRole('link', { name: 'Accounting' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Tickets' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Activity' })).not.toBeInTheDocument()
    expect(screen.getByText('Reusable documentation and templates')).toBeInTheDocument()
    expect(screen.getByText('TekDocs 0.8.41')).toBeInTheDocument()
  })

  it('does not attach a stale release promise to the hidden activity placeholder', () => {
    render(app('/activity'))

    expect(screen.getByRole('heading', { name: 'Activity' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Not scheduled' })).toBeInTheDocument()
    expect(screen.queryByText('Planned 0.1.0')).not.toBeInTheDocument()
  })

  it('provides stable page-level help without loading remote content', async () => {
    const user = userEvent.setup()
    // The documentation route fetches as soon as it mounts. Leaving that request
    // unstubbed made this test assert on help while the page was still resolving,
    // so whether the page's own code ran at all depended on how long the rest of the
    // suite took. Stub it and wait for the page to settle before touching help.
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ count: 0, results: [] }), { status: 200 }))
    render(app('/documentation'))
    expect(await screen.findByText('No documents have been added to this workspace.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Help for Documentation' }))
    const help = within(screen.getByRole('dialog', { name: 'Documentation help' }))
    expect(help.getByText(/reuse live or pinned blocks/)).toBeInTheDocument()
    expect(help.getByRole('status')).toHaveTextContent('public Wiki guide has not been published')
    expect(screen.queryByRole('link', { name: /Open the full guide/ })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Documentation help' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Help for Documentation' })).toHaveFocus()
  })

  it('renders MSP-owned assets instead of an aggregate placeholder', async () => {
    render(app('/assets'))

    expect(await screen.findByRole('heading', { name: 'Assets' })).toBeInTheDocument()
    expect(await screen.findByText('No assets have been created for this MSP workspace.')).toBeInTheDocument()
    expect(listAssets).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'msp', id: authContext.tenant.id, organization: null }),
      1,
      expect.any(AbortSignal),
    )
  })

  it('provides profile routes through the account menu', async () => {
    const user = userEvent.setup()
    render(app('/overview'))

    await user.click(screen.getByRole('button', { name: /Account menu for Primary Owner/i }))
    expect(screen.getByRole('menuitem', { name: 'Settings' })).toHaveAttribute('href', '/settings')
    expect(screen.getByRole('menuitem', { name: 'Staff & invitations' })).toHaveAttribute('href', '/staff')
    expect(screen.queryByRole('menuitem', { name: 'Integrations' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: 'Settings' }))
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  it('opens owner staff administration from the profile menu', async () => {
    const user = userEvent.setup()
    render(app('/overview'))

    await user.click(screen.getByRole('button', { name: /Account menu for Primary Owner/i }))
    await user.click(screen.getByRole('menuitem', { name: 'Staff & invitations' }))

    expect(await screen.findByRole('heading', { name: 'Staff & invitations' })).toBeInTheDocument()
    expect(await screen.findByText('No invitations match this view.')).toBeInTheDocument()
  })

  it('collapses the desktop navigation without removing accessible links', async () => {
    const user = userEvent.setup()
    render(app('/organizations'))

    expect(await screen.findByRole('heading', { name: 'Organizations' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Collapse navigation' }))
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument()
  })

  it('resolves a deep-linked organization route through the workspace boundary', async () => {
    render(app('/workspaces/organizations/00000000-0000-4000-8000-000000000010/overview'))

    expect(await screen.findByRole('heading', { name: 'Acme Dental' })).toBeInTheDocument()
    expect(loadOrganization).toHaveBeenCalledWith('00000000-0000-4000-8000-000000000010', expect.any(AbortSignal))
    expect(screen.getAllByText('Client workspace')).toHaveLength(2)
    expect(document.title).toBe('Acme Dental · Overview · TekDocs')
  })

  it('shows only the selected organization capability union in navigation', async () => {
    render(app('/workspaces/organizations/00000000-0000-4000-8000-000000000010/overview'))

    await screen.findByRole('heading', { name: 'Acme Dental' })
    const sidebar = within(screen.getByRole('complementary'))
    expect(sidebar.getByRole('link', { name: 'Assets' })).toHaveAttribute('href', '/workspaces/organizations/00000000-0000-4000-8000-000000000010/assets')
    expect(sidebar.getByRole('link', { name: 'Files' })).toHaveAttribute('href', '/workspaces/organizations/00000000-0000-4000-8000-000000000010/files')
    expect(sidebar.getByRole('link', { name: 'Certificates' })).toHaveAttribute('href', '/workspaces/organizations/00000000-0000-4000-8000-000000000010/certificates')
    expect(sidebar.queryByRole('link', { name: 'Organizations' })).not.toBeInTheDocument()
    expect(sidebar.queryByRole('link', { name: 'Products' })).not.toBeInTheDocument()
    expect(sidebar.queryByRole('link', { name: 'Accounting' })).not.toBeInTheDocument()
    for (const link of sidebar.getAllByRole('link')) {
      expect(link.getAttribute('href')).toMatch(/^\/workspaces\/organizations\/00000000-0000-4000-8000-000000000010\//)
    }
    expect(sidebar.getByRole('link', { name: 'Recycle bin' })).toHaveAttribute('href', '/workspaces/organizations/00000000-0000-4000-8000-000000000010/recycle_bin')
    expect(screen.getByRole('navigation', { name: 'Governance' })).toBeInTheDocument()
  })

  it('loads People through the selected organization boundary', async () => {
    render(app('/workspaces/organizations/00000000-0000-4000-8000-000000000010/people'))

    expect(await screen.findByRole('heading', { name: 'People' })).toBeInTheDocument()
    expect(await screen.findByText('No people have been added to this workspace.')).toBeInTheDocument()
    await vi.waitFor(() => expect(listPeople).toHaveBeenCalledWith(
      { organizationId: '00000000-0000-4000-8000-000000000010' },
      expect.objectContaining({ ordering: 'full_name' }),
      expect.any(AbortSignal),
    ))
  })

  it('loads Sites through the selected organization boundary', async () => {
    render(app('/workspaces/organizations/00000000-0000-4000-8000-000000000010/sites'))

    expect(await screen.findByRole('heading', { name: 'Sites' })).toBeInTheDocument()
    expect(await screen.findByText('No sites have been added to Acme Dental.')).toBeInTheDocument()
    expect(listSites).toHaveBeenCalledWith(
      { organizationId: '00000000-0000-4000-8000-000000000010' },
      '',
      expect.any(AbortSignal),
    )
  })

  it('clears retained organization context when returning to an MSP route', async () => {
    const user = userEvent.setup()
    render(app('/workspaces/organizations/00000000-0000-4000-8000-000000000010/overview'))

    await screen.findByRole('heading', { name: 'Acme Dental' })
    await user.click(screen.getByRole('button', { name: /Current workspace: Acme Dental/ }))
    await user.click(screen.getByRole('button', { name: 'Back to Example MSP. MSP workspace' }))

    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Current workspace: Example MSP/ })).toBeInTheDocument()
    expect(document.title).toBe('Example MSP · Overview · TekDocs')
    const sidebar = within(screen.getByRole('complementary'))
    expect(sidebar.getByRole('link', { name: 'Organizations' })).toHaveAttribute('href', '/organizations')
    expect(sidebar.queryByRole('link', { name: 'Accounting' })).not.toBeInTheDocument()
    for (const link of sidebar.getAllByRole('link')) expect(link.getAttribute('href')).not.toMatch(/^\/workspaces\/organizations\//)
  })
})
