import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router'
import { EntityRelationships } from '../relationships/EntityRelationships'
import type { RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from './api'
import { formatInstantDate, translate } from '../i18n/localization'
import { browserIntegrationsClient } from '../integrations/providerApi'
import type { HaloTicketSummary, IntegrationsClient } from '../integrations/providerApi'

const classificationLabels = {
  client: 'Client',
  vendor: 'Vendor',
  manufacturer: 'Manufacturer',
  partner: 'Partner',
}

export function WorkspaceOverview({ workspace, relationshipsClient, integrationsClient = browserIntegrationsClient }: { workspace: WorkspaceContext; relationshipsClient?: RelationshipsClient; integrationsClient?: IntegrationsClient }) {
  const organization = workspace.organization
  const showHaloTickets = workspace.kind === 'organization' && workspace.classifications.includes('client') && workspace.capabilities.includes('integrations')
  const [tickets, setTickets] = useState<HaloTicketSummary[] | null>(showHaloTickets ? null : [])
  const [ticketError, setTicketError] = useState(false)
  const [ticketRevision, setTicketRevision] = useState(0)

  useEffect(() => {
    if (!showHaloTickets) return
    const controller = new AbortController()
    integrationsClient.listHaloTickets(workspace, controller.signal)
      .then((results) => { if (!controller.signal.aborted) { setTickets(results); setTicketError(false) } })
      .catch(() => { if (!controller.signal.aborted) { setTickets([]); setTicketError(true) } })
    return () => controller.abort()
  }, [integrationsClient, showHaloTickets, ticketRevision, workspace])
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
      {showHaloTickets && <section className="content-section" aria-labelledby="halo-tickets-heading">
        <div className="section-heading"><div><h2 id="halo-tickets-heading">{translate('workspace.haloTickets')}</h2><p>{translate('workspace.haloTicketsHelp')}</p></div></div>
        {ticketError && <div role="alert"><p className="form-error">{translate('workspace.haloTicketsFailed')}</p><button className="secondary-button" type="button" onClick={() => { setTickets(null); setTicketRevision((value) => value + 1) }}>{translate('common.retry')}</button></div>}
        {!ticketError && (tickets === null ? <p role="status">{translate('workspace.haloTicketsLoading')}</p> : tickets.length === 0 ? <p className="empty-state">{translate('workspace.haloTicketsEmpty')}</p> : <ol className="plain-detail-list">{tickets.map((ticket) => <li key={ticket.id}><div><strong>#{ticket.number} {ticket.title}</strong><span>{[ticket.status, ticket.priority].filter(Boolean).join(' · ') || '—'} · {[ticket.assigned_team, ticket.assigned_agent].filter(Boolean).join(' · ') || translate('workspace.haloTicketUnassigned')}</span>{ticket.external_url && <a href={ticket.external_url} target="_blank" rel="noreferrer">{translate('workspace.openInHalo')}<ExternalLink size={13} aria-hidden="true" /></a>}</div><div><span>{ticket.stale ? translate('workspace.haloTicketStale', { date: ticket.source_last_synced_at ? formatInstantDate(ticket.source_last_synced_at) : translate('workspace.neverSynced') }) : translate('workspace.haloTicketUpdated', { date: formatInstantDate(ticket.source_updated_at) })}</span></div></li>)}</ol>)}
      </section>}
      <EntityRelationships organizationId={workspace.id} organizationName={workspace.name} client={relationshipsClient} />
    </>
  )
}
