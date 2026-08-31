import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router'
import { EntityRelationships } from '../relationships/EntityRelationships'
import type { RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from './api'
import { capabilityRegistry } from '../product/capabilities'

const classificationLabels = {
  client: 'Client',
  vendor: 'Vendor',
  manufacturer: 'Manufacturer',
  partner: 'Partner',
}

export function WorkspaceOverview({ workspace, relationshipsClient }: { workspace: WorkspaceContext; relationshipsClient?: RelationshipsClient }) {
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
      <EntityRelationships organizationId={workspace.id} organizationName={workspace.name} client={relationshipsClient} />
      <section className="content-section" aria-labelledby="workspace-areas-heading">
        <div className="section-heading"><div><h2 id="workspace-areas-heading">Workspace areas</h2><p>Records created in these areas belong to {workspace.name}.</p></div></div>
        <ul className="workspace-capability-list">
          {workspace.capabilities.filter((capability) => capability !== 'overview').map((capability) => <li key={capability}>{capabilityRegistry[capability].label}</li>)}
        </ul>
      </section>
    </>
  )
}
