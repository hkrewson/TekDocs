import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Link, MemoryRouter, Navigate, NavLink, Route, Routes, useLocation, useMatch } from 'react-router'
import {
  Activity,
  BookOpenText,
  Boxes,
  Building2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  FileCheck2,
  KeyRound,
  LogOut,
  Menu,
  Network,
  Package,
  Plug,
  Search,
  Settings,
  ShieldCheck,
  UsersRound,
  X,
} from 'lucide-react'
import { AuthGate } from './auth/AuthGate'
import { browserAuthClient } from './auth/api'
import type { AuthClient, AuthenticatedContext } from './auth/api'
import { SecuritySettings } from './auth/SecuritySettings'
import { Organizations } from './organizations/Organizations'
import { browserWorkspaceClient } from './workspaces/api'
import type { WorkspaceCapability, WorkspaceClient, WorkspaceContext } from './workspaces/api'
import { classificationSummary, organizationWorkspacePath, workspaceAreaFromPath } from './workspaces/navigation'
import type { WorkspaceArea } from './workspaces/navigation'
import { WorkspaceOverview } from './workspaces/WorkspaceOverview'
import { WorkspaceSwitcher } from './workspaces/WorkspaceSwitcher'
const EditorSpike = lazy(async () => {
  const module = await import('./editor/EditorSpike')
  return { default: module.EditorSpike }
})

type NavigationItem = {
  label: string
  path: string
  area: WorkspaceCapability
  icon: typeof BookOpenText
}

function AppLink({ to, className, children, ...props }: {
  to: string
  className?: string
  children: ReactNode
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  return <NavLink {...props} to={to} className={({ isActive }) => `${className ?? ''}${isActive ? ' active' : ''}`}>{children}</NavLink>
}

const workspaceNavigation: NavigationItem[] = [
  { label: 'Overview', path: '/overview', area: 'overview', icon: Activity },
  { label: 'Documentation', path: '/documentation', area: 'documentation', icon: BookOpenText },
  { label: 'Organizations', path: '/organizations', area: 'organizations', icon: Building2 },
  { label: 'People', path: '/people', area: 'people', icon: UsersRound },
  { label: 'Assets', path: '/assets', area: 'assets', icon: Boxes },
  { label: 'Products', path: '/overview', area: 'products', icon: Package },
  { label: 'Networks', path: '/networks', area: 'networks', icon: Network },
  { label: 'Credentials', path: '/credentials', area: 'credentials', icon: KeyRound },
]

const governanceNavigation: NavigationItem[] = [
  { label: 'Compliance', path: '/compliance', area: 'compliance', icon: ShieldCheck },
  { label: 'Activity', path: '/activity', area: 'activity', icon: FileCheck2 },
]

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="brand" aria-label="TekDocs">
      <span className="brand-mark" aria-hidden="true">T</span>
      {!collapsed && <span className="brand-name">TekDocs</span>}
    </div>
  )
}

function NavSection({ items, label, collapsed, onNavigate, workspace }: { items: NavigationItem[]; label: string; collapsed: boolean; onNavigate: () => void; workspace: WorkspaceContext | null }) {
  const availableItems = workspace
    ? items.filter((item) => workspace.capabilities.includes(item.area))
    : items.filter((item) => item.area !== 'products')
  return (
    <nav className="nav-list" aria-label={label}>
      {availableItems.map(({ label, path, area, icon: Icon }) => (
        <AppLink
          key={area}
          to={workspace ? organizationWorkspacePath(workspace, area) : path}
          onClick={onNavigate}
          className="nav-link"
          title={collapsed ? label : undefined}
        >
          <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
          {!collapsed && <span>{label}</span>}
        </AppLink>
      ))}
    </nav>
  )
}

