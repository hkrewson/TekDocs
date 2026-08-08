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
import type { WorkspaceClient, WorkspaceContext } from './workspaces/api'
import { WorkspaceOverview } from './workspaces/WorkspaceOverview'
const EditorSpike = lazy(async () => {
  const module = await import('./editor/EditorSpike')
  return { default: module.EditorSpike }
})

type NavigationItem = {
  label: string
  path: string
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
  { label: 'Overview', path: '/overview', icon: Activity },
  { label: 'Documentation', path: '/documentation', icon: BookOpenText },
  { label: 'Organizations', path: '/organizations', icon: Building2 },
  { label: 'People', path: '/people', icon: UsersRound },
  { label: 'Assets', path: '/assets', icon: Boxes },
  { label: 'Networks', path: '/networks', icon: Network },
  { label: 'Credentials', path: '/credentials', icon: KeyRound },
]

const governanceNavigation: NavigationItem[] = [
  { label: 'Compliance', path: '/compliance', icon: ShieldCheck },
  { label: 'Activity', path: '/activity', icon: FileCheck2 },
]

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="brand" aria-label="TekDocs">
      <span className="brand-mark" aria-hidden="true">T</span>
      {!collapsed && <span className="brand-name">TekDocs</span>}
    </div>
  )
}

function NavSection({ items, label, collapsed, onNavigate }: { items: NavigationItem[]; label: string; collapsed: boolean; onNavigate: () => void }) {
  return (
    <nav className="nav-list" aria-label={label}>
      {items.map(({ label, path, icon: Icon }) => (
        <AppLink
          key={path}
          to={path}
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

function workspaceInitials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || 'TD'
}

function Sidebar({ collapsed, mobileOpen, onCollapse, onMobileClose, workspaceName, workspaceLabel, workspaceLoading }: {
  collapsed: boolean
  mobileOpen: boolean
  onCollapse: () => void
  onMobileClose: () => void
  workspaceName: string
  workspaceLabel: string
  workspaceLoading: boolean
}) {
  return (
    <>
      {mobileOpen && <button className="sidebar-backdrop" onClick={onMobileClose} aria-label="Close navigation" />}
      <aside className={`sidebar${collapsed ? ' collapsed' : ''}${mobileOpen ? ' mobile-open' : ''}`}>
        <div className="sidebar-topline">
          <Brand collapsed={collapsed} />
          <button className="icon-button desktop-collapse" onClick={onCollapse} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
          <button className="icon-button mobile-close" onClick={onMobileClose} aria-label="Close navigation"><X size={19} /></button>
        </div>

        <button className="tenant-switcher" type="button" title={collapsed ? workspaceName : undefined} disabled={workspaceLoading}>
          <span className="tenant-initials">{workspaceInitials(workspaceName)}</span>
          {!collapsed && <><span className="tenant-copy"><strong>{workspaceLoading ? 'Loading workspace…' : workspaceName}</strong><span>{workspaceLabel}</span></span><ChevronDown size={15} /></>}
        </button>

        <div className="sidebar-scroll">
          <NavSection items={workspaceNavigation} label="Workspace" collapsed={collapsed} onNavigate={onMobileClose} />
          <div className="nav-divider" />
          <NavSection items={governanceNavigation} label="Governance" collapsed={collapsed} onNavigate={onMobileClose} />
        </div>
      </aside>
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
      <PageHeader title="Overview" description="TekDocs 0.1.3 adds routable organization workspaces and verified scope boundaries." />
      <section className="content-section">
        <div className="section-heading"><h2>Foundation status</h2><span>Milestone 0.1.3</span></div>
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
    let active = true
    workspaceClient.loadOrganization(organizationId)
      .then((workspace) => { if (active) setOrganizationWorkspace({ phase: 'ready', organizationId, workspace }) })
      .catch((error: unknown) => { if (active) setOrganizationWorkspace({ phase: 'error', organizationId, message: workspaceErrorMessage(error) }) })
    return () => { active = false }
  }, [organizationId, workspaceClient])

  const visibleWorkspaceState = organizationId && (organizationWorkspace.phase === 'idle' || organizationWorkspace.organizationId !== organizationId)
    ? { phase: 'loading' as const }
    : organizationWorkspace
  const selectedWorkspace = visibleWorkspaceState.phase === 'ready' ? visibleWorkspaceState.workspace : null
  const workspaceName = organizationId ? selectedWorkspace?.name ?? shellContext.tenant.name : shellContext.tenant.name
  const workspaceLabel = organizationId
    ? selectedWorkspace
      ? `${selectedWorkspace.classifications.join(' · ')} workspace`
      : 'Organization workspace'
    : 'MSP workspace'

  return (
    <div className="app-shell">
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCollapse={() => setCollapsed((value) => !value)} onMobileClose={() => setMobileOpen(false)} workspaceName={workspaceName} workspaceLabel={workspaceLabel} workspaceLoading={Boolean(organizationId) && visibleWorkspaceState.phase === 'loading'} />
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
