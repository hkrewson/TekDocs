import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router'
import type { WorkspaceContext } from './api'

const classificationLabels = {
  client: 'Client',
  vendor: 'Vendor',
  manufacturer: 'Manufacturer',
  partner: 'Partner',
}

const capabilityLabels = {
  overview: 'Overview',
  documentation: 'Documentation',
  files: 'Files',
  organizations: 'Organizations',
  people: 'People',
  sites: 'Sites',
  assets: 'Assets',
  licenses: 'Licenses',
  networks: 'Networks',
  domains: 'Domains',
  certificates: 'Certificates',
  credentials: 'Credentials',
  services: 'Services',
  tickets: 'Tickets',
  vendors: 'Vendors',
  products: 'Products',
  compliance: 'Compliance',
  activity: 'Activity',
  integrations: 'Integrations',
  accounting: 'Accounting',
}

export function WorkspaceOverview({ workspace }: { workspace: WorkspaceContext }) {
  const organization = workspace.organization
  return (
    <>
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/organizations">Organizations</Link><span aria-hidden="true">/</span><span aria-current="page">{workspace.name}</span>
      </nav>
      <header className="page-header workspace-page-header">
        <div>
          <h1>{workspace.name}</h1>
          <p>{workspace.classifications.map((classification) => classificationLabels[classification]).join(' · ')} workspace</p>
        </div>
        <Link className="secondary-button workspace-return" to="/organizations">Return to MSP organizations</Link>
      </header>
      <section className="content-section" aria-labelledby="organization-profile-heading">
        <div className="section-heading"><h2 id="organization-profile-heading">Organization profile</h2></div>
        <dl className="organization-profile">
          <div><dt>Display name</dt><dd>{workspace.name}</dd></div>
          <div><dt>Legal name</dt><dd>{organization?.legal_name || 'Not provided'}</dd></div>
          <div><dt>Classifications</dt><dd>{workspace.classifications.map((classification) => classificationLabels[classification]).join(', ')}</dd></div>
          <div><dt>Website</dt><dd>{organization?.website ? <a href={organization.website} target="_blank" rel="noreferrer">{organization.website}<ExternalLink size={13} aria-hidden="true" /></a> : 'Not provided'}</dd></div>
        </dl>
      </section>
      <section className="content-section" aria-labelledby="workspace-areas-heading">
        <div className="section-heading"><div><h2 id="workspace-areas-heading">Workspace areas</h2><p>Records created in these areas will belong to {workspace.name}. Individual data modules arrive in their scheduled milestones.</p></div></div>
        <ul className="workspace-capability-list">
          {workspace.capabilities.filter((capability) => capability !== 'overview').map((capability) => <li key={capability}>{capabilityLabels[capability]}</li>)}
        </ul>
      </section>
    </>
  )
}
