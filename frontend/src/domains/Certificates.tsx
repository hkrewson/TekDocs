import { useEffect, useMemo, useState } from 'react'
import { Plus, RefreshCw, Search } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { formatDateTime, formatInstantDate, translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { CertificateEndpoint, CertificateMonitoring, DomainMonitoring, DomainsClient, RegisteredDomain } from './api'

export function Certificates({ workspace, client }: { workspace: WorkspaceContext | null; client: DomainsClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(() => searchParams.get('q') ?? '')
  const [domains, setDomains] = useState<RegisteredDomain[] | null>(null)
  const [selectedDomain, setSelectedDomain] = useState<RegisteredDomain | null>(null)
  const [monitoring, setMonitoring] = useState<DomainMonitoring | null>(null)
  const [endpoints, setEndpoints] = useState<CertificateEndpoint[] | null>(null)
  const [history, setHistory] = useState<CertificateMonitoring | null>(null)
  const [adding, setAdding] = useState(false)
  const [protocol, setProtocol] = useState<CertificateEndpoint['protocol']>('https')
  const [hostnameId, setHostnameId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(workspace, controller.signal)
      .then((records) => { if (!controller.signal.aborted) setDomains(records) })
      .catch((caught: unknown) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : translate('certificates.loadFailed')) })
    return () => controller.abort()
  }, [client, workspace])

  const visibleDomains = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return domains ?? []
    return (domains ?? []).filter((domain) => domain.name.toLowerCase().includes(normalized))
  }, [domains, query])

  function updateQuery(value: string) {
    setQuery(value)
    const next = new URLSearchParams(searchParams)
    if (value.trim()) next.set('q', value)
    else next.delete('q')
    setSearchParams(next, { replace: true })
  }

  async function openDomain(domain: RegisteredDomain) {
    setSelectedDomain(domain)
    setMonitoring(null)
    setEndpoints(null)
    setHistory(null)
    setAdding(false)
    setError(null)
    try {
      const [nextMonitoring, nextEndpoints] = await Promise.all([
        client.monitoring(workspace, domain.id),
        client.listCertificates(workspace, domain.id),
      ])
      setMonitoring(nextMonitoring)
      setEndpoints(nextEndpoints)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('certificates.detailFailed'))
    }
  }

  async function createEndpoint() {
    if (!selectedDomain) return
    setBusy(true)
    setError(null)
    try {
      const created = await client.createCertificate(workspace, selectedDomain.id, protocol, hostnameId || null)
      setEndpoints((current) => [...(current ?? []), created])
      setAdding(false)
      setHostnameId('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('certificates.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  async function openHistory(endpoint: CertificateEndpoint) {
    if (!selectedDomain) return
    setHistory(null)
    setError(null)
    try {
      setHistory(await client.certificateMonitoring(workspace, selectedDomain.id, endpoint.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('certificates.historyFailed'))
    }
  }

  async function checkCertificate(endpointId: string) {
    if (!selectedDomain) return
    setBusy(true)
    setError(null)
    try {
      await client.scanCertificate(workspace, selectedDomain.id, endpointId)
      setEndpoints((current) => current?.map((endpoint) => endpoint.id === endpointId ? { ...endpoint, monitor_state: 'queued' } : endpoint) ?? null)
      setHistory(await client.certificateMonitoring(workspace, selectedDomain.id, endpointId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('certificates.checkFailed'))
    } finally {
      setBusy(false)
    }
  }

  return <>
    <header className="page-header"><div><h1>{translate('certificates.heading')}</h1><p>{translate('certificates.intro')}</p></div></header>
    {error && <p className="form-error" role="alert">{error}</p>}
    <section className="content-section" aria-labelledby="certificate-domains-heading">
      <div className="section-heading exposure-heading"><div><h2 id="certificate-domains-heading">{translate('certificates.domains')}</h2><p>{translate('certificates.chooseDomain')}</p></div><label className="exposure-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('certificates.search')}</span><input type="search" value={query} placeholder={translate('certificates.search')} onChange={(event) => updateQuery(event.target.value)} /></label></div>
      {domains === null && !error ? <p role="status">{translate('certificates.loading')}</p> : visibleDomains.length === 0 ? <p className="empty-state">{query ? translate('certificates.noMatches') : translate('certificates.empty')}</p> : <div className="record-selector">{visibleDomains.map((domain) => <button key={domain.id} type="button" className={selectedDomain?.id === domain.id ? 'selected' : undefined} aria-pressed={selectedDomain?.id === domain.id} onClick={() => { void openDomain(domain) }}><span><strong>{domain.name}</strong><small>{domain.monitor_state === 'never' ? translate('certificates.notChecked') : domain.monitor_state}</small></span><span>{domain.expiration_date ?? translate('certificates.expirationUnknown')}</span></button>)}</div>}
    </section>
    {selectedDomain && <section className="content-section" aria-labelledby="certificate-endpoints-heading">
      <div className="section-heading"><div><h2 id="certificate-endpoints-heading">{selectedDomain.name}</h2><p>{translate('certificates.endpointIntro')}</p></div><button className="secondary-button" type="button" aria-expanded={adding} aria-controls="certificate-add-form" onClick={() => setAdding((current) => !current)}><Plus size={15} aria-hidden="true" />{adding ? translate('common.cancel') : translate('certificates.add')}</button></div>
      {adding && monitoring && <div id="certificate-add-form" className="certificate-form-row"><label><span>{translate('certificates.hostname')}</span><select value={hostnameId} onChange={(event) => setHostnameId(event.target.value)}><option value="">{monitoring.domain.name} ({translate('certificates.apex')})</option>{monitoring.hostnames.map((hostname) => <option key={hostname.id} value={hostname.id}>{hostname.name}</option>)}</select></label><label><span>{translate('certificates.protocol')}</span><select value={protocol} onChange={(event) => setProtocol(event.target.value as CertificateEndpoint['protocol'])}><option value="https">HTTPS · 443</option><option value="smtps">SMTPS · 465</option><option value="imaps">IMAPS · 993</option><option value="pop3s">POP3S · 995</option></select></label><button className="primary-button" type="button" disabled={busy} onClick={() => { void createEndpoint() }}>{busy ? translate('common.saving') : translate('certificates.save')}</button></div>}
      {endpoints === null ? <p role="status">{translate('certificates.loadingEndpoints')}</p> : endpoints.length === 0 ? <p className="empty-state">{translate('certificates.noEndpoints')}</p> : <div className="network-table-wrap" role="group" aria-label={translate('domains.certificateTable')} tabIndex={0}><table className="network-table"><caption className="sr-only">{translate('domains.certificateTable')}</caption><thead><tr><th>{translate('certificates.endpoint')}</th><th>{translate('certificates.protocol')}</th><th>{translate('certificates.status')}</th><th>{translate('certificates.expires')}</th><th>{translate('certificates.hostnameValid')}</th><th>{translate('certificates.trust')}</th><th><span className="sr-only">{translate('common.actions')}</span></th></tr></thead><tbody>{endpoints.map((endpoint) => <tr key={endpoint.id}><td><strong>{endpoint.target_name}</strong><small>{translate('certificates.port', { port: endpoint.port })}</small></td><td>{endpoint.protocol.toUpperCase()}</td><td>{endpoint.monitor_state}</td><td>{endpoint.current_not_after ? formatInstantDate(endpoint.current_not_after) : translate('certificates.notChecked')}</td><td>{endpoint.current_hostname_valid === null ? translate('certificates.unknown') : endpoint.current_hostname_valid ? translate('certificates.valid') : translate('certificates.invalid')}</td><td>{endpoint.current_trust_valid === null ? translate('certificates.unknown') : endpoint.current_trust_valid ? translate('certificates.trusted') : translate('certificates.untrusted')}</td><td><button className="secondary-button" type="button" aria-expanded={history?.endpoint.id === endpoint.id} onClick={() => { void openHistory(endpoint) }}>{translate('domains.history')}</button></td></tr>)}</tbody></table></div>}
      {history && <div className="certificate-history"><div className="section-heading"><div><h3>{translate('certificates.history', { endpoint: history.endpoint.target_name })}</h3><p>{history.endpoint.protocol.toUpperCase()} · {translate('certificates.port', { port: history.endpoint.port })}</p></div><button className="secondary-button" type="button" disabled={busy} onClick={() => { void checkCertificate(history.endpoint.id) }}><RefreshCw size={15} aria-hidden="true" />{busy ? translate('certificates.queuing') : translate('certificates.check')}</button></div>{history.alerts.length > 0 && <ul className="domain-monitor-alerts">{history.alerts.map((alert) => <li key={alert.id}><strong>{alert.kind.replaceAll('_', ' ')}</strong><span>{formatDateTime(alert.created_at)}</span></li>)}</ul>}{history.runs.length === 0 ? <p className="empty-state">{translate('certificates.noChecks')}</p> : <div className="network-table-wrap" role="group" aria-label={translate('domains.certificateHistoryTable')} tabIndex={0}><table className="network-table"><caption className="sr-only">{translate('domains.certificateHistoryTable')}</caption><thead><tr><th>{translate('certificates.requested')}</th><th>{translate('certificates.status')}</th><th>{translate('certificates.leaf')}</th><th>{translate('certificates.chain')}</th><th>{translate('certificates.validity')}</th><th>TLS</th><th>{translate('certificates.evidence')}</th></tr></thead><tbody>{history.runs.map((run) => <tr key={run.id}><td>{formatDateTime(run.created_at)}</td><td>{run.state}{run.error_code && <small>{run.error_code}</small>}</td><td>{run.subject_common_name || translate('certificates.pending')}<small>{run.issuer_common_name}</small></td><td>{run.chain_length ? translate('certificates.chainCount', { count: run.chain_length }) : translate('certificates.pending')}</td><td>{run.not_after ? formatInstantDate(run.not_after) : translate('certificates.pending')}<small>{run.hostname_valid === false ? translate('certificates.hostnameInvalid') : ''}{run.trust_valid === false ? ` · ${translate('certificates.untrusted')}` : ''}</small></td><td>{run.tls_version || translate('certificates.pending')}<small>{run.cipher_name}</small></td><td><code title={run.evidence_digest}>{run.evidence_digest ? run.evidence_digest.slice(0, 12) : translate('certificates.pending')}</code></td></tr>)}</tbody></table></div>}</div>}
    </section>}
  </>
}
