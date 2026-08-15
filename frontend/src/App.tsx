import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Link, MemoryRouter, Navigate, NavLink, Route, Routes, useLocation, useMatch, useNavigate } from 'react-router'
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
  UserPlus,
  ScrollText,
  TicketCheck,
  Trash2,
  UsersRound,
  X,
} from 'lucide-react'
import { ContextualHelp } from './help/ContextualHelp'
import { translate } from './i18n/localization'
import { AuthGate } from './auth/AuthGate'
import { browserAccessControlClient } from './access-control/api'
import type { AccessControlClient } from './access-control/api'
import { browserAuthClient } from './auth/api'
import type { AuthClient, AuthenticatedContext } from './auth/api'
import { browserCatalogClient } from './catalog/api'
import type { CatalogClient } from './catalog/api'
import { browserComplianceClient } from './compliance/api'
import type { ComplianceClient } from './compliance/api'
import { browserCustomFieldsClient } from './custom-fields/api'
import type { CustomFieldsClient } from './custom-fields/api'
import { browserCredentialReferencesClient } from './credential-references/api'
import type { CredentialReferencesClient } from './credential-references/api'
import { browserDocumentsClient } from './documentation/api'
import type { DocumentsClient } from './documentation/api'
import { browserDomainsClient } from './domains/api'
import type { DomainsClient } from './domains/api'
import { browserInventoryClient } from './inventory/api'
import { browserCommercialClient } from './commercial/api'
import type { InventoryClient } from './inventory/api'
import { browserWebhooksClient } from './integrations/api'
import type { WebhooksClient } from './integrations/api'
import type { NetworksClient } from './networks/api'
import { browserStaffAdministrationClient } from './staff/api'
import type { StaffAdministrationClient } from './staff/api'
import { browserNotificationDeliveryAdminClient, browserNotificationsClient } from './notifications/api'
import type { NotificationsClient, NotificationTarget } from './notifications/api'
import { NotificationInbox } from './notifications/NotificationInbox'
import { browserPeopleClient } from './people/api'
import type { PeopleClient } from './people/api'
import { browserRelationshipsClient } from './relationships/api'
import type { RelationshipsClient } from './relationships/api'
import { browserRecycleBinClient } from './recycle-bin/api'
import type { RecycleBinClient } from './recycle-bin/api'
import { browserSitesClient } from './sites/api'
import type { SitesClient } from './sites/api'
import { browserWorkspaceClient } from './workspaces/api'
import type { WorkspaceCapability, WorkspaceClient, WorkspaceContext } from './workspaces/api'
import { classificationSummary, organizationWorkspacePath, workspaceAreaFromPath } from './workspaces/navigation'
import type { WorkspaceArea } from './workspaces/navigation'
import { WorkspaceOverview } from './workspaces/WorkspaceOverview'
import { WorkspaceSwitcher } from './workspaces/WorkspaceSwitcher'

const Assets = lazy(async () => ({ default: (await import('./inventory/Assets')).Assets }))
const AccessControl = lazy(async () => ({ default: (await import('./access-control/AccessControl')).AccessControl }))
const ClientPortal = lazy(async () => ({ default: (await import('./portal/ClientPortal')).ClientPortal }))
const CredentialReferences = lazy(async () => ({ default: (await import('./credential-references/CredentialReferences')).CredentialReferences }))
const CustomFields = lazy(async () => ({ default: (await import('./custom-fields/CustomFields')).CustomFields }))
const Documentation = lazy(async () => ({ default: (await import('./documentation/Documentation')).Documentation }))
const NotificationDeliveryAdmin = lazy(async () => ({ default: (await import('./notifications/NotificationDeliveryAdmin')).NotificationDeliveryAdmin }))
const Organizations = lazy(async () => ({ default: (await import('./organizations/Organizations')).Organizations }))
const People = lazy(async () => ({ default: (await import('./people/People')).People }))
const Products = lazy(async () => ({ default: (await import('./catalog/Products')).Products }))
const RecycleBin = lazy(async () => ({ default: (await import('./recycle-bin/RecycleBin')).RecycleBin }))
const SecuritySettings = lazy(async () => ({ default: (await import('./auth/SecuritySettings')).SecuritySettings }))
const StaffAdministration = lazy(async () => ({ default: (await import('./staff/StaffAdministration')).StaffAdministration }))
const Sites = lazy(async () => ({ default: (await import('./sites/Sites')).Sites }))
const Licenses = lazy(async () => ({ default: (await import('./inventory/Licenses')).Licenses }))
const Contracts = lazy(async () => ({ default: (await import('./commercial/Contracts')).Contracts }))
const Vendors = lazy(async () => ({ default: (await import('./inventory/Vendors')).Vendors }))
const Networks = lazy(async () => ({ default: (await import('./networks/Networks')).Networks }))
const Integrations = lazy(async () => ({ default: (await import('./integrations/Integrations')).Integrations }))
const Compliance = lazy(async () => ({ default: (await import('./compliance/Compliance')).Compliance }))
const Domains = lazy(async () => ({ default: (await import('./domains/Domains')).Domains }))

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

