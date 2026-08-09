import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Link, MemoryRouter, Navigate, NavLink, Route, Routes, useLocation, useMatch } from 'react-router'
import {
  Activity,
  BadgeCheck,
  BadgeDollarSign,
  BookOpenText,
  Boxes,
  BriefcaseBusiness,
  Building2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  File,
  FileCheck2,
  Globe2,
  Handshake,
  KeyRound,
  ListPlus,
  LogOut,
  Menu,
  MapPin,
  Network,
  Package,
  Plug,
  Search,
  Settings,
  ShieldCheck,
  ScrollText,
  TicketCheck,
  Trash2,
  UsersRound,
  X,
} from 'lucide-react'
import { AuthGate } from './auth/AuthGate'
import { AccessControl } from './access-control/AccessControl'
import { browserAccessControlClient } from './access-control/api'
import type { AccessControlClient } from './access-control/api'
import { browserAuthClient } from './auth/api'
import type { AuthClient, AuthenticatedContext } from './auth/api'
import { SecuritySettings } from './auth/SecuritySettings'
import { CustomFields } from './custom-fields/CustomFields'
import { browserCustomFieldsClient } from './custom-fields/api'
import type { CustomFieldsClient } from './custom-fields/api'
import { Organizations } from './organizations/Organizations'
import { People } from './people/People'
import { browserPeopleClient } from './people/api'
import type { PeopleClient } from './people/api'
import { browserRelationshipsClient } from './relationships/api'
import type { RelationshipsClient } from './relationships/api'
import { RecycleBin } from './recycle-bin/RecycleBin'
import { browserRecycleBinClient } from './recycle-bin/api'
import type { RecycleBinClient } from './recycle-bin/api'
import { Sites } from './sites/Sites'
import { browserSitesClient } from './sites/api'
import type { SitesClient } from './sites/api'
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

type NavigationSection = {
  label: string
  items: NavigationItem[]
}

function AppLink({ to, className, children, ...props }: {
  to: string
  className?: string
  children: ReactNode
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  return <NavLink {...props} to={to} className={({ isActive }) => `${className ?? ''}${isActive ? ' active' : ''}`}>{children}</NavLink>
}

const navigationSections: NavigationSection[] = [
  { label: 'Workspace', items: [
    { label: 'Overview', path: '/overview', area: 'overview', icon: Activity },
    { label: 'Organizations', path: '/organizations', area: 'organizations', icon: Building2 },
    { label: 'People', path: '/people', area: 'people', icon: UsersRound },
    { label: 'Sites', path: '/sites', area: 'sites', icon: MapPin },
    { label: 'Documentation', path: '/documentation', area: 'documentation', icon: BookOpenText },
    { label: 'Files', path: '/files', area: 'files', icon: File },
  ] },
  { label: 'Infrastructure', items: [
    { label: 'Assets', path: '/assets', area: 'assets', icon: Boxes },
    { label: 'Licenses', path: '/licenses', area: 'licenses', icon: ScrollText },
    { label: 'Networks', path: '/networks', area: 'networks', icon: Network },
    { label: 'Domains', path: '/domains', area: 'domains', icon: Globe2 },
    { label: 'Certificates', path: '/certificates', area: 'certificates', icon: BadgeCheck },
    { label: 'Credentials', path: '/credentials', area: 'credentials', icon: KeyRound },
    { label: 'Services', path: '/services', area: 'services', icon: BriefcaseBusiness },
  ] },
  { label: 'Relationships', items: [
    { label: 'Vendors', path: '/vendors', area: 'vendors', icon: Handshake },
    { label: 'Products', path: '/products', area: 'products', icon: Package },
    { label: 'Tickets', path: '/tickets', area: 'tickets', icon: TicketCheck },
  ] },
  { label: 'Business', items: [
    { label: 'Accounting', path: '/accounting', area: 'accounting', icon: BadgeDollarSign },
  ] },
  { label: 'Governance', items: [
    { label: 'Custom fields', path: '/custom-fields', area: 'custom_fields', icon: ListPlus },
    { label: 'Compliance', path: '/compliance', area: 'compliance', icon: ShieldCheck },
    { label: 'Activity', path: '/activity', area: 'activity', icon: FileCheck2 },
    { label: 'Recycle bin', path: '/recycle-bin', area: 'recycle_bin', icon: Trash2 },
    { label: 'Integrations', path: '/integrations', area: 'integrations', icon: Plug },
  ] },
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
  return (
    <nav className="nav-list" aria-label={label}>
      {!collapsed && <span className="nav-section-label">{label}</span>}
      {items.map(({ label, path, area, icon: Icon }) => (
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
  const availableSections = navigationSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => !workspace || workspace.capabilities.includes(item.area)),
    }))
    .filter((section) => section.items.length > 0)
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
            : availableSections.map((section, index) => (
              <div key={section.label}>
                {index > 0 && <div className="nav-divider" />}
                <NavSection items={section.items} label={section.label} collapsed={collapsed} onNavigate={onMobileClose} workspace={workspace} />
              </div>
            ))}
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" onClick={onMobileClose} aria-label="Close navigation" />}
    </>
  )
}