function Sidebar({ collapsed, mobileOpen, onCollapse, onMobileClose, tenant, workspace, activeArea, workspaceClient, workspaceLoading, organizationRoute }: {
  collapsed: boolean
  mobileOpen: boolean
  onCollapse: () => void
  onMobileClose: () => void
  tenant: AuthenticatedContext['tenant']
  workspace: WorkspaceContext | null
  activeArea: WorkspaceArea
  workspaceClient: WorkspaceClient
  workspaceLoading: boolean
  organizationRoute: boolean
}) {
  return (
    <>
      <aside className={`sidebar${collapsed ? ' collapsed' : ''}${mobileOpen ? ' mobile-open' : ''}`}>
        <div className="sidebar-topline">
          <Brand collapsed={collapsed} />
          <button className="icon-button desktop-collapse" onClick={onCollapse} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
          <button className="icon-button mobile-close" onClick={onMobileClose} aria-label="Close navigation"><X size={19} /></button>
        </div>

        <WorkspaceSwitcher tenant={tenant} activeWorkspace={workspace} activeArea={activeArea} client={workspaceClient} collapsed={collapsed} workspaceLoading={workspaceLoading} onNavigate={onMobileClose} />

        <div className="sidebar-scroll">
          {organizationRoute && !workspace
            ? <p className="workspace-navigation-state">{workspaceLoading ? 'Loading navigation…' : 'Workspace unavailable'}</p>
            : <><NavSection items={workspaceNavigation} label="Workspace" collapsed={collapsed} onNavigate={onMobileClose} workspace={workspace} />
              {(!workspace || governanceNavigation.some((item) => workspace.capabilities.includes(item.area))) && <><div className="nav-divider" /><NavSection items={governanceNavigation} label="Governance" collapsed={collapsed} onNavigate={onMobileClose} workspace={workspace} /></>}</>}
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" onClick={onMobileClose} aria-label="Close navigation" />}
    </>
  )
}

function ProfileMenu({ user, onSignOut, signingOut }: {
  user: AuthenticatedContext['user']
  onSignOut: () => Promise<void>
  signingOut: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  return (
    <div className="profile-menu" ref={ref}>
      <button className="profile-trigger" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label={`Account menu for ${user.display_name}`}>
        <CircleUserRound size={22} />
        <span className="profile-copy"><strong>{user.display_name}</strong><span>{user.email}</span></span>
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="profile-popover" role="menu">
          <AppLink to="/settings" role="menuitem" onClick={() => setOpen(false)}><Settings size={17} />Settings</AppLink>
          <AppLink to="/integrations" role="menuitem" onClick={() => setOpen(false)}><Plug size={17} />Integrations</AppLink>
          <button type="button" role="menuitem" disabled={signingOut} onClick={() => { setOpen(false); void onSignOut() }}><LogOut size={17} />{signingOut ? 'Signing out…' : 'Sign out'}</button>
        </div>
      )}
    </div>
  )
}

function PageHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <header className="page-header">
      <div><h1>{title}</h1><p>{description}</p></div>
      {action}
    </header>
  )
}

const plannedAreas: Record<string, { title: string; description: string; release: string; capabilities: string[] }> = {
  '/people': { title: 'People', description: 'MSP staff, client employees, contacts, and access associations.', release: '0.2.0', capabilities: ['Contact records', 'Organization membership', 'Portal access boundary'] },
  '/assets': { title: 'Assets', description: 'Hardware, software, licensing, warranty, and cost records.', release: '0.4.0', capabilities: ['Hardware inventory', 'Software and licenses', 'Cost visibility controls'] },
  '/networks': { title: 'Networks', description: 'Sites, VLANs, subnets, addresses, interfaces, and circuits.', release: '0.5.0', capabilities: ['Address management', 'Device relationships', 'NetBox-compatible identifiers'] },
  '/credentials': { title: 'Credentials', description: 'Encrypted secrets with explicit reveal and audit boundaries.', release: '0.4.0', capabilities: ['Envelope encryption', 'Reauthentication', 'Key rotation'] },
  '/compliance': { title: 'Compliance', description: 'Control ownership, evidence, reviews, and immutable evidence bundles.', release: '0.8.0', capabilities: ['Frameworks and controls', 'Evidence links', 'Review reminders'] },
  '/activity': { title: 'Activity', description: 'Append-only security and business change history.', release: '0.1.0', capabilities: ['Request correlation', 'Permission-aware history', 'Exportable evidence'] },
  '/integrations': { title: 'Integrations', description: 'Secure provider connections, jobs, webhooks, and reconciliation.', release: '0.7.0', capabilities: ['Provider contracts', 'Scheduled jobs', 'Conflict review'] },
}

function PlannedPage({ path }: { path: string }) {
  const area = plannedAreas[path]
  return (
    <>
      <PageHeader title={area.title} description={area.description} />
      <section className="content-section">
        <div className="section-heading"><h2>Planned for {area.release}</h2><span>Foundation established</span></div>
        <ul className="capability-list">{area.capabilities.map((capability) => <li key={capability}>{capability}</li>)}</ul>
      </section>
    </>
  )
}

