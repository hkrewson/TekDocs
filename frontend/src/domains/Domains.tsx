import { AlertTriangle, Plus, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { CollectionPagination } from '../CollectionPagination'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type {
  CertificateEndpoint, CertificateMonitoring, DomainDraft, DomainMonitoring, DomainsClient, RegisteredDomain,
} from './api'
import './domains.css'

const EMPTY: DomainDraft = {
  name: '', registrar_id: null, registration_date: null, expiration_date: null,
  renewal_mode: 'manual', owner_id: null, status: 'active', notes: '',
}
const PAGE_SIZES = [25, 50, 100] as const
const STATUSES = ['active', 'pending', 'expired', 'transferred'] as const
const ORDERINGS = ['name', '-name', 'expiration_date', '-expiration_date', 'status', '-status'] as const

function positiveInteger(value: string | null) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

function pageSizeFrom(value: string | null): typeof PAGE_SIZES[number] {
  const parsed = Number(value)
  return PAGE_SIZES.includes(parsed as typeof PAGE_SIZES[number]) ? parsed as typeof PAGE_SIZES[number] : 25
}

function statusFrom(value: string | null): '' | RegisteredDomain['status'] {
  return STATUSES.includes(value as RegisteredDomain['status']) ? value as RegisteredDomain['status'] : ''
}

function orderingFrom(value: string | null): typeof ORDERINGS[number] {
  return ORDERINGS.includes(value as typeof ORDERINGS[number]) ? value as typeof ORDERINGS[number] : 'name'
}

function formatDate(value: string | null) {
  return value ? new Date(`${value}T00:00:00`).toLocaleDateString() : 'Not recorded'
}

function formatInstant(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not checked yet'
}

export function Domains({ workspace, client }: { workspace: WorkspaceContext | null; client: DomainsClient }) {
  const [parameters, setParameters] = useSearchParams()
  const query = parameters.get('q') ?? ''
  const status = statusFrom(parameters.get('status'))
  const ordering = orderingFrom(parameters.get('ordering'))
  const page = positiveInteger(parameters.get('page'))
  const pageSize = pageSizeFrom(parameters.get('page_size'))
  const selectedId = parameters.get('domain')

  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [domains, setDomains] = useState<RegisteredDomain[]>([])
  const [pageState, setPageState] = useState({ count: 0, hasMore: false })
  const [canManage, setCanManage] = useState(false)
  const [revision, setRevision] = useState(0)
  const [detailPhase, setDetailPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [monitoring, setMonitoring] = useState<DomainMonitoring | null>(null)
  const [certificates, setCertificates] = useState<CertificateEndpoint[]>([])
  const [draft, setDraft] = useState<DomainDraft>({ ...EMPTY })
  const [saving, setSaving] = useState(false)
  const [closingAfterSave, setClosingAfterSave] = useState(false)
  const [drawerError, setDrawerError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)
  const [certificateOpen, setCertificateOpen] = useState(false)
  const [certificateProtocol, setCertificateProtocol] = useState<CertificateEndpoint['protocol']>('https')
  const [certificateHostnameId, setCertificateHostnameId] = useState('')
  const [certificateSaving, setCertificateSaving] = useState(false)
  const [certificateChecking, setCertificateChecking] = useState(false)
  const [certificateMonitoring, setCertificateMonitoring] = useState<CertificateMonitoring | null>(null)
  const creating = selectedId === 'new'
  const createDirty = creating && JSON.stringify(draft) !== JSON.stringify(EMPTY)
  const endpointDirty = Boolean(selectedId && selectedId !== 'new' && certificateOpen && (certificateProtocol !== 'https' || certificateHostnameId))

  const updateParameters = useCallback((changes: Record<string, string | number | null>, replace = false) => {
    setParameters((current) => {
      const next = new URLSearchParams(current)
      for (const [name, value] of Object.entries(changes)) {
        if (value === null || value === '' || name === 'page' && value === 1 || name === 'page_size' && value === 25 || name === 'ordering' && value === 'name') next.delete(name)
        else next.set(name, String(value))
      }
      return next
    }, { replace })
  }, [setParameters])

  const resetDrawerState = useCallback(() => {
    setDraft({ ...EMPTY })
    setDrawerError(null)
    setCertificateOpen(false)
    setCertificateProtocol('https')
    setCertificateHostnameId('')
    setCertificateMonitoring(null)
  }, [])
  const attempt = useUnsavedChanges(
    (createDirty || endpointDirty) && !closingAfterSave,
    (saving || certificateSaving) && !closingAfterSave,
    resetDrawerState,
    Boolean(selectedId && !closingAfterSave),
  )

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setPhase('loading')
      void client.listPage(workspace, { q: query, status, ordering, page, pageSize }, controller.signal)
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
  }, [client, ordering, page, pageSize, query, revision, status, workspace])

  useEffect(() => {
    if (!selectedId || selectedId === 'new') return
    const controller = new AbortController()
    queueMicrotask(() => {
      if (controller.signal.aborted) return
      setDetailPhase('loading')
      setDrawerError(null)
      setMonitoring(null)
      setCertificates([])
      setCertificateMonitoring(null)
      void Promise.all([
        client.monitoring(workspace, selectedId, controller.signal),
        client.listCertificates(workspace, selectedId),
      ]).then(([history, endpoints]) => {
        if (controller.signal.aborted) return
        setMonitoring(history)
        setCertificates(endpoints)
        setDetailPhase('ready')
      }).catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setDrawerError(caught instanceof Error ? caught.message : 'The domain record could not be loaded.')
        setDetailPhase('error')
      })
    })
    return () => controller.abort()
  }, [client, revision, selectedId, workspace])

  function changeCollection(changes: Record<string, string | number | null>, replace = false) {
    updateParameters({ ...changes, page: changes.page ?? null }, replace)
  }

  function openDomain(domain: RegisteredDomain) {
    resetDrawerState()
    updateParameters({ domain: domain.id })
  }

  function openNew() {
    setDraft({ ...EMPTY })
    resetDrawerState()
    updateParameters({ domain: 'new' })
  }

  function closeDrawer() {
    attempt(() => window.setTimeout(() => updateParameters({ domain: null }), 0))
  }

  async function save() {
    setSaving(true)
    setDrawerError(null)
    try {
      const created = await client.create(workspace, draft)
      setClosingAfterSave(true)
      setDraft({ ...EMPTY })
      window.setTimeout(() => {
        updateParameters({ domain: created.id }, true)
        setClosingAfterSave(false)
      }, 50)
      setRevision((value) => value + 1)
    } catch (caught) {
      setClosingAfterSave(false)
      setDrawerError(caught instanceof Error ? caught.message : 'The domain could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  async function scan() {
    if (!selectedId || selectedId === 'new') return
    setChecking(true)
    setDrawerError(null)
    try {
      await client.scan(workspace, selectedId)
      setMonitoring(await client.monitoring(workspace, selectedId))
      setRevision((value) => value + 1)
    } catch (caught) {
      setDrawerError(caught instanceof Error ? caught.message : 'The monitoring check could not be queued.')
    } finally {
      setChecking(false)
    }
  }

  async function createCertificate() {
    if (!selectedId || selectedId === 'new') return
    setCertificateSaving(true)
    setDrawerError(null)
    try {
      const created = await client.createCertificate(workspace, selectedId, certificateProtocol, certificateHostnameId || null)
      setCertificates((current) => [...current, created])
      setCertificateOpen(false)
      setCertificateProtocol('https')
      setCertificateHostnameId('')
    } catch (caught) {
      setDrawerError(caught instanceof Error ? caught.message : 'The certificate endpoint could not be saved.')
    } finally {
      setCertificateSaving(false)
    }
  }

  async function openCertificate(endpoint: CertificateEndpoint) {
    if (!selectedId || selectedId === 'new') return
    setCertificateMonitoring(null)
    setDrawerError(null)
    try {
      setCertificateMonitoring(await client.certificateMonitoring(workspace, selectedId, endpoint.id))
    } catch (caught) {
      setDrawerError(caught instanceof Error ? caught.message : 'Certificate history could not be loaded.')
    }
  }

  async function scanCertificate(endpointId: string) {
    if (!selectedId || selectedId === 'new') return
    setCertificateChecking(true)
    setDrawerError(null)
    try {
      await client.scanCertificate(workspace, selectedId, endpointId)
      setCertificates((current) => current.map((endpoint) => endpoint.id === endpointId ? { ...endpoint, monitor_state: 'queued' } : endpoint))
      setCertificateMonitoring(await client.certificateMonitoring(workspace, selectedId, endpointId))
    } catch (caught) {
      setDrawerError(caught instanceof Error ? caught.message : 'The certificate check could not be queued.')
    } finally {
      setCertificateChecking(false)
    }
  }

  const listedRecord = selectedId && selectedId !== 'new' ? domains.find((domain) => domain.id === selectedId) ?? null : null
  const record = monitoring?.domain ?? listedRecord
  const returnHref = useMemo(() => {
    const next = new URLSearchParams(parameters)
    next.delete('domain')
    return `?${next.toString()}`
  }, [parameters])
  const title = creating ? translate('domains.newHeading') : record?.name ?? 'Domain record'

  return <>
    <header className="page-header"><div><h1>Domains</h1><p>Registration ownership, renewal dates, and monitored DNS health.</p></div>{canManage && <button type="button" className="primary-button" onClick={openNew}><Plus size={16} aria-hidden="true" />{translate('domains.add')}</button>}</header>
    <section className="content-section domain-collection" aria-busy={phase === 'loading'}>
      <div className="domain-toolbar">
        <label className="domain-search"><span>Search</span><input type="search" value={query} placeholder="Domain, registrar, or owner" onChange={(event) => changeCollection({ q: event.target.value }, true)} /></label>
        <label><span>Status</span><select value={status} onChange={(event) => changeCollection({ status: event.target.value })}><option value="">All statuses</option>{STATUSES.map((value) => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></label>
        <label><span>Sort</span><select value={ordering} onChange={(event) => changeCollection({ ordering: event.target.value })}><option value="name">Name</option><option value="-name">Name, reverse</option><option value="expiration_date">Expiration, earliest</option><option value="-expiration_date">Expiration, latest</option><option value="status">Status</option><option value="-status">Status, reverse</option></select></label>
        <label className="collection-page-size"><span>Rows</span><select value={pageSize} onChange={(event) => changeCollection({ page_size: Number(event.target.value) })}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
      </div>
      {(query || status) && <div className="collection-active-filters">{query && <button type="button" className="row-action" onClick={() => changeCollection({ q: null })}>{translate('collections.searchFilter', { value: query })}</button>}{status && <button type="button" className="row-action" onClick={() => changeCollection({ status: null })}>{translate('collections.statusFilter', { value: status })}</button>}</div>}
      {phase === 'loading' && <p className="empty-state" role="status">Loading domains…</p>}
      {phase === 'error' && <div className="empty-state" role="alert"><p>Domains are temporarily unavailable.</p><button type="button" className="secondary-button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {phase === 'ready' && domains.length === 0 && <p className="empty-state">{query || status ? 'No domains match these conditions.' : 'No registered domains are recorded in this workspace.'}</p>}
      {phase === 'ready' && domains.length > 0 && <>
        <div className="domain-list-heading" aria-hidden="true"><span>Domain</span><span>Status</span><span>Expiration</span><span>Monitoring</span></div>
        <ul className="domain-list">{domains.map((domain) => <li key={domain.id}><button id={`domain-row-${domain.id}`} type="button" aria-labelledby={`domain-row-${domain.id}-name`} onClick={() => openDomain(domain)}><span className="domain-identity"><strong id={`domain-row-${domain.id}-name`}>{domain.name}</strong><small>{domain.registrar ?? 'Registrar not recorded'}</small></span><span data-label="Status">{domain.status}</span><span data-label="Expiration">{formatDate(domain.expiration_date)}</span><span data-label="Monitoring">{domain.monitor_state}<small>{domain.last_monitor_at ? new Date(domain.last_monitor_at).toLocaleDateString() : 'Not checked'}</small></span></button></li>)}</ul>
        <CollectionPagination label="Domains" page={page} pageSize={pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={(next) => changeCollection({ page: next })} />
      </>}
    </section>
    {selectedId && <QuickDrawer title={title} returnFocusId={creating ? undefined : `domain-row-${selectedId}`} returnHref={returnHref} returnLabel="Back to domains" onClose={closeDrawer}>
      {creating && !canManage && phase === 'ready' && <p className="form-message error" role="alert">You do not have permission to add domains.</p>}
      {creating && canManage && <DomainCreateForm draft={draft} saving={saving} error={drawerError} onChange={setDraft} onSave={save} onCancel={closeDrawer} />}
      {!creating && detailPhase === 'loading' && <p className="empty-state" role="status">Loading domain record…</p>}
      {!creating && detailPhase === 'error' && <div className="empty-state" role="alert"><p>{drawerError ?? 'The domain record is unavailable.'}</p><button type="button" className="secondary-button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {!creating && detailPhase === 'ready' && record && monitoring && <div className="domain-record">
        {(record.status === 'expired' || record.review_state === 'conflict' || record.monitor_state === 'failed') && <div className="record-warning"><AlertTriangle size={17} aria-hidden="true" /><div><strong>Review required</strong><p>{record.status === 'expired' ? 'The recorded registration has expired.' : record.review_state === 'conflict' ? 'The observed expiration differs from the saved registration.' : 'The latest automated domain check failed.'}</p></div></div>}
        {drawerError && <p className="form-message error" role="alert">{drawerError}</p>}
        <dl className="record-facts"><div><dt>Status</dt><dd>{record.status}</dd></div><div><dt>Registrar</dt><dd>{record.registrar ?? 'Not recorded'}</dd></div><div><dt>Registered</dt><dd>{formatDate(record.registration_date)}</dd></div><div><dt>Expires</dt><dd>{formatDate(record.expiration_date)}</dd></div><div><dt>Renewal</dt><dd>{record.renewal_mode}</dd></div><div><dt>Owner</dt><dd>{record.owner ?? 'Unassigned'}</dd></div><div><dt>Review</dt><dd>{record.review_state}</dd></div><div><dt>Last checked</dt><dd>{formatInstant(record.last_monitor_at)}</dd></div></dl>
        {record.notes && <section className="drawer-section"><h3>Notes</h3><p className="preserve-lines">{record.notes}</p></section>}
        <div className="form-actions"><button type="button" className="primary-button" disabled={checking || !record.monitoring_enabled || !canManage} onClick={() => { void scan() }}><RefreshCw size={15} aria-hidden="true" />{checking ? 'Queuing…' : 'Check now'}</button></div>
        <section className="drawer-section"><div className="drawer-section-heading"><div><h3>Recent monitoring</h3><p>Automated observations stay separate from entered registration data.</p></div></div>
          {monitoring.alerts.length > 0 && <ul className="domain-monitor-alerts">{monitoring.alerts.slice(0, 4).map((alert) => <li key={alert.id}><strong>{alert.kind.replaceAll('_', ' ')}</strong><span>{new Date(alert.created_at).toLocaleString()}</span></li>)}</ul>}
          {monitoring.runs.length === 0 ? <p className="empty-state">{translate('domains.noChecks')}</p> : <DomainRunSummary run={monitoring.runs[0]} />}
          {monitoring.runs.length > 1 && <details className="drawer-disclosure"><summary>Previous checks ({monitoring.runs.length})</summary><div className="drawer-history-list">{monitoring.runs.map((run) => <DomainRunSummary key={run.id} run={run} />)}</div></details>}
        </section>
        <section className="drawer-section"><div className="drawer-section-heading"><div><h3>TLS endpoints</h3><p>Certificate checks for this domain and its recorded hostnames.</p></div>{canManage && <button type="button" className="row-action" aria-expanded={certificateOpen} onClick={() => setCertificateOpen((value) => !value)}>{certificateOpen ? 'Cancel' : 'Add endpoint'}</button>}</div>
          {certificateOpen && <div className="certificate-form-row"><label><span>Hostname</span><select value={certificateHostnameId} onChange={(event) => setCertificateHostnameId(event.target.value)}><option value="">{record.name} (apex)</option>{monitoring.hostnames.map((hostname) => <option key={hostname.id} value={hostname.id}>{hostname.name}</option>)}</select></label><label><span>Protocol</span><select value={certificateProtocol} onChange={(event) => setCertificateProtocol(event.target.value as CertificateEndpoint['protocol'])}><option value="https">HTTPS · 443</option><option value="smtps">SMTPS · 465</option><option value="imaps">IMAPS · 993</option><option value="pop3s">POP3S · 995</option></select></label><button type="button" className="primary-button" disabled={certificateSaving} onClick={() => { void createCertificate() }}>{certificateSaving ? 'Saving…' : 'Save endpoint'}</button></div>}
          {certificates.length === 0 ? <p className="empty-state">No TLS certificate endpoints are monitored for this domain.</p> : <ul className="domain-endpoint-list">{certificates.map((endpoint) => <li key={endpoint.id}><button type="button" onClick={() => { void openCertificate(endpoint) }}><span><strong>{endpoint.target_name}</strong><small>{endpoint.protocol.toUpperCase()} · {translate('certificates.port', { port: endpoint.port })}</small></span><span>{endpoint.monitor_state}<small>{endpoint.current_not_after ? `Expires ${new Date(endpoint.current_not_after).toLocaleDateString()}` : 'Not checked'}</small></span></button></li>)}</ul>}
          {certificateMonitoring && <div className="certificate-history"><div className="drawer-section-heading"><div><h4>{certificateMonitoring.endpoint.target_name}</h4><p>{certificateMonitoring.endpoint.protocol.toUpperCase()} on port {certificateMonitoring.endpoint.port}</p></div><button type="button" className="row-action" disabled={certificateChecking || !canManage} onClick={() => { void scanCertificate(certificateMonitoring.endpoint.id) }}><RefreshCw size={14} aria-hidden="true" />{certificateChecking ? 'Queuing…' : 'Check certificate'}</button></div>{certificateMonitoring.alerts.length > 0 && <ul className="domain-monitor-alerts">{certificateMonitoring.alerts.map((alert) => <li key={alert.id}><strong>{alert.kind.replaceAll('_', ' ')}</strong><span>{new Date(alert.created_at).toLocaleString()}</span></li>)}</ul>}{certificateMonitoring.runs.length === 0 ? <p className="empty-state">No certificate checks have run.</p> : <div className="drawer-history-list">{certificateMonitoring.runs.map((run) => <div className="drawer-history-row" key={run.id}><strong>{run.state}</strong><span>{run.subject_common_name || 'Pending'}{run.issuer_common_name ? ` · ${run.issuer_common_name}` : ''}</span><small>{run.not_after ? `Expires ${new Date(run.not_after).toLocaleDateString()}` : new Date(run.created_at).toLocaleString()}</small></div>)}</div>}</div>}
        </section>
      </div>}
    </QuickDrawer>}
  </>
}

function DomainCreateForm({ draft, saving, error, onChange, onSave, onCancel }: { draft: DomainDraft; saving: boolean; error: string | null; onChange: (draft: DomainDraft) => void; onSave: () => Promise<void>; onCancel: () => void }) {
  return <form className="domain-create-form" onSubmit={(event) => { event.preventDefault(); void onSave() }}>
    <p>{translate('domains.newHelp')}</p>
    {error && <p className="form-message error" role="alert">{error}</p>}
    <div className="form-grid"><label className="wide-field"><span>Domain name</span><input autoFocus required value={draft.name} placeholder="example.com" onChange={(event) => onChange({ ...draft, name: event.target.value })} /></label><label><span>Status</span><select value={draft.status} onChange={(event) => onChange({ ...draft, status: event.target.value as DomainDraft['status'] })}><option value="active">Active</option><option value="pending">Pending</option><option value="expired">Expired</option><option value="transferred">Transferred</option></select></label><label><span>Renewal</span><select value={draft.renewal_mode} onChange={(event) => onChange({ ...draft, renewal_mode: event.target.value as DomainDraft['renewal_mode'] })}><option value="manual">Manual</option><option value="auto">Automatic</option><option value="external">Managed externally</option></select></label><label><span>Registered on</span><input type="date" value={draft.registration_date ?? ''} onChange={(event) => onChange({ ...draft, registration_date: event.target.value || null })} /></label><label><span>Expires on</span><input type="date" value={draft.expiration_date ?? ''} onChange={(event) => onChange({ ...draft, expiration_date: event.target.value || null })} /></label><label className="wide-field"><span>Notes (Markdown)</span><textarea rows={5} value={draft.notes} onChange={(event) => onChange({ ...draft, notes: event.target.value })} /></label></div>
    <div className="form-actions"><button className="primary-button" disabled={saving || !draft.name.trim()}>{saving ? 'Saving…' : 'Save domain'}</button><button type="button" className="secondary-button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
  </form>
}

function DomainRunSummary({ run }: { run: DomainMonitoring['runs'][number] }) {
  return <div className="drawer-history-row"><strong>{run.state}{run.error_code ? ` · ${run.error_code}` : ''}</strong><span>{run.dns_source ? `${run.dns_record_count} DNS records · ${run.dnssec_validated ? 'DNSSEC validated' : 'DNSSEC not validated'}` : 'Collection pending'}</span><small>{new Date(run.created_at).toLocaleString()} · {run.evidence_digest ? `Result ${run.evidence_digest.slice(0, 12)}` : 'No result yet'}</small></div>
}
