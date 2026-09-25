import { AlertTriangle, Plus, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { CollectionPagination } from '../CollectionPagination'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { formatDateTime, formatInstantDate, translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { CertificateEndpoint, CertificateMonitoring, DomainMonitoring, DomainsClient, RegisteredDomain } from './api'
import './domains.css'

const PAGE_SIZES = [25, 50, 100] as const

function positiveInteger(value: string | null) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

function pageSizeFrom(value: string | null): typeof PAGE_SIZES[number] {
  const parsed = Number(value)
  return PAGE_SIZES.includes(parsed as typeof PAGE_SIZES[number]) ? parsed as typeof PAGE_SIZES[number] : 25
}

export function Certificates({ workspace, client }: { workspace: WorkspaceContext | null; client: DomainsClient }) {
  const [parameters, setParameters] = useSearchParams()
  const query = parameters.get('q') ?? ''
  const page = positiveInteger(parameters.get('page'))
  const pageSize = pageSizeFrom(parameters.get('page_size'))
  const selectedDomainId = parameters.get('domain')
  const selectedEndpointId = parameters.get('endpoint')
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [domains, setDomains] = useState<RegisteredDomain[]>([])
  const [pageState, setPageState] = useState({ count: 0, hasMore: false })
  const [canManage, setCanManage] = useState(false)
  const [revision, setRevision] = useState(0)
  const [detailPhase, setDetailPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [monitoring, setMonitoring] = useState<DomainMonitoring | null>(null)
  const [endpoints, setEndpoints] = useState<CertificateEndpoint[]>([])
  const [historyPhase, setHistoryPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [history, setHistory] = useState<CertificateMonitoring | null>(null)
  const [adding, setAdding] = useState(false)
  const [protocol, setProtocol] = useState<CertificateEndpoint['protocol']>('https')
  const [hostnameId, setHostnameId] = useState('')
  const [busy, setBusy] = useState(false)
  const [closingAfterSave, setClosingAfterSave] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const draftDirty = Boolean(adding && (protocol !== 'https' || hostnameId))

  const updateParameters = useCallback((changes: Record<string, string | number | null>, replace = false) => {
    setParameters((current) => {
      const next = new URLSearchParams(current)
      for (const [name, value] of Object.entries(changes)) {
        if (value === null || value === '' || name === 'page' && value === 1 || name === 'page_size' && value === 25) next.delete(name)
        else next.set(name, String(value))
      }
      return next
    }, { replace })
  }, [setParameters])

  const discard = useCallback(() => {
    setAdding(false)
    setProtocol('https')
    setHostnameId('')
    setError(null)
  }, [])
  const attempt = useUnsavedChanges(draftDirty && !closingAfterSave, busy && !closingAfterSave, discard, Boolean(selectedDomainId && adding && !closingAfterSave))

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setPhase('loading')
      void client.listPage(workspace, { q: query, status: '', ordering: 'name', page, pageSize }, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return
          setDomains(result.results)
          setPageState({ count: result.count, hasMore: result.has_more })
          setCanManage(result.can_manage)
          setPhase('ready')
        })
        .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, page, pageSize, query, revision, workspace])

  useEffect(() => {
    if (!selectedDomainId) return
    const controller = new AbortController()
    queueMicrotask(() => {
      if (controller.signal.aborted) return
      setDetailPhase('loading')
      setError(null)
      setMonitoring(null)
      setEndpoints([])
      void Promise.all([
        client.monitoring(workspace, selectedDomainId, controller.signal),
        client.listCertificates(workspace, selectedDomainId),
      ]).then(([nextMonitoring, nextEndpoints]) => {
        if (controller.signal.aborted) return
        setMonitoring(nextMonitoring)
        setEndpoints(nextEndpoints)
        setDetailPhase('ready')
      }).catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setError(caught instanceof Error ? caught.message : translate('certificates.detailFailed'))
        setDetailPhase('error')
      })
    })
    return () => controller.abort()
  }, [client, revision, selectedDomainId, workspace])

  useEffect(() => {
    if (!selectedDomainId || !selectedEndpointId) return
    let active = true
    queueMicrotask(() => {
      if (!active) return
      setHistory(null)
      setHistoryPhase('loading')
      setError(null)
      void client.certificateMonitoring(workspace, selectedDomainId, selectedEndpointId)
        .then((result) => { if (active) { setHistory(result); setHistoryPhase('ready') } })
        .catch((caught: unknown) => {
          if (!active) return
          setError(caught instanceof Error ? caught.message : translate('certificates.historyFailed'))
          setHistoryPhase('error')
        })
    })
    return () => { active = false }
  }, [client, revision, selectedDomainId, selectedEndpointId, workspace])

  function changeCollection(changes: Record<string, string | number | null>, replace = false) {
    updateParameters({ ...changes, page: changes.page ?? null }, replace)
  }

  function openDomain(domain: RegisteredDomain) {
    discard()
    updateParameters({ domain: domain.id, endpoint: null })
  }

  function closeDrawer() {
    attempt(() => window.setTimeout(() => updateParameters({ domain: null, endpoint: null }), 0))
  }

  async function createEndpoint() {
    if (!selectedDomainId) return
    setBusy(true)
    setError(null)
    try {
      const created = await client.createCertificate(workspace, selectedDomainId, protocol, hostnameId || null)
      setEndpoints((current) => [...current, created])
      setClosingAfterSave(true)
      discard()
      window.setTimeout(() => {
        updateParameters({ endpoint: created.id }, true)
        setClosingAfterSave(false)
      }, 50)
    } catch (caught) {
      setClosingAfterSave(false)
      setError(caught instanceof Error ? caught.message : translate('certificates.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  async function checkCertificate(endpointId: string) {
    if (!selectedDomainId) return
    setBusy(true)
    setError(null)
    try {
      await client.scanCertificate(workspace, selectedDomainId, endpointId)
      setEndpoints((current) => current.map((endpoint) => endpoint.id === endpointId ? { ...endpoint, monitor_state: 'queued' } : endpoint))
      setHistory(await client.certificateMonitoring(workspace, selectedDomainId, endpointId))
      setHistoryPhase('ready')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('certificates.checkFailed'))
    } finally {
      setBusy(false)
    }
  }

  const listedDomain = selectedDomainId ? domains.find((domain) => domain.id === selectedDomainId) ?? null : null
  const record = monitoring?.domain ?? listedDomain
  const returnHref = useMemo(() => {
    const next = new URLSearchParams(parameters)
    next.delete('domain')
    next.delete('endpoint')
    return `?${next.toString()}`
  }, [parameters])

  return <>
    <header className="page-header"><div><h1>{translate('certificates.heading')}</h1><p>{translate('certificates.intro')}</p></div></header>
    <section className="content-section domain-collection" aria-busy={phase === 'loading'}>
      <div className="domain-toolbar certificate-toolbar"><label className="domain-search"><span>{translate('certificates.search')}</span><input type="search" value={query} placeholder="Domain name" onChange={(event) => changeCollection({ q: event.target.value }, true)} /></label><label className="collection-page-size"><span>Rows</span><select value={pageSize} onChange={(event) => changeCollection({ page_size: Number(event.target.value) })}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></label></div>
      {query && <div className="collection-active-filters"><button type="button" className="row-action" onClick={() => changeCollection({ q: null })}>{translate('collections.searchFilter', { value: query })}</button></div>}
      {phase === 'loading' && <p className="empty-state" role="status">{translate('certificates.loading')}</p>}
      {phase === 'error' && <div className="empty-state" role="alert"><p>{translate('certificates.loadFailed')}</p><button type="button" className="secondary-button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {phase === 'ready' && domains.length === 0 && <p className="empty-state">{query ? translate('certificates.noMatches') : translate('certificates.empty')}</p>}
      {phase === 'ready' && domains.length > 0 && <>
        <div className="certificate-domain-heading" aria-hidden="true"><span>Domain</span><span>Registration expires</span><span>Domain health</span></div>
        <ul className="certificate-domain-list">{domains.map((domain) => <li key={domain.id}><button id={`certificate-domain-${domain.id}`} type="button" aria-labelledby={`certificate-domain-${domain.id}-name`} onClick={() => openDomain(domain)}><span><strong id={`certificate-domain-${domain.id}-name`}>{domain.name}</strong><small>{domain.registrar ?? 'Registrar not recorded'}</small></span><span data-label="Registration expires">{domain.expiration_date ?? translate('certificates.expirationUnknown')}</span><span data-label="Domain health">{domain.monitor_state}<small>{translate('certificates.reviewState', { state: domain.review_state })}</small></span></button></li>)}</ul>
        <CollectionPagination label={translate('certificates.heading')} page={page} pageSize={pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={(next) => changeCollection({ page: next })} />
      </>}
    </section>
    {selectedDomainId && <QuickDrawer title={record ? `Certificates · ${record.name}` : 'Certificate endpoints'} returnFocusId={`certificate-domain-${selectedDomainId}`} returnHref={returnHref} returnLabel="Back to certificate domains" onClose={closeDrawer}>
      {detailPhase === 'loading' && <p className="empty-state" role="status">{translate('certificates.loadingEndpoints')}</p>}
      {detailPhase === 'error' && <div className="empty-state" role="alert"><p>{error ?? translate('certificates.detailFailed')}</p><button type="button" className="secondary-button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {detailPhase === 'ready' && record && monitoring && <div className="certificate-record">
        <dl className="record-facts"><div><dt>Registration expires</dt><dd>{record.expiration_date ?? translate('certificates.expirationUnknown')}</dd></div><div><dt>Domain monitoring</dt><dd>{record.monitor_state}</dd></div><div><dt>Review</dt><dd>{record.review_state}</dd></div><div><dt>TLS endpoints</dt><dd>{endpoints.length}</dd></div></dl>
        {error && <p className="form-message error" role="alert">{error}</p>}
        <section className="drawer-section"><div className="drawer-section-heading"><div><h3>TLS endpoints</h3><p>{translate('certificates.endpointIntro')}</p></div>{canManage && <button type="button" className="row-action" aria-expanded={adding} onClick={() => { if (adding) discard(); else setAdding(true) }}><Plus size={14} aria-hidden="true" />{adding ? translate('common.cancel') : translate('certificates.add')}</button>}</div>
          {adding && <div className="certificate-form-row"><label><span>{translate('certificates.hostname')}</span><select value={hostnameId} onChange={(event) => setHostnameId(event.target.value)}><option value="">{record.name} ({translate('certificates.apex')})</option>{monitoring.hostnames.map((hostname) => <option key={hostname.id} value={hostname.id}>{hostname.name}</option>)}</select></label><label><span>{translate('certificates.protocol')}</span><select value={protocol} onChange={(event) => setProtocol(event.target.value as CertificateEndpoint['protocol'])}><option value="https">HTTPS · 443</option><option value="smtps">SMTPS · 465</option><option value="imaps">IMAPS · 993</option><option value="pop3s">POP3S · 995</option></select></label><button className="primary-button" type="button" disabled={busy} onClick={() => { void createEndpoint() }}>{busy ? translate('common.saving') : translate('certificates.save')}</button></div>}
          {endpoints.length === 0 ? <p className="empty-state">{translate('certificates.noEndpoints')}</p> : <ul className="certificate-endpoint-list">{endpoints.map((endpoint) => <li key={endpoint.id}><button type="button" aria-label={`${endpoint.target_name} ${endpoint.protocol.toUpperCase()} certificate`} aria-pressed={selectedEndpointId === endpoint.id} onClick={() => updateParameters({ endpoint: endpoint.id })}><span><strong>{endpoint.target_name}</strong><small>{endpoint.protocol.toUpperCase()} · {translate('certificates.port', { port: endpoint.port })}</small></span><span>{endpoint.monitor_state}<small>{endpoint.current_not_after ? `Expires ${formatInstantDate(endpoint.current_not_after)}` : translate('certificates.notChecked')}</small></span></button></li>)}</ul>}
        </section>
        {selectedEndpointId && <section className="drawer-section certificate-observation"><div className="drawer-section-heading"><div><h3>{history?.endpoint.target_name ?? 'Certificate observation'}</h3><p>Retained validation evidence and check history.</p></div></div>
          {historyPhase === 'loading' && <p className="empty-state" role="status">Loading certificate history…</p>}
          {historyPhase === 'error' && <div className="empty-state" role="alert"><p>{error ?? translate('certificates.historyFailed')}</p><button type="button" className="secondary-button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
          {historyPhase === 'ready' && history && <CertificateDetail history={history} canManage={canManage} busy={busy} onCheck={checkCertificate} />}
        </section>}
      </div>}
    </QuickDrawer>}
  </>
}

function CertificateDetail({ history, canManage, busy, onCheck }: { history: CertificateMonitoring; canManage: boolean; busy: boolean; onCheck: (id: string) => Promise<void> }) {
  const endpoint = history.endpoint
  const needsReview = endpoint.current_hostname_valid === false || endpoint.current_trust_valid === false || endpoint.monitor_state === 'failed'
  return <div className="certificate-detail">
    {needsReview && <div className="record-warning"><AlertTriangle size={17} aria-hidden="true" /><div><strong>Review required</strong><p>The latest certificate observation has a hostname, trust, or collection failure.</p></div></div>}
    <dl className="record-facts"><div><dt>Protocol</dt><dd>{endpoint.protocol.toUpperCase()} · {translate('certificates.port', { port: endpoint.port })}</dd></div><div><dt>Status</dt><dd>{endpoint.monitor_state}</dd></div><div><dt>Expires</dt><dd>{endpoint.current_not_after ? formatInstantDate(endpoint.current_not_after) : translate('certificates.notChecked')}</dd></div><div><dt>Hostname</dt><dd>{endpoint.current_hostname_valid === null ? translate('certificates.unknown') : endpoint.current_hostname_valid ? translate('certificates.valid') : translate('certificates.invalid')}</dd></div><div><dt>Trust</dt><dd>{endpoint.current_trust_valid === null ? translate('certificates.unknown') : endpoint.current_trust_valid ? translate('certificates.trusted') : translate('certificates.untrusted')}</dd></div></dl>
    <div className="form-actions">{canManage && <button type="button" className="primary-button" disabled={busy} onClick={() => { void onCheck(endpoint.id) }}><RefreshCw size={15} aria-hidden="true" />{busy ? translate('certificates.queuing') : translate('certificates.check')}</button>}</div>
    {history.alerts.length > 0 && <ul className="domain-monitor-alerts">{history.alerts.map((alert) => <li key={alert.id}><strong>{alert.kind.replaceAll('_', ' ')}</strong><span>{formatDateTime(alert.created_at)}</span></li>)}</ul>}
    {history.runs.length === 0 ? <p className="empty-state">{translate('certificates.noChecks')}</p> : <div className="drawer-history-list">{history.runs.map((run) => <div className="drawer-history-row" key={run.id}><strong>{run.state}{run.error_code ? ` · ${run.error_code}` : ''}</strong><span>{run.subject_common_name || translate('certificates.pending')}{run.issuer_common_name ? ` · ${run.issuer_common_name}` : ''}</span><small>{formatDateTime(run.created_at)} · {run.tls_version || translate('certificates.pending')} · {run.evidence_digest ? `Result ${run.evidence_digest.slice(0, 12)}` : translate('certificates.pending')}</small></div>)}</div>}
  </div>
}
