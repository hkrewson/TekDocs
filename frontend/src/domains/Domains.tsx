import { RefreshCw, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'

import type { WorkspaceContext } from '../workspaces/api'
import type { DomainDraft, DomainMonitoring, DomainsClient, RegisteredDomain } from './api'

const EMPTY: DomainDraft = {
  name: '', registrar_id: null, registration_date: null, expiration_date: null,
  renewal_mode: 'manual', owner_id: null, status: 'active', notes: '',
}

export function Domains({ workspace, client }: { workspace: WorkspaceContext | null; client: DomainsClient }) {
  const [domains, setDomains] = useState<RegisteredDomain[]>([])
  const [draft, setDraft] = useState<DomainDraft>(EMPTY)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [monitoring, setMonitoring] = useState<DomainMonitoring | null>(null)
  const [monitoringId, setMonitoringId] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void client.list(workspace, controller.signal).then((records) => {
      setDomains(records)
      setError(null)
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Domains could not be loaded.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [client, workspace])

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const created = await client.create(workspace, draft)
      setDomains((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)))
      setDraft(EMPTY)
      setOpen(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The domain could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  async function openMonitoring(domain: RegisteredDomain) {
    setMonitoringId(domain.id)
    setMonitoring(null)
    setError(null)
    try {
      setMonitoring(await client.monitoring(workspace, domain.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Monitoring history could not be loaded.')
    }
  }

  async function scan(domainId: string) {
    setChecking(true)
    setError(null)
    try {
      await client.scan(workspace, domainId)
      setDomains((current) => current.map((domain) => domain.id === domainId ? { ...domain, monitor_state: 'queued' } : domain))
      setMonitoring(await client.monitoring(workspace, domainId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The monitoring check could not be queued.')
    } finally {
      setChecking(false)
    }
  }

  return <>
    <header className="page-header"><div><h1>Domains</h1><p>Registration ownership, renewal dates, and responsible staff for this workspace.</p></div><button type="button" className="primary-button" onClick={() => setOpen(true)}><Plus size={16} /> Add domain</button></header>
    {error && <p role="alert" className="form-error">{error}</p>}
    {open && <section className="content-section" aria-labelledby="domain-form-title">
      <div className="section-heading"><div><h2 id="domain-form-title">New registered domain</h2><p>Enter the known registration details. Monitoring keeps entered values separate from observed evidence.</p></div></div>
      <div className="compliance-risk-form">
        <label><span>Domain name</span><input autoFocus value={draft.name} placeholder="example.com" onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label><span>Status</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as DomainDraft['status'] })}><option value="active">Active</option><option value="pending">Pending</option><option value="expired">Expired</option><option value="transferred">Transferred</option></select></label>
        <label><span>Registered on</span><input type="date" value={draft.registration_date ?? ''} onChange={(event) => setDraft({ ...draft, registration_date: event.target.value || null })} /></label>
        <label><span>Expires on</span><input type="date" value={draft.expiration_date ?? ''} onChange={(event) => setDraft({ ...draft, expiration_date: event.target.value || null })} /></label>
        <label><span>Renewal</span><select value={draft.renewal_mode} onChange={(event) => setDraft({ ...draft, renewal_mode: event.target.value as DomainDraft['renewal_mode'] })}><option value="manual">Manual</option><option value="auto">Automatic</option><option value="external">Managed externally</option></select></label>
        <label className="wide-field"><span>Notes (Markdown)</span><textarea rows={3} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} /></label>
        <div className="form-actions wide-field"><button type="button" className="primary-button" disabled={saving || !draft.name.trim()} onClick={() => { void save() }}>{saving ? 'Saving…' : 'Save domain'}</button><button type="button" className="secondary-button" onClick={() => setOpen(false)}>Cancel</button></div>
      </div>
    </section>}
    <section className="content-section" aria-labelledby="domain-list-title">
      <div className="section-heading"><div><h2 id="domain-list-title">Registered domains</h2><p>Only domains owned by the active MSP or organization workspace appear here.</p></div><span>{domains.length}</span></div>
      {loading ? <p role="status">Loading domains…</p> : domains.length === 0 ? <p className="empty-state">No registered domains are recorded in this workspace.</p> : <div className="network-table-wrap"><table className="network-table"><thead><tr><th>Domain</th><th>Status</th><th>Renewal</th><th>Expiration</th><th>Monitoring</th><th>Owner</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{domains.map((domain) => <tr key={domain.id}><td><strong>{domain.name}</strong><small>{domain.registrar ?? 'Registrar not recorded'}</small></td><td>{domain.status}</td><td>{domain.renewal_mode}</td><td>{domain.expiration_date ?? 'Not recorded'}</td><td>{domain.monitor_state}<small>{domain.last_monitor_at ? `Last checked ${new Date(domain.last_monitor_at).toLocaleString()}` : 'Not checked yet'}</small></td><td>{domain.owner ?? 'Unassigned'}</td><td><button type="button" className="secondary-button" onClick={() => { void openMonitoring(domain) }}>Details</button></td></tr>)}</tbody></table></div>}
    </section>
    {monitoringId && <section className="content-section" aria-labelledby="domain-monitoring-title">
      <div className="section-heading"><div><h2 id="domain-monitoring-title">Monitoring details</h2><p>RDAP and DNS observations retain their source and never overwrite entered registration data.</p></div><button type="button" className="secondary-button" disabled={checking} onClick={() => { void scan(monitoringId) }}><RefreshCw size={16} /> {checking ? 'Queuing…' : 'Check now'}</button></div>
      {!monitoring ? <p role="status">Loading monitoring history…</p> : <>
        <dl className="domain-monitor-summary"><div><dt>Domain</dt><dd>{monitoring.domain.name}</dd></div><div><dt>Review</dt><dd>{monitoring.domain.review_state}</dd></div><div><dt>Next check</dt><dd>{new Date(monitoring.domain.next_monitor_at).toLocaleString()}</dd></div></dl>
        <h3>Recent notifications</h3>
        {monitoring.alerts.length === 0 ? <p className="empty-state">No monitoring notifications have been generated.</p> : <ul className="domain-monitor-alerts">{monitoring.alerts.map((alert) => <li key={alert.id}><strong>{alert.kind.replaceAll('_', ' ')}</strong><span>{new Date(alert.created_at).toLocaleString()}</span></li>)}</ul>}
        <h3>Collection history</h3>
        {monitoring.runs.length === 0 ? <p className="empty-state">No monitoring checks have run.</p> : <div className="network-table-wrap"><table className="network-table"><thead><tr><th>Requested</th><th>State</th><th>RDAP</th><th>Observed expiration</th><th>DNS</th><th>DNSSEC</th></tr></thead><tbody>{monitoring.runs.map((run) => <tr key={run.id}><td>{new Date(run.created_at).toLocaleString()}</td><td>{run.state}{run.error_code && <small>{run.error_code}</small>}</td><td>{run.rdap_source || 'Pending'}</td><td>{run.observed_expiration_date ?? 'Not observed'}</td><td>{run.dns_source ? `${run.dns_record_count} records via ${run.dns_source}` : 'Pending'}</td><td>{run.dnssec_validated === null ? 'Unknown' : run.dnssec_validated ? 'Validated' : 'Not validated'}</td></tr>)}</tbody></table></div>}
      </>}
    </section>}
  </>
}