function ProfileMenu({ user, canManageAccess, onSignOut, signingOut }: {
  user: AuthenticatedContext['user']
  canManageAccess: boolean
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
          {canManageAccess && <AppLink to="/access-control" role="menuitem" onClick={() => setOpen(false)}><ShieldCheck size={17} />Access control</AppLink>}
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
  '/files': { title: 'Files', description: 'Managed files and attachments with explicit ownership and references.', release: '0.3.8', capabilities: ['Safe uploads', 'Ownership scope', 'Permission-aware references'] },
  '/assets': { title: 'Assets', description: 'Hardware, software, licensing, warranty, and cost records.', release: '0.3.5', capabilities: ['Hardware inventory', 'Software and licenses', 'Cost visibility controls'] },
  '/licenses': { title: 'Licenses', description: 'Software entitlements, seats, renewals, and client assignments.', release: '0.3.6', capabilities: ['License inventory', 'Seat assignments', 'Renewal dates'] },
  '/networks': { title: 'Networks', description: 'Sites, VLANs, subnets, addresses, interfaces, and circuits.', release: '0.5.0', capabilities: ['Address management', 'Device relationships', 'NetBox-compatible identifiers'] },
  '/domains': { title: 'Domains', description: 'Domain registration, DNS ownership, and expiration monitoring.', release: '0.7.8', capabilities: ['Registration records', 'DNS monitoring', 'Expiry notifications'] },
  '/certificates': { title: 'Certificates', description: 'TLS endpoints, certificate chains, and expiry monitoring.', release: '0.7.9', capabilities: ['Endpoint inventory', 'Chain evidence', 'Expiry notifications'] },
  '/credentials': { title: 'Credentials', description: 'Encrypted secrets with explicit reveal and audit boundaries.', release: '0.3.1', capabilities: ['Envelope encryption', 'Reauthentication', 'Key rotation'] },
  '/services': { title: 'Services', description: 'Services, contracts, providers, and operational dependencies.', release: '0.3.7', capabilities: ['Service inventory', 'Provider relationships', 'Renewal tracking'] },
  '/vendors': { title: 'Vendors', description: 'Organizations supplying products or services to this workspace.', release: '0.3.4', capabilities: ['Relationship-derived list', 'Supplier provenance', 'Related contacts'] },
  '/products': { title: 'Products', description: 'Reusable supplier product and model definitions.', release: '0.3.3', capabilities: ['Product templates', 'Model specifications', 'Client asset provenance'] },
  '/tickets': { title: 'Tickets', description: 'Service requests associated with the active workspace.', release: 'Post-1.0', capabilities: ['Client requests', 'Object relationships', 'Portal visibility'] },
  '/accounting': { title: 'Accounting', description: 'MSP business records for billing, purchasing, and financial operations.', release: 'Post-1.0', capabilities: ['Invoices and payments', 'Quotes and recurring billing', 'Expenses and trips'] },
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
      <PageHeader title="Overview" description="TekDocs 0.1.15 stabilizes the entity, workspace, and authorization foundation before certification." />
      <section className="content-section">
        <div className="section-heading"><h2>Foundation status</h2><span>Milestone 0.1.15</span></div>
        <div className="status-table" role="table" aria-label="Foundation status">
          {[
            ['Application shell', 'Available'],
            ['Tenant and entity primitives', 'Available'],
            ['Tenant and organization isolation', 'Available'],
            ['Organization records and classifications', 'Available'],
            ['Versioned custom-field definitions', 'Available'],
            ['Typed entity links and backlinks', 'Available'],
            ['Scoped roles and access collections', 'Available'],
            ['Workspace recycle bin', 'Available'],
            ['Database-enforced audit immutability', 'Available'],
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

function OrganizationWorkspaceRoute({ state, relationshipsClient }: { state: OrganizationWorkspaceState | { phase: 'loading' }; relationshipsClient: RelationshipsClient }) {
  if (state.phase === 'loading' || state.phase === 'idle') return <section className="content-section" role="status">Loading organization workspace…</section>
  if (state.phase === 'error') {
    return <section className="content-section workspace-error" role="alert"><h1>Workspace unavailable</h1><p>{state.message}</p><Link className="secondary-button" to="/organizations">Return to organizations</Link></section>
  }
  return <WorkspaceOverview workspace={state.workspace} relationshipsClient={relationshipsClient} />
}

const organizationAreaDetails: Partial<Record<WorkspaceCapability, { title: string; description: string; release: string }>> = {
  people: { title: 'People', description: 'Employees and contacts scoped to this organization.', release: '0.1.5' },
  sites: { title: 'Sites', description: 'Sites and nested physical locations scoped to this organization.', release: '0.1.6' },
  custom_fields: { title: 'Custom fields', description: 'Versioned extensions scoped to this organization or inherited from the MSP.', release: '0.1.7' },
  documentation: { title: 'Documentation', description: 'Documentation owned by or explicitly referenced into this organization.', release: '0.2.2' },
  files: { title: 'Files', description: 'Files owned by or explicitly referenced into this organization.', release: '0.3.8' },
  assets: { title: 'Assets', description: 'Hardware and software assigned to this organization.', release: '0.3.5' },
  licenses: { title: 'Licenses', description: 'Software entitlements and assignments scoped to this organization.', release: '0.3.6' },
  networks: { title: 'Networks', description: 'Network records scoped to this organization.', release: '0.4.1' },
  domains: { title: 'Domains', description: 'Domain registration and DNS records scoped to this organization.', release: '0.7.8' },
  certificates: { title: 'Certificates', description: 'TLS endpoints and certificate evidence scoped to this organization.', release: '0.7.9' },
  credentials: { title: 'Credentials', description: 'Protected credential records scoped to this organization.', release: '0.3.1' },
  services: { title: 'Services', description: 'Services, providers, contracts, and dependencies scoped to this organization.', release: '0.3.7' },
  vendors: { title: 'Vendors', description: 'Suppliers related to this organization through products, assets, or services.', release: '0.3.4' },
  products: { title: 'Products', description: 'Supplier product and model templates owned by this organization.', release: '0.3.3' },
  tickets: { title: 'Tickets', description: 'Service requests associated with this organization.', release: 'Post-1.0' },
  recycle_bin: { title: 'Recycle bin', description: 'Archived records that can be recovered into this organization.', release: '0.1.13' },
}

function OrganizationAreaRoute({ state, area, peopleClient, sitesClient, customFieldsClient, relationshipsClient, recycleBinClient }: { state: OrganizationWorkspaceState | { phase: 'loading' }; area: WorkspaceCapability; peopleClient: PeopleClient; sitesClient: SitesClient; customFieldsClient: CustomFieldsClient; relationshipsClient: RelationshipsClient; recycleBinClient: RecycleBinClient }) {
  if (area === 'overview') return <OrganizationWorkspaceRoute state={state} relationshipsClient={relationshipsClient} />
  if (state.phase === 'loading' || state.phase === 'idle') return <section className="content-section" role="status">Loading organization workspace…</section>
  if (state.phase === 'error') return <OrganizationWorkspaceRoute state={state} relationshipsClient={relationshipsClient} />
  if (!state.workspace.capabilities.includes(area) || !organizationAreaDetails[area]) {
    return <section className="content-section workspace-error" role="alert"><h1>Area unavailable</h1><p>This area is not available for the selected organization.</p><Link className="secondary-button" to={organizationWorkspacePath(state.workspace, 'overview')}>Return to overview</Link></section>
  }
  if (area === 'people') return <People workspace={state.workspace} client={peopleClient} sitesClient={sitesClient} />
  if (area === 'sites') return <Sites workspace={state.workspace} client={sitesClient} customFieldsClient={customFieldsClient} />
  if (area === 'custom_fields') return <CustomFields workspace={state.workspace} client={customFieldsClient} />
  if (area === 'recycle_bin') return <RecycleBin workspace={state.workspace} client={recycleBinClient} />
  const details = organizationAreaDetails[area]
  return (
    <>
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link to={organizationWorkspacePath(state.workspace, 'overview')}>{state.workspace.name}</Link><span aria-hidden="true">/</span><span aria-current="page">{details.title}</span></nav>
      <PageHeader title={details.title} description={details.description} />
      <section className="content-section"><div className="section-heading"><h2>Planned for {details.release}</h2><span>{classificationSummary(state.workspace.classifications)} workspace</span></div><p className="workspace-area-note">The route and ownership context are established. The domain records arrive in their scheduled slice.</p></section>
    </>
  )
}

export function ApplicationShell({ authContext, authClient, accessControlClient, workspaceClient, peopleClient, sitesClient, customFieldsClient, relationshipsClient, recycleBinClient, onSignOut, signingOut = false, signOutError = null }: {
  authContext: AuthenticatedContext
  authClient: AuthClient
  accessControlClient: AccessControlClient
  workspaceClient: WorkspaceClient
  peopleClient: PeopleClient
  sitesClient: SitesClient
  customFieldsClient: CustomFieldsClient
  relationshipsClient: RelationshipsClient
  recycleBinClient: RecycleBinClient
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
          <ProfileMenu user={shellContext.user} canManageAccess={shellContext.permissions?.includes('memberships.assign_role') ?? false} onSignOut={onSignOut} signingOut={signingOut} />
        </header>
        <main className="main-content" key={location.pathname}>
          {signOutError && <div className="shell-alert" role="alert">{signOutError}</div>}
          <Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/documentation" element={<Documentation />} />
            <Route path="/people" element={<People workspace={null} client={peopleClient} sitesClient={sitesClient} />} />
            <Route path="/sites" element={<Sites workspace={null} client={sitesClient} customFieldsClient={customFieldsClient} />} />
            <Route path="/custom-fields" element={<CustomFields workspace={null} client={customFieldsClient} />} />
            <Route path="/recycle-bin" element={<RecycleBin workspace={null} client={recycleBinClient} />} />
            <Route path="/organizations" element={<Organizations />} />
            <Route path="/settings" element={<SecuritySettings client={authClient} context={shellContext} onProfileUpdated={setShellContext} />} />
            <Route path="/access-control" element={shellContext.permissions?.includes('memberships.assign_role') ? <AccessControl client={accessControlClient} /> : <Navigate to="/overview" replace />} />
            {Object.keys(plannedAreas).map((path) => <Route key={path} path={path} element={<PlannedPage path={path} />} />)}
            <Route path="/workspaces/organizations/:organizationId" element={<Navigate to="overview" replace />} />
            <Route path="/workspaces/organizations/:organizationId/overview" element={<OrganizationWorkspaceRoute state={visibleWorkspaceState} relationshipsClient={relationshipsClient} />} />
            {(Object.keys(organizationAreaDetails) as WorkspaceCapability[]).map((area) => <Route key={area} path={`/workspaces/organizations/:organizationId/${area}`} element={<OrganizationAreaRoute state={visibleWorkspaceState} area={area} peopleClient={peopleClient} sitesClient={sitesClient} customFieldsClient={customFieldsClient} relationshipsClient={relationshipsClient} recycleBinClient={recycleBinClient} />} />)}
            <Route path="/workspaces/organizations/:organizationId/*" element={<Navigate to={`/workspaces/organizations/${organizationId}/overview`} replace />} />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export function App({ initialPath, authClient = browserAuthClient, accessControlClient = browserAccessControlClient, workspaceClient = browserWorkspaceClient, peopleClient = browserPeopleClient, sitesClient = browserSitesClient, customFieldsClient = browserCustomFieldsClient, relationshipsClient = browserRelationshipsClient, recycleBinClient = browserRecycleBinClient, initialAuthContext }: {
  initialPath?: string
  authClient?: AuthClient
  accessControlClient?: AccessControlClient
  workspaceClient?: WorkspaceClient
  peopleClient?: PeopleClient
  sitesClient?: SitesClient
  customFieldsClient?: CustomFieldsClient
  relationshipsClient?: RelationshipsClient
  recycleBinClient?: RecycleBinClient
  initialAuthContext?: AuthenticatedContext
}) {
  const application = (
    <AuthGate client={authClient} initialContext={initialAuthContext}>
      {({ context, signOut, signingOut, signOutError }) => (
        <ApplicationShell
          authContext={context}
          authClient={authClient}
          accessControlClient={accessControlClient}
          workspaceClient={workspaceClient}
          peopleClient={peopleClient}
          sitesClient={sitesClient}
          customFieldsClient={customFieldsClient}
          relationshipsClient={relationshipsClient}
          recycleBinClient={recycleBinClient}
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
