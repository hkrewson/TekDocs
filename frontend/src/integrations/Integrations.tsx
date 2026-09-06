import { useEffect, useState } from 'react'
import { Download, Play, Plus, RefreshCw } from 'lucide-react'
import { translate } from '../i18n/localization'

import type { DocumentsClient, DocumentRecord } from '../documentation/api'
import type { WorkspaceContext } from '../workspaces/api'
import type { WebhooksClient } from './api'
import { Imports } from './Imports'
import type { ImportsClient } from './importsApi'
import { browserIntegrationsClient } from './providerApi'
import type {
  GitExportBundle,
  IntegrationConflict,
  IntegrationConnection,
  IntegrationConnectionDraft,
  IntegrationJob,
  IntegrationLog,
  IntegrationObservation,
  IntegrationProvider,
  IntegrationsClient,
} from './providerApi'
import { Webhooks } from './Webhooks'

type Tab = 'connections' | 'imports' | 'reconciliation' | 'exports' | 'webhooks'
const EMPTY_CONNECTION: IntegrationConnectionDraft = {
  provider: 'netbox', name: '', base_url: '', credentials: {}, sync_interval_minutes: 60,
}

export function Integrations({ workspace, client: webhookClient, documentsClient, providerClient = browserIntegrationsClient, importsClient }: {
  workspace: WorkspaceContext; client: WebhooksClient; documentsClient: DocumentsClient; providerClient?: IntegrationsClient; importsClient?: ImportsClient
}) {
  const client = {
    ...webhookClient,
    gitExportDownloadUrl: (selectedWorkspace: WorkspaceContext, bundle: GitExportBundle) =>
      providerClient.gitExportDownloadUrl(selectedWorkspace, bundle),
  }
  const [tab, setTab] = useState<Tab>('connections')
  const [connections, setConnections] = useState<IntegrationConnection[]>([])
  const [providers, setProviders] = useState<IntegrationProvider[]>([])
  const [jobs, setJobs] = useState<IntegrationJob[]>([])
  const [logs, setLogs] = useState<IntegrationLog[]>([])
  const [observations, setObservations] = useState<IntegrationObservation[]>([])
  const [conflicts, setConflicts] = useState<IntegrationConflict[]>([])
  const [exports, setExports] = useState<GitExportBundle[]>([])
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [selectedPublications, setSelectedPublications] = useState<string[]>([])
  const [draft, setDraft] = useState(EMPTY_CONNECTION)
  const [showForm, setShowForm] = useState(false)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rotating, setRotating] = useState<{ connection: IntegrationConnection; credentials: Record<string, string> } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      providerClient.listProviders(workspace, controller.signal),
      providerClient.listConnections(workspace, controller.signal),
      providerClient.listJobs(workspace, controller.signal),
      providerClient.listLogs(workspace, controller.signal),
      providerClient.listObservations(workspace, controller.signal),
      providerClient.listConflicts(workspace, controller.signal),
      providerClient.listGitExports(workspace, controller.signal),
      documentsClient.list({ organizationId: workspace.kind === 'organization' ? workspace.id : undefined }, controller.signal),
    ]).then(([nextProviders, nextConnections, nextJobs, nextLogs, nextObservations, nextConflicts, nextExports, nextDocuments]) => {
      setProviders(nextProviders)
      setConnections(nextConnections)
      setJobs(nextJobs?.results ?? [])
      setLogs(nextLogs?.results ?? [])
      setObservations(nextObservations?.results ?? [])
      setConflicts(nextConflicts?.results ?? [])
      setExports(nextExports)
      setDocuments(nextDocuments.results.filter((item) => !item.is_template))
      setPhase('ready')
    }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [documentsClient, providerClient, workspace])

  async function createConnection() {
    setSaving(true); setError(null)
    try {
      const connection = await providerClient.createConnection(workspace, draft)
      setConnections((current) => [...current, connection].sort((a, b) => a.name.localeCompare(b.name)))
      setDraft(EMPTY_CONNECTION); setShowForm(false)
    } catch { setError(translate('integrations.createFailed')) }
    finally { setSaving(false) }
  }

  const selectedProvider = providers.find((provider) => provider.key === draft.provider)
  const providerFor = (key: string) => providers.find((provider) => provider.key === key)

  async function sync(connection: IntegrationConnection) {
    setSaving(true); setError(null)
    try { const job = await providerClient.startSync(workspace, connection); setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]) }
    catch { setError(translate('integrations.syncFailed')) }
    finally { setSaving(false) }
  }

  async function cancelJob(job: IntegrationJob) {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.cancelJob(workspace, job)
      setJobs((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch { setError(translate('integrations.cancelFailed')) }
    finally { setSaving(false) }
  }

  async function toggle(connection: IntegrationConnection) {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.updateConnection(workspace, connection, !connection.active)
      setConnections((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch { setError(translate('integrations.changeFailed')) }
    finally { setSaving(false) }
  }

  async function rotate(connection: IntegrationConnection, credentials: Record<string, string>) {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.rotateConnection(workspace, connection, credentials)
      setConnections((current) => current.map((item) => item.id === updated.id ? updated : item))
      setRotating(null)
    } catch { setError(translate('integrations.rotateFailed')) }
    finally { setSaving(false) }
  }

  function beginRotate(connection: IntegrationConnection) {
    const provider = providerFor(connection.provider)
    if (!provider) return
    setRotating({ connection, credentials: Object.fromEntries(provider.credential_fields.map((field) => [field.key, field.secret ? '' : connection.provider_details[field.key] ?? ''])) })
  }

  async function reconcile(conflict: IntegrationConflict, resolution: 'keep_local' | 'accept_remote' | 'ignored') {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.resolveConflict(workspace, conflict, resolution)
      setConflicts((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch { setError(translate('integrations.reviewFailed')) }
    finally { setSaving(false) }
  }

  async function createExport() {
    if (selected.length === 0 && selectedPublications.length === 0) return
    setSaving(true); setError(null)
    try {
      const bundle = await providerClient.createGitExport(workspace, selected, selectedPublications)
      setExports((current) => [bundle, ...current]); setSelected([]); setSelectedPublications([])
    } catch { setError(translate('integrations.exportFailed')) }
    finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>Integrations</h1><p>{translate('integrations.intro', { workspace: workspace.name })}</p></div></header>
    <nav className="mode-tabs catalog-tabs" aria-label="Integration sections">
      {([['connections', 'Connections'], ['imports', 'Imports'], ['reconciliation', 'Reconciliation'], ['exports', 'Git exports'], ['webhooks', 'Webhooks']] as [Tab, string][]).map(([value, label]) => <button key={value} className={tab === value ? 'selected' : ''} type="button" onClick={() => setTab(value)}>{label}</button>)}
    </nav>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && tab !== 'imports' && <section className="content-section" role="status">Loading integration activity…</section>}
    {phase === 'error' && tab !== 'imports' && <section className="content-section" role="alert"><h2>Integrations unavailable</h2><p>{translate('integrations.loadFailed')}</p></section>}
    {phase === 'ready' && tab === 'connections' && <>
      <section className="content-section"><div className="section-heading"><div><h2>Connections</h2><p>{translate('integrations.connectionsHelp')}</p></div><button className="primary-button" type="button" onClick={() => setShowForm((value) => !value)}><Plus size={16} />{translate('integrations.newConnection')}</button></div>
        {showForm && <div className="form-grid integration-connection-form"><label><span>Name</span><input value={draft.name} maxLength={100} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label><span>Provider</span><select value={draft.provider} onChange={(event) => { const provider = providers.find((item) => item.key === event.target.value); setDraft({ ...draft, provider: event.target.value, base_url: provider?.default_base_url ?? '', credentials: {}, sync_interval_minutes: provider?.minimum_sync_interval_minutes ?? 60 }) }}>{providers.map((provider) => <option key={provider.key} value={provider.key}>{provider.label}</option>)}</select></label>{selectedProvider?.base_url_editable && <label className="wide-field"><span>API base URL</span><input type="url" value={draft.base_url} placeholder="https://provider.example/api/" onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} /></label>}{selectedProvider?.credential_fields.map((field) => <label key={field.key} className={field.secret ? 'wide-field' : undefined}><span>{field.label}</span><input aria-label={field.label} type={field.input_type === 'password' ? 'password' : 'text'} autoComplete={field.secret ? 'new-password' : 'off'} value={draft.credentials[field.key] ?? ''} onChange={(event) => setDraft({ ...draft, credentials: { ...draft.credentials, [field.key]: event.target.value } })} />{field.help_text && <small>{field.help_text}</small>}</label>)}{selectedProvider?.setup_help_url && <p className="wide-field form-help">{translate('integrations.providerSetupHelp')} <a href={selectedProvider.setup_help_url} target="_blank" rel="noreferrer">{translate('integrations.providerSetupGuidance', { provider: selectedProvider.label })}</a></p>}<label><span>Sync interval (minutes)</span><input type="number" min={selectedProvider?.minimum_sync_interval_minutes ?? 5} max={selectedProvider?.maximum_sync_interval_minutes ?? 10080} value={draft.sync_interval_minutes} onChange={(event) => setDraft({ ...draft, sync_interval_minutes: Number(event.target.value) })} /></label><div className="form-actions wide-field"><button className="primary-button" type="button" disabled={saving || !draft.name || Boolean(selectedProvider?.base_url_editable && !draft.base_url) || Boolean(selectedProvider?.credential_fields.some((field) => (draft.credentials[field.key]?.length ?? 0) < field.minimum_length))} onClick={() => { void createConnection() }}>{saving ? 'Saving…' : 'Save connection'}</button><button className="secondary-button" type="button" onClick={() => setShowForm(false)}>{translate('common.cancel')}</button></div></div>}
        {connections.length === 0 ? <p className="empty-state">No systems are connected to this workspace.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.connectionTable')} tabIndex={0}><table><thead><tr><th>Name</th><th>System</th><th>Status</th><th>Last completed</th><th>Next update</th><th>Needs review</th><th>Actions</th></tr></thead><tbody>{connections.map((connection) => <tr key={connection.id}><td><strong>{connection.name}</strong><br /><small>{connection.provider_details.tenant_id ? `Tenant ${connection.provider_details.tenant_id}` : connection.base_url}</small></td><td>{providerFor(connection.provider)?.label ?? connection.provider} · read-only<br /><small>{connection.provider_details.permission_status === 'verified' ? translate('integrations.permissionsVerified') : connection.provider_details.permission_status === 'not_validated' ? translate('integrations.permissionsUnchecked') : `Every ${connection.sync_interval_minutes} min`} · {connection.reconciliation_counts.observations ?? 0} records</small></td><td>{connection.active ? connection.health_status : 'paused'}{connection.last_error_code && <><br /><code>{connection.last_error_code}</code></>}</td><td>{connection.last_successful_sync_at ? new Date(connection.last_successful_sync_at).toLocaleString() : 'Not yet'}</td><td>{new Date(connection.next_sync_at).toLocaleString()}{connection.rate_limit_reset_at && <><br /><small>Rate limit resets {new Date(connection.rate_limit_reset_at).toLocaleString()}</small></>}</td><td>{connection.reconciliation_counts.review_required ?? 0}</td><td><div className="table-actions"><button className="secondary-button" type="button" disabled={saving || !connection.active} onClick={() => { void sync(connection) }}><Play size={14} />{translate('integrations.sync')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => { void toggle(connection) }}>{connection.active ? 'Pause' : 'Resume'}</button><button className="icon-button" type="button" disabled={saving} aria-label={`Replace the credential for ${connection.name}`} title={`Replace the credential for ${connection.name}`} onClick={() => beginRotate(connection)}><RefreshCw size={15} /></button></div></td></tr>)}</tbody></table></div>}
        {rotating && providerFor(rotating.connection.provider) && <div className="archive-confirmation" role="alertdialog" aria-labelledby="replace-credential-heading" aria-describedby="replace-credential-help"><div><strong id="replace-credential-heading">{translate('integrations.rotateHeading', { name: rotating.connection.name })}</strong><p id="replace-credential-help">{translate('integrations.rotateHelp')}</p><div className="form-grid">{providerFor(rotating.connection.provider)?.credential_fields.map((field) => <label key={field.key}><span>{field.label}</span><input type={field.secret ? 'password' : 'text'} autoComplete={field.secret ? 'new-password' : 'off'} value={rotating.credentials[field.key] ?? ''} onChange={(event) => setRotating({ ...rotating, credentials: { ...rotating.credentials, [field.key]: event.target.value } })} /></label>)}</div></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving || Boolean(providerFor(rotating.connection.provider)?.credential_fields.some((field) => (rotating.credentials[field.key]?.length ?? 0) < field.minimum_length))} onClick={() => { void rotate(rotating.connection, rotating.credentials) }}>{translate('integrations.rotateAction')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setRotating(null)}>{translate('common.cancel')}</button></div></div>}
      </section>
      <section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.recentUpdates')}</h2><p>{translate('integrations.recentUpdatesHelp')}</p></div></div>{jobs.length === 0 ? <p className="empty-state">No updates have run.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.syncJobTable')} tabIndex={0}><table><thead><tr><th>Started</th><th>Connection</th><th>Started by</th><th>Status</th><th>Attempts</th><th>Result</th><th>Actions</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td>{new Date(job.created_at).toLocaleString()}</td><td>{job.connection_name}</td><td>{job.trigger}</td><td>{job.state.replace('_', ' ')}</td><td>{job.attempts}</td><td>{job.last_error_code || `${job.result_counts.observations ?? 0} records found`}</td><td>{(job.state === 'pending' || job.state === 'processing') ? <button className="secondary-button" type="button" disabled={saving} onClick={() => { void cancelJob(job) }}>{translate('common.cancel')}</button> : '—'}</td></tr>)}</tbody></table></div>}</section>
      <section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.sourceRecords')}</h2><p>{translate('integrations.sourceRecordsHelp')}</p></div></div>{observations.length === 0 ? <p className="empty-state">No records have been found.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.observationTable')} tabIndex={0}><table><thead><tr><th>Connection</th><th>Type</th><th>Source record</th><th>Updated at source</th><th>TekDocs record</th><th>Status</th></tr></thead><tbody>{observations.map((observation) => { const conflict = conflicts.find((item) => item.connection_id === observation.connection_id && item.remote_type === observation.remote_type && item.remote_id === observation.remote_id && item.status === 'open'); return <tr key={observation.id}><td>{observation.connection_name}</td><td>{observation.remote_type.replaceAll('_', ' ')}</td><td>{Object.values(observation.safe_projection).filter((value) => value !== null && value !== '').slice(0, 3).map(String).join(' · ') || observation.remote_id}</td><td>{observation.stale ? translate('integrations.staleSource', { date: new Date(observation.source_timestamp ?? observation.observed_at).toLocaleString() }) : new Date(observation.source_timestamp ?? observation.observed_at).toLocaleString()}</td><td>{observation.linked_local_entity_name || conflict?.local_entity_name || observation.linked_local_entity_id || conflict?.local_entity_id || translate('integrations.notLinked')}</td><td>{conflict ? translate('integrations.needsReview') : observation.accepted ? translate('integrations.accepted') : observation.linked_local_entity_id ? translate('integrations.linkedObservation') : translate('integrations.observedOnly')}</td></tr> })}</tbody></table></div>}</section>
      <section className="content-section"><div className="section-heading"><div><h2>Operational log</h2><p>Thirty-day structured events contain allowlisted codes and numeric metrics—not provider messages or response bodies.</p></div></div>{logs.length === 0 ? <p className="empty-state">No provider events have been recorded.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.logTable')} tabIndex={0}><table><thead><tr><th>Time</th><th>Connection</th><th>Level</th><th>Code</th><th>Metrics</th></tr></thead><tbody>{logs.map((event) => <tr key={event.id}><td>{new Date(event.occurred_at).toLocaleString()}</td><td>{event.connection_name}</td><td>{event.level}</td><td><code>{event.code}</code></td><td>{Object.entries(event.metrics).map(([key, value]) => `${key}: ${value}`).join(', ') || '—'}</td></tr>)}</tbody></table></div>}</section>
    </>}
    {tab === 'imports' && <Imports workspace={workspace} client={importsClient} />}
    {phase === 'ready' && tab === 'reconciliation' && <section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.reviewDifferences')}</h2><p>{translate('integrations.reviewDifferencesHelp')}</p></div></div>{conflicts.filter((item) => item.status === 'open').length === 0 ? <p className="empty-state">{translate('integrations.noDifferences')}</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.reconciliationTable')} tabIndex={0}><table><thead><tr><th>Connection</th><th>Source record</th><th>Source details</th><th>Change</th><th>TekDocs record</th><th>Decision</th></tr></thead><tbody>{conflicts.filter((item) => item.status === 'open').map((conflict) => <tr key={conflict.id}><td>{conflict.connection_name}</td><td><code>{conflict.remote_type}:{conflict.remote_id}</code></td><td>{Object.entries(conflict.provider_values ?? {}).filter(([, value]) => value !== null && value !== '').slice(0, 4).map(([key, value]) => `${key}: ${String(value)}`).join(' · ') || 'No saved details'}</td><td>{conflict.difference}</td><td>{conflict.local_entity_name || conflict.local_entity_id || 'Not matched'}</td><td><div className="table-actions"><button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'keep_local') }}>{translate('integrations.keepFlagged')}</button>{conflict.local_entity_id && <button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'accept_remote') }}>{translate('integrations.acknowledgeChange')}</button>}<button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'ignored') }}>{translate('integrations.dismissDifference')}</button></div></td></tr>)}</tbody></table></div>}</section>}
    {phase === 'ready' && tab === 'exports' && <><section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.createExport')}</h2><p>{translate('integrations.createExportHelp')}</p></div><button className="primary-button" type="button" disabled={saving || (selected.length === 0 && selectedPublications.length === 0)} onClick={() => { void createExport() }}>{translate('integrations.createBundle')}</button></div>{documents.length === 0 ? <p className="empty-state">No documents are available in this workspace.</p> : <><h3>Editable documents</h3><div className="integration-export-choices">{documents.map((document) => <label key={document.id}><input type="checkbox" checked={selected.includes(document.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, document.id] : current.filter((id) => id !== document.id))} /><span>{document.title}</span><small>{document.category}</small></label>)}</div>{documents.some((document) => document.publications.length > 0) && <><h3>Published copies</h3><div className="integration-export-choices">{documents.flatMap((document) => document.publications.map((publication) => <label key={publication.id}><input type="checkbox" checked={selectedPublications.includes(publication.id)} onChange={(event) => setSelectedPublications((current) => event.target.checked ? [...current, publication.id] : current.filter((id) => id !== publication.id))} /><span>{document.title}</span><small>{publication.lifecycle_state.replace('_', ' ')}</small></label>))}</div></>}</>}</section><section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.savedExports')}</h2><p>{translate('integrations.savedExportsHelp')}</p></div></div>{exports.length === 0 ? <p className="empty-state">No exports have been created.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.bundleTable')} tabIndex={0}><table><thead><tr><th>Created</th><th>Documents</th><th>Published copies</th><th>Size</th><th>File ID</th><th>Download</th></tr></thead><tbody>{exports.map((bundle) => <tr key={bundle.id}><td>{new Date(bundle.created_at).toLocaleString()}</td><td>{bundle.selection_manifest.documents.length}</td><td>{bundle.selection_manifest.publications.length}</td><td>{Math.ceil(bundle.byte_size / 1024)} KiB</td><td><code>{bundle.content_digest.slice(0, 16)}…</code></td><td>{client.gitExportDownloadUrl && <a className="secondary-button" href={client.gitExportDownloadUrl(workspace, bundle)}><Download size={14} />ZIP</a>}</td></tr>)}</tbody></table></div>}</section></>}
    {tab === 'webhooks' && <Webhooks workspace={workspace} client={client} embedded />}
  </>
}