function Overview() {
  return (
    <>
      <PageHeader title="Overview" description="TekDocs 0.1.4 adds bounded workspace discovery and URL-scoped navigation." />
      <section className="content-section">
        <div className="section-heading"><h2>Foundation status</h2><span>Milestone 0.1.4</span></div>
        <div className="status-table" role="table" aria-label="Foundation status">
          {[
            ['Application shell', 'Available'],
            ['Tenant and entity primitives', 'Available'],
            ['Tenant and organization isolation', 'Available'],
            ['Organization records and classifications', 'Available'],
            ['Owner authentication', 'Available'],
            ['Email delivery foundation', 'Available'],
            ['Invitation issuance API', 'Available'],
            ['Invitation account activation', 'Available'],
            ['Password recovery', 'Available'],
            ['Session security', 'Available'],
            ['Reusable documentation', 'Milestone 0.3.0'],
          ].map(([name, status]) => <div className="status-row" role="row" key={name}><span role="cell">{name}</span><span role="cell">{status}</span></div>)}
        </div>
      </section>
    </>
  )
}

function Documentation() {
  return (
    <>
      <PageHeader title="Documentation" description="Canonical Markdown with a rich editor and stable block identity." action={<button className="primary-button">New document</button>} />
      <Suspense fallback={<section className="content-section">Loading editor…</section>}><EditorSpike /></Suspense>
    </>
  )
}

type OrganizationWorkspaceState =
  | { phase: 'idle' }
  | { phase: 'ready'; organizationId: string; workspace: WorkspaceContext }
  | { phase: 'error'; organizationId: string; message: string }

function workspaceErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'The workspace could not be loaded.'
}

function OrganizationWorkspaceRoute({ state }: { state: OrganizationWorkspaceState | { phase: 'loading' } }) {
  if (state.phase === 'loading' || state.phase === 'idle') return <section className="content-section" role="status">Loading organization workspace…</section>
  if (state.phase === 'error') {
    return <section className="content-section workspace-error" role="alert"><h1>Workspace unavailable</h1><p>{state.message}</p><Link className="secondary-button" to="/organizations">Return to organizations</Link></section>
  }
  return <WorkspaceOverview workspace={state.workspace} />
}

const organizationAreaDetails: Partial<Record<WorkspaceCapability, { title: string; description: string; release: string }>> = {
  documentation: { title: 'Documentation', description: 'Documentation owned by or explicitly referenced into this organization.', release: '0.2.2' },
  people: { title: 'People', description: 'Employees and contacts scoped to this organization.', release: '0.1.5' },
  assets: { title: 'Assets', description: 'Hardware and software assigned to this organization.', release: '0.3.5' },
  products: { title: 'Products', description: 'Supplier product and model templates owned by this organization.', release: '0.3.3' },
  networks: { title: 'Networks', description: 'Network records scoped to this organization.', release: '0.4.1' },
  credentials: { title: 'Credentials', description: 'Protected credential records scoped to this organization.', release: '0.3.1' },
}

function OrganizationAreaRoute({ state, area }: { state: OrganizationWorkspaceState | { phase: 'loading' }; area: WorkspaceCapability }) {
  if (area === 'overview') return <OrganizationWorkspaceRoute state={state} />
  if (state.phase === 'loading' || state.phase === 'idle') return <section className="content-section" role="status">Loading organization workspace…</section>
  if (state.phase === 'error') return <OrganizationWorkspaceRoute state={state} />
  if (!state.workspace.capabilities.includes(area) || !organizationAreaDetails[area]) {
    return <section className="content-section workspace-error" role="alert"><h1>Area unavailable</h1><p>This area is not available for the selected organization.</p><Link className="secondary-button" to={organizationWorkspacePath(state.workspace, 'overview')}>Return to overview</Link></section>
  }
  const details = organizationAreaDetails[area]
  return (
    <>
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link to={organizationWorkspacePath(state.workspace, 'overview')}>{state.workspace.name}</Link><span aria-hidden="true">/</span><span aria-current="page">{details.title}</span></nav>
      <PageHeader title={details.title} description={details.description} />
      <section className="content-section"><div className="section-heading"><h2>Planned for {details.release}</h2><span>{classificationSummary(state.workspace.classifications)} workspace</span></div><p className="workspace-area-note">The route and ownership context are established. The domain records arrive in their scheduled slice.</p></section>
    </>
  )
}

