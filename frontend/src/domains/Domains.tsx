import { RefreshCw, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'

import type { WorkspaceContext } from '../workspaces/api'
import type {
  CertificateEndpoint, CertificateMonitoring, DomainDraft, DomainMonitoring, DomainsClient, RegisteredDomain,
} from './api'

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
  const [certificates, setCertificates] = useState<CertificateEndpoint[]>([])
  const [certificateOpen, setCertificateOpen] = useState(false)
  const [certificateProtocol, setCertificateProtocol] = useState<CertificateEndpoint['protocol']>('https')
  const [certificateHostnameId, setCertificateHostnameId] = useState<string>('')
  const [certificateSaving, setCertificateSaving] = useState(false)
  const [certificateChecking, setCertificateChecking] = useState(false)
  const [certificateMonitoring, setCertificateMonitoring] = useState<CertificateMonitoring | null>(null)

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
      const [history, endpoints] = await Promise.all([
        client.monitoring(workspace, domain.id), client.listCertificates(workspace, domain.id),
      ])
      setMonitoring(history)
      setCertificates(endpoints)
      setCertificateMonitoring(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Monitoring history could not be loaded.')
    }
  }

  async function createCertificate() {
    if (!monitoringId) return
    setCertificateSaving(true)
    setError(null)
    try {
      const created = await client.createCertificate(
        workspace, monitoringId, certificateProtocol, certificateHostnameId || null,
      )
      setCertificates((current) => [...current, created])
      setCertificateOpen(false)
      setCertificateHostnameId('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The certificate endpoint could not be saved.')
    } finally {
      setCertificateSaving(false)
    }
  }

  async function openCertificate(endpoint: CertificateEndpoint) {
    if (!monitoringId) return
    setCertificateMonitoring(null)
    setError(null)
    try {
      setCertificateMonitoring(await client.certificateMonitoring(workspace, monitoringId, endpoint.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Certificate history could not be loaded.')
    }
  }

  async function scanCertificate(endpointId: string) {
    if (!monitoringId) return
    setCertificateChecking(true)
    setError(null)
    try {
      await client.scanCertificate(workspace, monitoringId, endpointId)
      setCertificates((current) => current.map((endpoint) => (
        endpoint.id === endpointId ? { ...endpoint, monitor_state: 'queued' } : endpoint
      )))
      setCertificateMonitoring(await client.certificateMonitoring(workspace, monitoringId, endpointId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The certificate check could not be queued.')
    } finally {
      setCertificateChecking(false)
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
        <div className="section-heading domain-subsection-heading"><div><h3>TLS certificate endpoints</h3><p>Fixed-port direct TLS checks retain certificate and validation evidence without storing certificate bodies.</p></div><button type="button" className="secondary-button" onClick={() => setCertificateOpen((current) => !current)}>{certificateOpen ? 'Cancel' : 'Add endpoint'}</button></div>
        {certificateOpen && <div className="certificate-form-row">
          <label><span>Hostname</span><select value={certificateHostnameId} onChange={(event) => setCertificateHostnameId(event.target.value)}><option value="">{monitoring.domain.name} (apex)</option>{monitoring.hostnames.map((hostname) => <option key={hostname.id} value={hostname.id}>{hostname.name}</option>)}</select></label>
          <label><span>Protocol</span><select value={certificateProtocol} onChange={(event) => setCertificateProtocol(event.target.value as CertificateEndpoint['protocol'])}><option value="https">HTTPS · 443</option><option value="smtps">SMTPS · 465</option><option value="imaps">IMAPS · 993</option><option value="pop3s">POP3S · 995</option></select></label>
          <button type="button" className="primary-button" disabled={certificateSaving} onClick={() => { void createCertificate() }}>{certificateSaving ? 'Saving…' : 'Save endpoint'}</button>
        </div>}
        {certificates.length === 0 ? <p className="empty-state">No TLS certificate endpoints are monitored for this domain.</p> : <div className="network-table-wrap"><table className="network-table"><thead><tr><th>Endpoint</th><th>Protocol</th><th>Status</th><th>Expires</th><th>Hostname</th><th>Trust</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{certificates.map((endpoint) => <tr key={endpoint.id}><td><strong>{endpoint.target_name}</strong><small>Port {endpoint.port}</small></td><td>{endpoint.protocol.toUpperCase()}</td><td>{endpoint.monitor_state}</td><td>{endpoint.current_not_after ? new Date(endpoint.current_not_after).toLocaleDateString() : 'Not checked'}</td><td>{endpoint.current_hostname_valid === null ? 'Unknown' : endpoint.current_hostname_valid ? 'Valid' : 'Invalid'}</td><td>{endpoint.current_trust_valid === null ? 'Unknown' : endpoint.current_trust_valid ? 'Trusted' : 'Untrusted'}</td><td><button type="button" className="secondary-button" onClick={() => { void openCertificate(endpoint) }}>History</button></td></tr>)}</tbody></table></div>}
        {certificateMonitoring && <div className="certificate-history"><div className="section-heading"><div><h3>{certificateMonitoring.endpoint.target_name} certificate history</h3><p>{certificateMonitoring.endpoint.protocol.toUpperCase()} on port {certificateMonitoring.endpoint.port}</p></div><button type="button" className="secondary-button" disabled={certificateChecking} onClick={() => { void scanCertificate(certificateMonitoring.endpoint.id) }}><RefreshCw size={16} /> {certificateChecking ? 'Queuing…' : 'Check certificate'}</button></div>
          {certificateMonitoring.alerts.length > 0 && <ul className="domain-monitor-alerts">{certificateMonitoring.alerts.map((alert) => <li key={alert.id}><strong>{alert.kind.replaceAll('_', ' ')}</strong><span>{new Date(alert.created_at).toLocaleString()}</span></li>)}</ul>}
          {certificateMonitoring.runs.length === 0 ? <p className="empty-state">No certificate checks have run.</p> : <div className="network-table-wrap"><table className="network-table"><thead><tr><th>Requested</th><th>State</th><th>Leaf</th><th>Chain</th><th>Validity</th><th>TLS</th></tr></thead><tbody>{certificateMonitoring.runs.map((run) => <tr key={run.id}><td>{new Date(run.created_at).toLocaleString()}</td><td>{run.state}{run.error_code && <small>{run.error_code}</small>}</td><td>{run.subject_common_name || 'Pending'}<small>{run.issuer_common_name || ''}</small></td><td>{run.chain_length ? `${run.chain_length} certificates` : 'Pending'}</td><td>{run.not_after ? `Expires ${new Date(run.not_after).toLocaleDateString()}` : 'Pending'}<small>{run.hostname_valid === null ? '' : run.hostname_valid ? 'Hostname valid' : 'Hostname invalid'}{run.trust_valid === false ? ' · untrusted' : ''}</small></td><td>{run.tls_version || 'Pending'}<small>{run.cipher_name}</small></td></tr>)}</tbody></table></div>}
        </div>}
      </>}
    </section>}
  </>
}