function ProfileMenu({ user, canManageAccess, canManageStaff, canManageNotifications, onSignOut, signingOut }: {
  user: AuthenticatedContext['user']
  canManageAccess: boolean
  canManageStaff: boolean
  canManageNotifications: boolean
  onSignOut: () => Promise<void>
  signingOut: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  return (
    <div className="profile-menu" ref={ref}>
      <button ref={triggerRef} className="profile-trigger" onClick={() => setOpen((value) => !value)} aria-haspopup="menu" aria-expanded={open} aria-label={`Account menu for ${user.display_name}`}>
        <CircleUserRound size={22} />
        <span className="profile-copy"><strong>{user.display_name}</strong><span>{user.email}</span></span>
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="profile-popover" role="menu">
          <AppLink to="/settings" role="menuitem" onClick={() => setOpen(false)}><Settings size={17} />Settings</AppLink>
          {canManageStaff && <AppLink to="/staff" role="menuitem" onClick={() => setOpen(false)}><UserPlus size={17} />Staff &amp; invitations</AppLink>}
          {canManageAccess && <AppLink to="/access-control" role="menuitem" onClick={() => setOpen(false)}><ShieldCheck size={17} />Access control</AppLink>}
          {canManageNotifications && <AppLink to="/notification-delivery" role="menuitem" onClick={() => setOpen(false)}><Activity size={17} />Email delivery</AppLink>}
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
  '/networks': { title: 'Networks', description: 'Simple location-owned networks with VLAN, CIDR, range, gateway, and DNS.', release: '0.5.10', capabilities: ['Network records', 'Calculated gateway and ranges', 'Workspace isolation'] },
  '/domains': { title: 'Domains', description: 'Domain registration, DNS ownership, and expiration monitoring.', release: '0.7.8', capabilities: ['Registration records', 'DNS monitoring', 'Expiry notifications'] },
  '/certificates': { title: 'Certificates', description: 'TLS endpoints, certificate chains, and expiry monitoring.', release: '0.7.9', capabilities: ['Endpoint inventory', 'Chain evidence', 'Expiry notifications'] },
  '/services': { title: 'Services', description: 'Services, contracts, providers, and operational dependencies.', release: '0.3.7', capabilities: ['Service inventory', 'Provider relationships', 'Renewal tracking'] },
  '/vendors': { title: 'Vendors', description: 'Organizations supplying products or services to this workspace.', release: '0.3.4', capabilities: ['Relationship-derived list', 'Supplier provenance', 'Related contacts'] },
  '/products': { title: 'Products', description: 'Reusable supplier product and model definitions.', release: '0.3.3', capabilities: ['Product templates', 'Model specifications', 'Client asset provenance'] },
  '/tickets': { title: 'Tickets', description: 'Service requests associated with the active workspace.', release: 'Post-1.0', capabilities: ['Client requests', 'Object relationships', 'Portal visibility'] },
  '/accounting': { title: 'Accounting', description: 'MSP business records for billing, purchasing, and financial operations.', release: 'Post-1.0', capabilities: ['Invoices and payments', 'Quotes and recurring billing', 'Expenses and trips'] },
  '/compliance': { title: 'Compliance', description: 'Versioned frameworks and immutable control catalogs.', release: '0.7.1', capabilities: ['Stable framework identities', 'Versioned controls', 'Immutable catalog snapshots'] },
  '/activity': { title: 'Activity', description: 'Append-only security and business change history.', release: '0.1.0', capabilities: ['Request correlation', 'Permission-aware history', 'Exportable evidence'] },
  '/integrations': { title: 'Integrations', description: 'Secure provider connections, jobs, webhooks, and reconciliation.', release: '0.7.0', capabilities: ['Provider contracts', 'Scheduled jobs', 'Conflict review'] },
}

function PlannedPage({ path }: { path: string }) {
  const area = plannedAreas[path]
  if (path === '/products') {
    return <>
      <PageHeader title="Products" description="Reusable supplier product and model definitions." />
      <section className="content-section"><div className="section-heading"><div><h2>Supplier catalogs are available</h2><p>Open a vendor or manufacturer to manage its templates and product publications. Open a client to create assets from those exact supplier models.</p></div><span>0.3.4</span></div><Link className="secondary-button" to="/organizations">Browse organizations</Link></section>
    </>
  }
  return (
    <>
      <PageHeader title={area.title} description={area.description} />
      <section className="content-section">
        <div className="section-heading"><h2>Planned {area.release}</h2><span>Foundation</span></div>
        <ul className="capability-list">{area.capabilities.map((capability) => <li key={capability}>{capability}</li>)}</ul>
      </section>
    </>
  )
}

function Overview() {
  return (
    <>
      <PageHeader title="Overview" description="TekDocs 0.8.14" />
      <section className="content-section">
        <div className="section-heading"><h2>Foundation status</h2><span>0.8.14</span></div>
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
            ['Controlled publication decisions', 'Available'],
            ['Client portal identity boundary', 'Available'],
            ['Read-only client publication portal', 'Available'],
            ['Permission-filtered notification inbox', 'Available'],
            ['Retryable SMTP notifications', 'Available'],
            ['1Password credential references', 'Available'],
            ['Supplier product and model catalogs', 'Available'],
            ['Client asset catalog provenance', 'Available'],
            ['Software installations and licensing', 'Available'],
            ['MSP-owned operational inventory', 'Available'],
            ['Derived client vendors', 'Available'],
            ['Racks and network-device placement', 'Available'],
          ].map(([name, status]) => <div className="status-row" role="row" key={name}><span role="cell">{name}</span><span role="cell">{status}</span></div>)}
        </div>
      </section>
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
  documentation: { title: 'Documentation', description: 'Documentation owned by or explicitly referenced into this organization.', release: '0.2.8' },
  files: { title: 'Files', description: 'Files owned by or explicitly referenced into this organization.', release: '0.3.8' },
  assets: { title: 'Assets', description: 'Hardware lifecycle and software records created from retained supplier provenance.', release: '0.3.5' },
  licenses: { title: 'Licenses', description: 'Software entitlements and assignments scoped to this organization.', release: '0.3.6' },
  networks: { title: 'Networks', description: 'Simple location-owned network records; physical devices and MAC addresses belong to Assets.', release: '0.5.10' },
  domains: { title: 'Domains', description: 'Domain registration and DNS records scoped to this organization.', release: '0.7.8' },
  certificates: { title: 'Certificates', description: 'TLS endpoints and certificate evidence scoped to this organization.', release: '0.7.9' },
  credentials: { title: 'Credential references', description: 'Links to externally protected credentials; TekDocs does not store or reveal their values.', release: '0.3.1' },
  services: { title: 'Services', description: 'Services, providers, contracts, and dependencies scoped to this organization.', release: '0.3.7' },
  vendors: { title: 'Vendors', description: 'Suppliers related to this organization through products, assets, or services.', release: '0.3.4' },
  products: { title: 'Products', description: 'Supplier product and model templates owned by this organization.', release: '0.3.3' },
  tickets: { title: 'Tickets', description: 'Service requests associated with this organization.', release: 'Post-1.0' },
  recycle_bin: { title: 'Recycle bin', description: 'Archived records that can be recovered into this organization.', release: '0.1.13' },
  integrations: { title: 'Integrations', description: 'Signed webhooks and provider connections scoped to this organization.', release: '0.6.3' },
  compliance: { title: 'Compliance', description: 'Versioned control catalogs scoped to this organization.', release: '0.7.1' },
}

function OrganizationAreaRoute({ state, area, peopleClient, sitesClient, customFieldsClient, relationshipsClient, recycleBinClient, documentsClient, workspaceClient, credentialReferencesClient, catalogClient, inventoryClient, webhooksClient, complianceClient, domainsClient, networksClient }: { state: OrganizationWorkspaceState | { phase: 'loading' }; area: WorkspaceCapability; peopleClient: PeopleClient; sitesClient: SitesClient; customFieldsClient: CustomFieldsClient; relationshipsClient: RelationshipsClient; recycleBinClient: RecycleBinClient; documentsClient: DocumentsClient; workspaceClient: WorkspaceClient; credentialReferencesClient: CredentialReferencesClient; catalogClient: CatalogClient; inventoryClient: InventoryClient; webhooksClient: WebhooksClient; complianceClient: ComplianceClient; domainsClient: DomainsClient; networksClient?: NetworksClient }) {
  if (area === 'overview') return <OrganizationWorkspaceRoute state={state} relationshipsClient={relationshipsClient} />
  if (state.phase === 'loading' || state.phase === 'idle') return <section className="content-section" role="status">Loading organization workspace…</section>
  if (state.phase === 'error') return <OrganizationWorkspaceRoute state={state} relationshipsClient={relationshipsClient} />
  if (!state.workspace.capabilities.includes(area) || !organizationAreaDetails[area]) {
    return <section className="content-section workspace-error" role="alert"><h1>Area unavailable</h1><p>This area is not available for the selected organization.</p><Link className="secondary-button" to={organizationWorkspacePath(state.workspace, 'overview')}>Return to overview</Link></section>
  }
  if (area === 'people') return <People workspace={state.workspace} client={peopleClient} sitesClient={sitesClient} />
  if (area === 'sites') return <Sites workspace={state.workspace} client={sitesClient} customFieldsClient={customFieldsClient} />
  if (area === 'custom_fields') return <CustomFields workspace={state.workspace} client={customFieldsClient} />
  if (area === 'documentation') return <Suspense fallback={<section className="content-section" role="status">Loading documentation…</section>}><Documentation workspace={state.workspace} client={documentsClient} workspaceClient={workspaceClient} relationshipsClient={relationshipsClient} /></Suspense>
  if (area === 'credentials') return <CredentialReferences workspace={state.workspace} client={credentialReferencesClient} />
  if (area === 'products') return <Products workspace={state.workspace} client={catalogClient} />
  if (area === 'assets') return <Suspense fallback={<section className="content-section" role="status">Loading assets…</section>}><Assets workspace={state.workspace} client={inventoryClient} /></Suspense>
  if (area === 'licenses') return <Suspense fallback={<section className="content-section" role="status">Loading licenses…</section>}><Licenses workspace={state.workspace} client={inventoryClient} /></Suspense>
  if (area === 'services') return <Suspense fallback={<section className="content-section" role="status">Loading contracts…</section>}><Contracts key={state.workspace.id} workspace={state.workspace} client={browserCommercialClient} /></Suspense>
  if (area === 'vendors') return <Suspense fallback={<section className="content-section" role="status">Loading vendors…</section>}><Vendors workspace={state.workspace} client={inventoryClient} /></Suspense>
  if (area === 'networks') return <Suspense fallback={<section className="content-section" role="status">Loading networks…</section>}><Networks workspace={state.workspace} client={networksClient} relationshipsClient={relationshipsClient} /></Suspense>
  if (area === 'integrations') return <Suspense fallback={<section className="content-section" role="status">Loading integrations…</section>}><Integrations workspace={state.workspace} client={webhooksClient} documentsClient={documentsClient} /></Suspense>
  if (area === 'compliance') return <Suspense fallback={<section className="content-section" role="status">Loading compliance…</section>}><Compliance workspace={state.workspace} client={complianceClient} /></Suspense>
  if (area === 'domains') return <Suspense fallback={<section className="content-section" role="status">Loading domains…</section>}><Domains workspace={state.workspace} client={domainsClient} /></Suspense>
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

export function ApplicationShell({ authContext, authClient, accessControlClient, staffAdministrationClient, workspaceClient, peopleClient, sitesClient, customFieldsClient, relationshipsClient, recycleBinClient, documentsClient, credentialReferencesClient = browserCredentialReferencesClient, catalogClient = browserCatalogClient, inventoryClient = browserInventoryClient, notificationsClient = browserNotificationsClient, webhooksClient = browserWebhooksClient, complianceClient = browserComplianceClient, domainsClient = browserDomainsClient, networksClient, onSignOut, signingOut = false, signOutError = null }: {
  authContext: AuthenticatedContext
  authClient: AuthClient
  accessControlClient: AccessControlClient
  staffAdministrationClient: StaffAdministrationClient
  workspaceClient: WorkspaceClient
  peopleClient: PeopleClient
  sitesClient: SitesClient
  customFieldsClient: CustomFieldsClient
  relationshipsClient: RelationshipsClient
  recycleBinClient: RecycleBinClient
  documentsClient: DocumentsClient
  credentialReferencesClient?: CredentialReferencesClient
  catalogClient?: CatalogClient
  inventoryClient?: InventoryClient
  notificationsClient?: NotificationsClient
  webhooksClient?: WebhooksClient
  complianceClient?: ComplianceClient
  domainsClient?: DomainsClient
  networksClient?: NetworksClient
  onSignOut: () => Promise<void>
  signingOut?: boolean
  signOutError?: string | null
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [shellContext, setShellContext] = useState(authContext)
  const [organizationWorkspace, setOrganizationWorkspace] = useState<OrganizationWorkspaceState>({ phase: 'idle' })
  const location = useLocation()
  const navigate = useNavigate()
  const mainRef = useRef<HTMLElement>(null)
  const previousPathname = useRef(location.pathname)
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
  const mspWorkspace = useMemo<WorkspaceContext>(() => ({
    kind: 'msp', id: shellContext.tenant.id, name: shellContext.tenant.name,
    classifications: [], capabilities: [], organization: null,
  }), [shellContext.tenant.id, shellContext.tenant.name])
  const activeArea = workspaceAreaFromPath(location.pathname)

  function openNotificationTarget(target: NotificationTarget) {
    if (!target.organization_id) return
    const area = target.kind === 'organization_documentation' ? 'documentation' : 'overview'
    void navigate(`/workspaces/organizations/${target.organization_id}/${area}`)
  }

  useEffect(() => {
    const areaLabel = activeArea.charAt(0).toUpperCase() + activeArea.slice(1)
    document.title = `${selectedWorkspace?.name ?? shellContext.tenant.name} · ${areaLabel} · TekDocs`
  }, [activeArea, selectedWorkspace?.name, shellContext.tenant.name])

  useEffect(() => {
    if (previousPathname.current !== location.pathname) {
      mainRef.current?.focus({ preventScroll: true })
      previousPathname.current = location.pathname
    }
  }, [location.pathname])

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">{translate('shell.skip')}</a>
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCollapse={() => setCollapsed((value) => !value)} onMobileClose={() => setMobileOpen(false)} tenant={shellContext.tenant} workspace={selectedWorkspace} activeArea={activeArea} workspaceClient={workspaceClient} workspaceLoading={Boolean(organizationId) && visibleWorkspaceState.phase === 'loading'} organizationRoute={Boolean(organizationId)} />
      <div className={`app-body${collapsed ? ' sidebar-collapsed' : ''}`}>
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <label className="search-field"><Search size={17} /><span className="sr-only">Search TekDocs</span><input placeholder="Search TekDocs" disabled /></label>
          <ContextualHelp key={location.pathname} pathname={location.pathname} />
          <NotificationInbox client={notificationsClient} onOpen={openNotificationTarget} />
          <ProfileMenu user={shellContext.user} canManageAccess={shellContext.permissions?.includes('memberships.assign_role') ?? false} canManageStaff={shellContext.permissions?.includes('staff_invitations.view') ?? false} canManageNotifications={shellContext.permissions?.includes('notifications.manage') ?? false} onSignOut={onSignOut} signingOut={signingOut} />
        </header>
        <main id="main-content" ref={mainRef} className="main-content" key={location.pathname} tabIndex={-1}>
          {signOutError && <div className="shell-alert" role="alert">{signOutError}</div>}
          <Suspense fallback={<section className="content-section" role="status"><h1>Loading workspace</h1><p>Please wait…</p></section>}><Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/documentation" element={<Suspense fallback={<section className="content-section" role="status">Loading documentation…</section>}><Documentation workspace={null} client={documentsClient} workspaceClient={workspaceClient} relationshipsClient={relationshipsClient} /></Suspense>} />
            <Route path="/credentials" element={<CredentialReferences workspace={null} client={credentialReferencesClient} />} />
            <Route path="/people" element={<People workspace={null} client={peopleClient} sitesClient={sitesClient} />} />
            <Route path="/sites" element={<Sites workspace={null} client={sitesClient} customFieldsClient={customFieldsClient} />} />
            <Route path="/custom-fields" element={<CustomFields workspace={null} client={customFieldsClient} />} />
            <Route path="/recycle-bin" element={<RecycleBin workspace={null} client={recycleBinClient} />} />
            <Route path="/organizations" element={<Organizations />} />
            <Route path="/settings" element={<SecuritySettings client={authClient} context={shellContext} onProfileUpdated={setShellContext} />} />
            <Route path="/staff" element={shellContext.permissions?.includes('staff_invitations.view') ? <Suspense fallback={<section className="content-section" role="status">Loading staff administration…</section>}><StaffAdministration client={staffAdministrationClient} /></Suspense> : <Navigate to="/overview" replace />} />
            <Route path="/access-control" element={shellContext.permissions?.includes('memberships.assign_role') ? <Suspense fallback={<section className="content-section" role="status">Loading access control…</section>}><AccessControl client={accessControlClient} /></Suspense> : <Navigate to="/overview" replace />} />
            <Route path="/notification-delivery" element={shellContext.permissions?.includes('notifications.manage') ? <NotificationDeliveryAdmin client={browserNotificationDeliveryAdminClient} /> : <Navigate to="/overview" replace />} />
            <Route path="/assets" element={<Suspense fallback={<section className="content-section" role="status">Loading assets…</section>}><Assets workspace={mspWorkspace} client={inventoryClient} /></Suspense>} />
            <Route path="/licenses" element={<Suspense fallback={<section className="content-section" role="status">Loading licenses…</section>}><Licenses workspace={mspWorkspace} client={inventoryClient} /></Suspense>} />
            <Route path="/services" element={<Suspense fallback={<section className="content-section" role="status">Loading contracts…</section>}><Contracts workspace={mspWorkspace} client={browserCommercialClient} /></Suspense>} />
            <Route path="/vendors" element={<Suspense fallback={<section className="content-section" role="status">Loading vendors…</section>}><Vendors workspace={mspWorkspace} client={inventoryClient} /></Suspense>} />
            <Route path="/networks" element={<Suspense fallback={<section className="content-section" role="status">Loading networks…</section>}><Networks workspace={mspWorkspace} client={networksClient} relationshipsClient={relationshipsClient} /></Suspense>} />
            <Route path="/integrations" element={<Suspense fallback={<section className="content-section" role="status">Loading integrations…</section>}><Integrations workspace={mspWorkspace} client={webhooksClient} documentsClient={documentsClient} /></Suspense>} />
            <Route path="/compliance" element={<Suspense fallback={<section className="content-section" role="status">Loading compliance…</section>}><Compliance workspace={null} client={complianceClient} /></Suspense>} />
            {Object.keys(plannedAreas).filter((path) => !['/assets', '/licenses', '/services', '/vendors', '/networks', '/integrations', '/compliance', '/domains'].includes(path)).map((path) => <Route key={path} path={path} element={<PlannedPage path={path} />} />)}
            <Route path="/domains" element={<Suspense fallback={<section className="content-section" role="status">Loading domains…</section>}><Domains workspace={null} client={domainsClient} /></Suspense>} />
            <Route path="/workspaces/organizations/:organizationId" element={<Navigate to="overview" replace />} />
            <Route path="/workspaces/organizations/:organizationId/overview" element={<OrganizationWorkspaceRoute state={visibleWorkspaceState} relationshipsClient={relationshipsClient} />} />
            {(Object.keys(organizationAreaDetails) as WorkspaceCapability[]).map((area) => <Route key={area} path={`/workspaces/organizations/:organizationId/${area}`} element={<OrganizationAreaRoute state={visibleWorkspaceState} area={area} peopleClient={peopleClient} sitesClient={sitesClient} customFieldsClient={customFieldsClient} relationshipsClient={relationshipsClient} recycleBinClient={recycleBinClient} documentsClient={documentsClient} workspaceClient={workspaceClient} credentialReferencesClient={credentialReferencesClient} catalogClient={catalogClient} inventoryClient={inventoryClient} webhooksClient={webhooksClient} complianceClient={complianceClient} domainsClient={domainsClient} networksClient={networksClient} />} />)}
            <Route path="/workspaces/organizations/:organizationId/*" element={<Navigate to={`/workspaces/organizations/${organizationId}/overview`} replace />} />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes></Suspense>
        </main>
      </div>
    </div>
  )
}

export function App({ initialPath, authClient = browserAuthClient, accessControlClient = browserAccessControlClient, staffAdministrationClient = browserStaffAdministrationClient, workspaceClient = browserWorkspaceClient, peopleClient = browserPeopleClient, sitesClient = browserSitesClient, customFieldsClient = browserCustomFieldsClient, relationshipsClient = browserRelationshipsClient, recycleBinClient = browserRecycleBinClient, documentsClient = browserDocumentsClient, credentialReferencesClient = browserCredentialReferencesClient, catalogClient = browserCatalogClient, inventoryClient = browserInventoryClient, notificationsClient = browserNotificationsClient, webhooksClient = browserWebhooksClient, complianceClient = browserComplianceClient, domainsClient = browserDomainsClient, networksClient, initialAuthContext }: {
  initialPath?: string
  authClient?: AuthClient
  accessControlClient?: AccessControlClient
  staffAdministrationClient?: StaffAdministrationClient
  workspaceClient?: WorkspaceClient
  peopleClient?: PeopleClient
  sitesClient?: SitesClient
  customFieldsClient?: CustomFieldsClient
  relationshipsClient?: RelationshipsClient
  recycleBinClient?: RecycleBinClient
  documentsClient?: DocumentsClient
  credentialReferencesClient?: CredentialReferencesClient
  catalogClient?: CatalogClient
  inventoryClient?: InventoryClient
  notificationsClient?: NotificationsClient
  webhooksClient?: WebhooksClient
  complianceClient?: ComplianceClient
  domainsClient?: DomainsClient
  networksClient?: NetworksClient
  initialAuthContext?: AuthenticatedContext
}) {
  const application = (
    <AuthGate client={authClient} initialContext={initialAuthContext}>
      {({ context, signOut, signingOut, signOutError }) => (
        context.surface === 'client_portal' ? <Suspense fallback={<section className="content-section" role="status">Loading client portal…</section>}><ClientPortal
          context={context}
          onSignOut={signOut}
          signingOut={signingOut}
          signOutError={signOutError}
        /></Suspense> : <ApplicationShell
          authContext={context}
          authClient={authClient}
          accessControlClient={accessControlClient}
          staffAdministrationClient={staffAdministrationClient}
          workspaceClient={workspaceClient}
          peopleClient={peopleClient}
          sitesClient={sitesClient}
          customFieldsClient={customFieldsClient}
          relationshipsClient={relationshipsClient}
          recycleBinClient={recycleBinClient}
          documentsClient={documentsClient}
          credentialReferencesClient={credentialReferencesClient}
          catalogClient={catalogClient}
          inventoryClient={inventoryClient}
          notificationsClient={notificationsClient}
          webhooksClient={webhooksClient}
          complianceClient={complianceClient}
          domainsClient={domainsClient}
          networksClient={networksClient}
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