export function ApplicationShell({ authContext, authClient, workspaceClient, onSignOut, signingOut = false, signOutError = null }: {
  authContext: AuthenticatedContext
  authClient: AuthClient
  workspaceClient: WorkspaceClient
  onSignOut: () => Promise<void>
  signingOut?: boolean
  signOutError?: string | null
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [shellContext, setShellContext] = useState(authContext)
  const [organizationWorkspace, setOrganizationWorkspace] = useState<OrganizationWorkspaceState>({ phase: 'idle' })
  const location = useLocation()
  const organizationMatch = useMatch('/workspaces/organizations/:organizationId/*')
  const organizationId = organizationMatch?.params.organizationId

  useEffect(() => {
    if (!organizationId) return
    const controller = new AbortController()
    workspaceClient.loadOrganization(organizationId, controller.signal)
      .then((workspace) => { if (!controller.signal.aborted) setOrganizationWorkspace({ phase: 'ready', organizationId, workspace }) })
      .catch((error: unknown) => { if (!controller.signal.aborted) setOrganizationWorkspace({ phase: 'error', organizationId, message: workspaceErrorMessage(error) }) })
    return () => controller.abort()
  }, [organizationId, workspaceClient])

  const visibleWorkspaceState = !organizationId
    ? { phase: 'idle' as const }
    : organizationWorkspace.phase === 'idle' || organizationWorkspace.organizationId !== organizationId
      ? { phase: 'loading' as const }
      : organizationWorkspace
  const selectedWorkspace = visibleWorkspaceState.phase === 'ready' ? visibleWorkspaceState.workspace : null
  const activeArea = workspaceAreaFromPath(location.pathname)

  useEffect(() => {
    const areaLabel = activeArea.charAt(0).toUpperCase() + activeArea.slice(1)
    document.title = `${selectedWorkspace?.name ?? shellContext.tenant.name} · ${areaLabel} · TekDocs`
  }, [activeArea, selectedWorkspace?.name, shellContext.tenant.name])

  return (
    <div className="app-shell">
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCollapse={() => setCollapsed((value) => !value)} onMobileClose={() => setMobileOpen(false)} tenant={shellContext.tenant} workspace={selectedWorkspace} activeArea={activeArea} workspaceClient={workspaceClient} workspaceLoading={Boolean(organizationId) && visibleWorkspaceState.phase === 'loading'} organizationRoute={Boolean(organizationId)} />
      <div className={`app-body${collapsed ? ' sidebar-collapsed' : ''}`}>
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <label className="search-field"><Search size={17} /><span className="sr-only">Search TekDocs</span><input placeholder="Search TekDocs" disabled /></label>
          <ProfileMenu user={shellContext.user} onSignOut={onSignOut} signingOut={signingOut} />
        </header>
        <main className="main-content" key={location.pathname}>
          {signOutError && <div className="shell-alert" role="alert">{signOutError}</div>}
          <Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/documentation" element={<Documentation />} />
            <Route path="/organizations" element={<Organizations />} />
            <Route path="/settings" element={<SecuritySettings client={authClient} context={shellContext} onProfileUpdated={setShellContext} />} />
            {Object.keys(plannedAreas).map((path) => <Route key={path} path={path} element={<PlannedPage path={path} />} />)}
            <Route path="/workspaces/organizations/:organizationId" element={<Navigate to="overview" replace />} />
            <Route path="/workspaces/organizations/:organizationId/overview" element={<OrganizationWorkspaceRoute state={visibleWorkspaceState} />} />
            {(Object.keys(organizationAreaDetails) as WorkspaceCapability[]).map((area) => <Route key={area} path={`/workspaces/organizations/:organizationId/${area}`} element={<OrganizationAreaRoute state={visibleWorkspaceState} area={area} />} />)}
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export function App({ initialPath, authClient = browserAuthClient, workspaceClient = browserWorkspaceClient, initialAuthContext }: {
  initialPath?: string
  authClient?: AuthClient
  workspaceClient?: WorkspaceClient
  initialAuthContext?: AuthenticatedContext
}) {
  const application = (
    <AuthGate client={authClient} initialContext={initialAuthContext}>
      {({ context, signOut, signingOut, signOutError }) => (
        <ApplicationShell
          authContext={context}
          authClient={authClient}
          workspaceClient={workspaceClient}
          onSignOut={signOut}
          signingOut={signingOut}
          signOutError={signOutError}
        />
      )}
    </AuthGate>
  )
  return initialPath
    ? <MemoryRouter initialEntries={[initialPath]}>{application}</MemoryRouter>
    : <BrowserRouter>{application}</BrowserRouter>
}
