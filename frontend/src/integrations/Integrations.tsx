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
  IntegrationProvider,
  IntegrationsClient,
} from './providerApi'
import { Webhooks } from './Webhooks'

type Tab = 'connections' | 'imports' | 'reconciliation' | 'exports' | 'webhooks'
const EMPTY_CONNECTION: IntegrationConnectionDraft = {
  provider: 'netbox', name: '', base_url: '', api_token: '', sync_interval_minutes: 60,
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

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      providerClient.listProviders(workspace, controller.signal),
      providerClient.listConnections(workspace, controller.signal),
      providerClient.listJobs(workspace, controller.signal),
      providerClient.listLogs(workspace, controller.signal),
      providerClient.listConflicts(workspace, controller.signal),
      providerClient.listGitExports(workspace, controller.signal),
      documentsClient.list({ organizationId: workspace.kind === 'organization' ? workspace.id : undefined }, controller.signal),
    ]).then(([nextProviders, nextConnections, nextJobs, nextLogs, nextConflicts, nextExports, nextDocuments]) => {
      setProviders(nextProviders)
      setConnections(nextConnections)
      setJobs(nextJobs?.results ?? [])
      setLogs(nextLogs?.results ?? [])
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
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The provider connection could not be created.') }
    finally { setSaving(false) }
  }

  const selectedProvider = providers.find((provider) => provider.key === draft.provider)
  const providerFor = (key: string) => providers.find((provider) => provider.key === key)

  async function sync(connection: IntegrationConnection) {
    setSaving(true); setError(null)
    try { const job = await providerClient.startSync(workspace, connection); setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The sync could not be queued.') }
    finally { setSaving(false) }
  }

  async function toggle(connection: IntegrationConnection) {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.updateConnection(workspace, connection, !connection.active)
      setConnections((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The connection could not be changed.') }
    finally { setSaving(false) }
  }

  async function rotate(connection: IntegrationConnection) {
    const apiToken = window.prompt(`Enter the replacement API token for ${connection.name}. It will be encrypted and will not be shown again.`)
    if (!apiToken) return
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.rotateConnection(workspace, connection, apiToken)
      setConnections((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The provider credential could not be rotated.') }
    finally { setSaving(false) }
  }

  async function reconcile(conflict: IntegrationConflict, resolution: 'keep_local' | 'accept_remote' | 'ignored') {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.resolveConflict(workspace, conflict, resolution)
      setConflicts((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The reconciliation decision could not be saved.') }
    finally { setSaving(false) }
  }

  async function createExport() {
    if (selected.length === 0 && selectedPublications.length === 0) return
    setSaving(true); setError(null)
    try {
      const bundle = await providerClient.createGitExport(workspace, selected, selectedPublications)
      setExports((current) => [bundle, ...current]); setSelected([]); setSelectedPublications([])
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The sanitized export could not be created.') }
    finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>Integrations</h1><p>Safe imports, read-only provider sync, reviewed reconciliation, signed webhooks, and sanitized exports for {workspace.name}.</p></div></header>
    <nav className="mode-tabs catalog-tabs" aria-label="Integration sections">
      {([['connections', 'Connections'], ['imports', 'Imports'], ['reconciliation', 'Reconciliation'], ['exports', 'Git exports'], ['webhooks', 'Webhooks']] as [Tab, string][]).map(([value, label]) => <button key={value} className={tab === value ? 'selected' : ''} type="button" onClick={() => setTab(value)}>{label}</button>)}
    </nav>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && tab !== 'imports' && <section className="content-section" role="status">Loading integration activity…</section>}
    {phase === 'error' && tab !== 'imports' && <section className="content-section" role="alert"><h2>Integration activity unavailable</h2><p>Refresh the page or verify your integration permissions.</p></section>}
    {phase === 'ready' && tab === 'connections' && <>
      <section className="content-section"><div className="section-heading"><div><h2>Provider connections</h2><p>Provider sync is read-only. Credentials are encrypted and never returned after setup.</p></div><button className="primary-button" type="button" onClick={() => setShowForm((value) => !value)}><Plus size={16} />{translate('integrations.newConnection')}</button></div>
        {showForm && <div className="form-grid integration-connection-form"><label><span>Name</span><input value={draft.name} maxLength={100} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label><span>Provider</span><select value={draft.provider} onChange={(event) => { const provider = providers.find((item) => item.key === event.target.value); setDraft({ ...draft, provider: event.target.value, sync_interval_minutes: provider?.minimum_sync_interval_minutes ?? 60 }) }}>{providers.map((provider) => <option key={provider.key} value={provider.key}>{provider.label}</option>)}</select></label><label className="wide-field"><span>API base URL</span><input type="url" value={draft.base_url} placeholder="https://provider.example/api/" onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} /></label><label className="wide-field"><span>{selectedProvider?.credential_fields[0]?.label ?? 'Credential'}</span><input type="password" autoComplete="new-password" value={draft.api_token} onChange={(event) => setDraft({ ...draft, api_token: event.target.value })} /><small>Requires a recent MFA-authenticated session. The value is not retained in browser state after save.</small></label><label><span>Sync interval (minutes)</span><input type="number" min={selectedProvider?.minimum_sync_interval_minutes ?? 5} max={selectedProvider?.maximum_sync_interval_minutes ?? 10080} value={draft.sync_interval_minutes} onChange={(event) => setDraft({ ...draft, sync_interval_minutes: Number(event.target.value) })} /></label><div className="form-actions wide-field"><button className="primary-button" type="button" disabled={saving || !draft.name || !draft.base_url || draft.api_token.length < (selectedProvider?.credential_fields[0]?.minimum_length ?? 8)} onClick={() => { void createConnection() }}>{saving ? 'Saving…' : 'Save connection'}</button><button className="secondary-button" type="button" onClick={() => setShowForm(false)}>{translate('common.cancel')}</button></div></div>}
        {connections.length === 0 ? <p className="empty-state">No external provider connections belong to this Workspace.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.connectionTable')} tabIndex={0}><table><thead><tr><th>Name</th><th>Provider</th><th>Health</th><th>Last success</th><th>Next attempt</th><th>Review</th><th>Actions</th></tr></thead><tbody>{connections.map((connection) => <tr key={connection.id}><td><strong>{connection.name}</strong><br /><small>{connection.base_url}</small></td><td>{providerFor(connection.provider)?.label ?? connection.provider} · read-only<br /><small>Every {connection.sync_interval_minutes} min</small></td><td>{connection.active ? connection.health_status : 'paused'}{connection.last_error_code && <><br /><code>{connection.last_error_code}</code></>}</td><td>{connection.last_successful_sync_at ? new Date(connection.last_successful_sync_at).toLocaleString() : 'Not yet'}</td><td>{new Date(connection.next_sync_at).toLocaleString()}{connection.rate_limit_reset_at && <><br /><small>Rate limit resets {new Date(connection.rate_limit_reset_at).toLocaleString()}</small></>}</td><td>{connection.reconciliation_counts.review_required ?? 0}</td><td><div className="table-actions"><button className="secondary-button" type="button" disabled={saving || !connection.active} onClick={() => { void sync(connection) }}><Play size={14} />{translate('integrations.sync')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => { void toggle(connection) }}>{connection.active ? 'Pause' : 'Resume'}</button><button className="icon-button" type="button" disabled={saving} aria-label={`Rotate ${connection.name} provider credential`} onClick={() => { void rotate(connection) }}><RefreshCw size={15} /></button></div></td></tr>)}</tbody></table></div>}
      </section>
      <section className="content-section"><div className="section-heading"><div><h2>Recent sync jobs</h2><p>Jobs resume by bounded cursor and retain only safe counts and error codes.</p></div></div>{jobs.length === 0 ? <p className="empty-state">No sync jobs have been queued.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.syncJobTable')} tabIndex={0}><table><thead><tr><th>Created</th><th>Connection</th><th>Trigger</th><th>State</th><th>Attempts</th><th>Result</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td>{new Date(job.created_at).toLocaleString()}</td><td>{job.connection_name}</td><td>{job.trigger}</td><td>{job.state.replace('_', ' ')}</td><td>{job.attempts}</td><td>{job.last_error_code || `${job.result_counts.observations ?? 0} observations`}</td></tr>)}</tbody></table></div>}</section>
      <section className="content-section"><div className="section-heading"><div><h2>Operational log</h2><p>Thirty-day structured events contain allowlisted codes and numeric metrics—not provider messages or response bodies.</p></div></div>{logs.length === 0 ? <p className="empty-state">No provider events have been recorded.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.logTable')} tabIndex={0}><table><thead><tr><th>Time</th><th>Connection</th><th>Level</th><th>Code</th><th>Metrics</th></tr></thead><tbody>{logs.map((event) => <tr key={event.id}><td>{new Date(event.occurred_at).toLocaleString()}</td><td>{event.connection_name}</td><td>{event.level}</td><td><code>{event.code}</code></td><td>{Object.entries(event.metrics).map(([key, value]) => `${key}: ${value}`).join(', ') || '—'}</td></tr>)}</tbody></table></div>}</section>
    </>}
    {tab === 'imports' && <Imports workspace={workspace} client={importsClient} />}
    {phase === 'ready' && tab === 'reconciliation' && <section className="content-section"><div className="section-heading"><div><h2>Reconciliation queue</h2><p>Provider differences require an explicit decision. “Accept remote” updates only the external identity fingerprint; it never overwrites a TekDocs record.</p></div></div>{conflicts.filter((item) => item.status === 'open').length === 0 ? <p className="empty-state">No unresolved provider differences.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.reconciliationTable')} tabIndex={0}><table><thead><tr><th>Connection</th><th>Remote object</th><th>Difference</th><th>TekDocs match</th><th>Decision</th></tr></thead><tbody>{conflicts.filter((item) => item.status === 'open').map((conflict) => <tr key={conflict.id}><td>{conflict.connection_name}</td><td><code>{conflict.remote_type}:{conflict.remote_id}</code></td><td>{conflict.difference}</td><td>{conflict.local_entity_id ?? 'Unmatched'}</td><td><div className="table-actions"><button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'keep_local') }}>{translate('integrations.keepTekdocs')}</button>{conflict.local_entity_id && <button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'accept_remote') }}>{translate('integrations.acceptFingerprint')}</button>}<button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'ignored') }}>{translate('integrations.ignore')}</button></div></td></tr>)}</tbody></table></div>}</section>}
    {phase === 'ready' && tab === 'exports' && <><section className="content-section"><div className="section-heading"><div><h2>Create sanitized Git bundle</h2><p>Select editable Markdown and/or immutable STATIC publications. Credential references, attachment content, secrets, audit data, provider payloads, and editor HTML are excluded.</p></div><button className="primary-button" type="button" disabled={saving || (selected.length === 0 && selectedPublications.length === 0)} onClick={() => { void createExport() }}>{translate('integrations.createBundle')}</button></div>{documents.length === 0 ? <p className="empty-state">No documents are available in this Workspace.</p> : <><h3>Editable documents</h3><div className="integration-export-choices">{documents.map((document) => <label key={document.id}><input type="checkbox" checked={selected.includes(document.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, document.id] : current.filter((id) => id !== document.id))} /><span>{document.title}</span><small>{document.category}</small></label>)}</div>{documents.some((document) => document.publications.length > 0) && <><h3>STATIC publications</h3><div className="integration-export-choices">{documents.flatMap((document) => document.publications.map((publication) => <label key={publication.id}><input type="checkbox" checked={selectedPublications.includes(publication.id)} onChange={(event) => setSelectedPublications((current) => event.target.checked ? [...current, publication.id] : current.filter((id) => id !== publication.id))} /><span>{document.title}</span><small>{publication.lifecycle_state.replace('_', ' ')}</small></label>))}</div></>}</>}</section><section className="content-section"><div className="section-heading"><div><h2>Retained bundles</h2><p>ZIP bytes are deterministic for the same selected content and can be unpacked into a Git working tree.</p></div></div>{exports.length === 0 ? <p className="empty-state">No sanitized bundles have been created.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.bundleTable')} tabIndex={0}><table><thead><tr><th>Created</th><th>Documents</th><th>STATIC</th><th>Size</th><th>Digest</th><th>Download</th></tr></thead><tbody>{exports.map((bundle) => <tr key={bundle.id}><td>{new Date(bundle.created_at).toLocaleString()}</td><td>{bundle.selection_manifest.documents.length}</td><td>{bundle.selection_manifest.publications.length}</td><td>{Math.ceil(bundle.byte_size / 1024)} KiB</td><td><code>{bundle.content_digest.slice(0, 16)}…</code></td><td>{client.gitExportDownloadUrl && <a className="secondary-button" href={client.gitExportDownloadUrl(workspace, bundle)}><Download size={14} />ZIP</a>}</td></tr>)}</tbody></table></div>}</section></>}
    {tab === 'webhooks' && <Webhooks workspace={workspace} client={client} embedded />}
  </>
}
