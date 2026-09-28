import { browserAuthClient } from '../auth/api'
import { browserDocumentsClient } from '../documentation/api'
import { useEffect, useState } from 'react'
import { Download, Pencil, Play, Plus, RefreshCw } from 'lucide-react'
import { useLocation, useSearchParams } from 'react-router'
import { translate } from '../i18n/localization'

import '../collections/collections.css'
import { CollectionPagination } from '../CollectionPagination'
import { QuickDrawer } from '../collections/QuickDrawer'
import type { DocumentsClient, DocumentRecord } from '../documentation/api'
import type { AuthClient } from '../auth/api'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { browserNetworksClient } from '../networks/api'
import type { NetBoxChoice, NetBoxObjectType, NetworkSubnet, NetworksClient } from '../networks/api'
import { browserInventoryClient } from '../inventory/api'
import type { InventoryClient, ModelChoice } from '../inventory/api'
import { RackPlaceChoice } from '../networks/RackPlaceChoice'
import { RecordSections } from '../records/RecordNavigation'
import type { WorkspaceContext } from '../workspaces/api'
import type { WebhooksClient } from './api'
import { Imports } from './Imports'
import type { ImportsClient } from './importsApi'
import { browserIntegrationsClient, IntegrationRequestError } from './providerApi'
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

const EMPTY_CONNECTION: IntegrationConnectionDraft = {
  provider: 'netbox', name: '', base_url: '', credentials: {}, sync_interval_minutes: 60,
}

export function Integrations({ workspace, client: webhookClient, documentsClient = browserDocumentsClient, providerClient = browserIntegrationsClient, networksClient = browserNetworksClient, inventoryClient = browserInventoryClient, importsClient, authClient = browserAuthClient }: {
  workspace: WorkspaceContext; client: WebhooksClient; documentsClient?: DocumentsClient; providerClient?: IntegrationsClient; networksClient?: NetworksClient; inventoryClient?: InventoryClient; importsClient?: ImportsClient; authClient?: Pick<AuthClient, 'reauthenticate'>
}) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const client = {
    ...webhookClient,
    gitExportDownloadUrl: (selectedWorkspace: WorkspaceContext, bundle: GitExportBundle) =>
      providerClient.gitExportDownloadUrl(selectedWorkspace, bundle),
  }
  const requestedSection = params.get('section')
  const section = INTEGRATION_SECTIONS.some((item) => item.id === requestedSection) ? requestedSection! : 'connections'
  const [connections, setConnections] = useState<IntegrationConnection[]>([])
  const [providers, setProviders] = useState<IntegrationProvider[]>([])
  const [jobs, setJobs] = useState<IntegrationJob[]>([])
  const [logs, setLogs] = useState<IntegrationLog[]>([])
  const [observations, setObservations] = useState<IntegrationObservation[]>([])
  const [observationPage, setObservationPage] = useState({ page: 1, page_size: 25, count: 0, has_more: false })
  const [conflicts, setConflicts] = useState<IntegrationConflict[]>([])
  const [conflictPage, setConflictPage] = useState({ page: 1, page_size: 25, count: 0, has_more: false })
  const [exports, setExports] = useState<GitExportBundle[]>([])
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [selectedPublications, setSelectedPublications] = useState<string[]>([])
  const [draft, setDraft] = useState(EMPTY_CONNECTION)
  const [showForm, setShowForm] = useState(false)
  const [loadState, setLoadState] = useState<{ section: string; value: 'loading' | 'ready' | 'error' }>({ section: 'connections', value: 'loading' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rotating, setRotating] = useState<{ connection: IntegrationConnection; credentials: Record<string, string> } | null>(null)
  const [editing, setEditing] = useState<{ connection: IntegrationConnection; name: string; base_url: string; sync_interval_minutes: number } | null>(null)
  const [adopting, setAdopting] = useState<IntegrationConflict | null>(null)
  const [reauthenticationAction, setReauthenticationAction] = useState<'create' | 'rotate' | null>(null)
  const [password, setPassword] = useState('')
  const [reload, setReload] = useState(0)
  const sourcePage = Math.max(1, Number(params.get('source_page')) || 1)
  const sourceSearch = params.get('source_search') ?? ''
  const sourceType = params.get('source_type') ?? ''
  const [sourceSearchDraft, setSourceSearchDraft] = useState(sourceSearch)
  const [sourceSearchParam, setSourceSearchParam] = useState(sourceSearch)
  const reviewPage = Math.max(1, Number(params.get('review_page')) || 1)
  const reviewSearch = params.get('review_search') ?? ''
  const reviewType = params.get('review_type') ?? ''
  const [reviewSearchDraft, setReviewSearchDraft] = useState(reviewSearch)
  const [reviewSearchParam, setReviewSearchParam] = useState(reviewSearch)
  const phase = loadState.section === section ? loadState.value : 'loading'
  const connectionDirty = showForm && JSON.stringify(draft) !== JSON.stringify(EMPTY_CONNECTION)
  const rotationDirty = Boolean(rotating && Object.values(rotating.credentials).some(Boolean))
  const editingDirty = Boolean(editing && (editing.name !== editing.connection.name || editing.base_url !== editing.connection.base_url || editing.sync_interval_minutes !== editing.connection.sync_interval_minutes))
  const exportDirty = selected.length > 0 || selectedPublications.length > 0
  useUnsavedChanges(connectionDirty || rotationDirty || editingDirty || exportDirty, saving, () => {
    setShowForm(false)
    setDraft(EMPTY_CONNECTION)
    setRotating(null)
    setEditing(null)
    setReauthenticationAction(null)
    setPassword('')
    setSelected([])
    setSelectedPublications([])
    setError(null)
  })

  if (sourceSearchParam !== sourceSearch) {
    setSourceSearchParam(sourceSearch)
    setSourceSearchDraft(sourceSearch)
  }
  if (reviewSearchParam !== reviewSearch) {
    setReviewSearchParam(reviewSearch)
    setReviewSearchDraft(reviewSearch)
  }

  useEffect(() => {
    if (!['connections', 'reconciliation', 'exports'].includes(section)) return
    const controller = new AbortController()
    const request = section === 'connections'
      ? Promise.all([
        providerClient.listProviders(workspace, controller.signal),
        providerClient.listConnections(workspace, controller.signal),
        providerClient.listJobs(workspace, controller.signal),
        providerClient.listLogs(workspace, controller.signal),
        providerClient.listObservations(workspace, { page: sourcePage, page_size: 25, q: sourceSearch, remote_type: sourceType }, controller.signal),
      ]).then(([nextProviders, nextConnections, nextJobs, nextLogs, nextObservations]) => {
        setProviders(nextProviders)
        setConnections(nextConnections)
        setJobs(nextJobs?.results ?? [])
        setLogs(nextLogs?.results ?? [])
        setObservations(nextObservations?.results ?? [])
        setObservationPage(nextObservations ?? { page: 1, page_size: 25, count: 0, has_more: false })
      })
      : section === 'reconciliation'
        ? Promise.all([
          providerClient.listProviders(workspace, controller.signal),
          providerClient.listConflicts(workspace, { page: reviewPage, page_size: 25, q: reviewSearch, remote_type: reviewType, status: 'open' }, controller.signal),
        ]).then(([nextProviders, nextConflicts]) => {
          setProviders(nextProviders)
          setConflicts(nextConflicts?.results ?? [])
          setConflictPage(nextConflicts ?? { page: 1, page_size: 25, count: 0, has_more: false })
        })
        : Promise.all([
          providerClient.listGitExports(workspace, controller.signal),
          documentsClient.list({ organizationId: workspace.kind === 'organization' ? workspace.id : undefined }, controller.signal),
        ]).then(([nextExports, nextDocuments]) => {
          setExports(nextExports)
          setDocuments(nextDocuments.results.filter((item) => !item.is_template))
        })
    request.then(() => {
      setLoadState({ section, value: 'ready' })
    }).catch(() => { if (!controller.signal.aborted) setLoadState({ section, value: 'error' }) })
    return () => controller.abort()
  }, [documentsClient, providerClient, reload, reviewPage, reviewSearch, reviewType, section, sourcePage, sourceSearch, sourceType, workspace])

  function updateSourceCollection(values: { page?: number; search?: string; type?: string }) {
    const next = new URLSearchParams(params)
    const page = values.page ?? sourcePage
    const search = values.search ?? sourceSearch
    const type = values.type ?? sourceType
    if (page > 1) next.set('source_page', String(page)); else next.delete('source_page')
    if (search) next.set('source_search', search); else next.delete('source_search')
    if (type) next.set('source_type', type); else next.delete('source_type')
    setParams(next)
  }

  function updateReviewCollection(values: { page?: number; search?: string; type?: string }) {
    const next = new URLSearchParams(params)
    const page = values.page ?? reviewPage
    const search = values.search ?? reviewSearch
    const type = values.type ?? reviewType
    if (page > 1) next.set('review_page', String(page)); else next.delete('review_page')
    if (search) next.set('review_search', search); else next.delete('review_search')
    if (type) next.set('review_type', type); else next.delete('review_type')
    setParams(next)
  }

  async function createConnection() {
    setSaving(true); setError(null)
    try {
      const connection = await providerClient.createConnection(workspace, draft)
      setConnections((current) => [...current, connection].sort((a, b) => a.name.localeCompare(b.name)))
      setDraft(EMPTY_CONNECTION); setShowForm(false)
    } catch (caught) {
      if (caught instanceof IntegrationRequestError && caught.code === 'recent_authentication_required') {
        setReauthenticationAction('create')
      } else {
        setError(translate('integrations.createFailed'))
      }
    }
    finally { setSaving(false) }
  }

  async function confirmReauthentication() {
    const action = reauthenticationAction
    const submittedPassword = password
    setPassword('')
    setSaving(true)
    setError(null)
    try {
      await authClient.reauthenticate(submittedPassword)
      setReauthenticationAction(null)
    } catch {
      setError(translate('integrations.reauthenticationFailed'))
      setSaving(false)
      return
    }
    setSaving(false)
    if (action === 'rotate' && rotating) await rotate(rotating.connection, rotating.credentials)
    else if (action === 'create') await createConnection()
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
      const updated = await providerClient.updateConnection(workspace, connection, { active: !connection.active, sync_interval_minutes: connection.sync_interval_minutes })
      setConnections((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch { setError(translate('integrations.changeFailed')) }
    finally { setSaving(false) }
  }

  async function saveConnectionEdit() {
    if (!editing) return
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.updateConnection(workspace, editing.connection, {
        name: editing.name,
        ...(providerFor(editing.connection.provider)?.base_url_editable ? { base_url: editing.base_url } : {}),
        active: editing.connection.active,
        sync_interval_minutes: editing.sync_interval_minutes,
      })
      setConnections((current) => current.map((item) => item.id === updated.id ? updated : item).sort((a, b) => a.name.localeCompare(b.name)))
      setEditing(null)
    } catch { setError(translate('integrations.changeFailed')) }
    finally { setSaving(false) }
  }

  async function rotate(connection: IntegrationConnection, credentials: Record<string, string>) {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.rotateConnection(workspace, connection, credentials)
      setConnections((current) => current.map((item) => item.id === updated.id ? updated : item))
      setRotating(null)
    } catch (caught) {
      if (caught instanceof IntegrationRequestError && caught.code === 'recent_authentication_required') {
        setReauthenticationAction('rotate')
      } else {
        setError(translate('integrations.rotateFailed'))
      }
    }
    finally { setSaving(false) }
  }

  function beginRotate(connection: IntegrationConnection) {
    const provider = providerFor(connection.provider)
    if (!provider) return
    setRotating({ connection, credentials: Object.fromEntries(provider.credential_fields.map((field) => [field.key, field.secret ? '' : connection.provider_details[field.key] ?? ''])) })
  }

  function beginEdit(connection: IntegrationConnection) {
    setShowForm(false)
    setEditing({ connection, name: connection.name, base_url: connection.base_url, sync_interval_minutes: connection.sync_interval_minutes })
  }

  async function reconcile(conflict: IntegrationConflict, resolution: 'keep_local' | 'accept_remote' | 'ignored') {
    setSaving(true); setError(null)
    try {
      const updated = await providerClient.resolveConflict(workspace, conflict, resolution)
      setConflicts((current) => current.filter((item) => item.id !== updated.id))
      setConflictPage((current) => ({ ...current, count: Math.max(0, current.count - 1) }))
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
    <header className="page-header"><div><h1 id="integrations-heading" tabIndex={-1}>Integrations</h1><p>{translate('integrations.intro', { workspace: workspace.name })}</p></div></header>
    <RecordSections current={section} sections={INTEGRATION_SECTIONS.map((item) => ({
      ...item,
      label: translate(item.label),
      href: item.id === 'connections' ? location.pathname : `${location.pathname}?section=${item.id}`,
    }))} />
    {error && <div className="form-message error" role="alert">{error}</div>}
    {phase === 'loading' && ['connections', 'reconciliation', 'exports'].includes(section) && <section className="content-section" role="status">Loading integration activity…</section>}
    {phase === 'error' && ['connections', 'reconciliation', 'exports'].includes(section) && <section className="content-section" role="alert"><h2>Integrations unavailable</h2><p>{translate('integrations.loadFailed')}</p><button className="secondary-button" type="button" onClick={() => { setLoadState({ section, value: 'loading' }); setReload((current) => current + 1) }}>{translate('collections.retry')}</button></section>}
    {phase === 'ready' && section === 'connections' && <>
      <section className="content-section"><div className="section-heading"><div><h2>Connections</h2><p>{translate('integrations.connectionsHelp')}</p></div><button className="primary-button" type="button" onClick={() => setShowForm(true)}><Plus size={16} />{translate('integrations.newConnection')}</button></div>
        {connections.length === 0 ? <p className="empty-state">No systems are connected to this workspace.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.connectionTable')} tabIndex={0}><table><thead><tr><th>Name</th><th>System</th><th>Status</th><th>Last completed</th><th>Next update</th><th>Needs review</th><th>Actions</th></tr></thead><tbody>{connections.map((connection) => <tr key={connection.id}><td><strong>{connection.name}</strong><br /><small>{connection.provider_details.tenant_id ? `Tenant ${connection.provider_details.tenant_id}` : connection.base_url}</small></td><td>{providerFor(connection.provider)?.label ?? connection.provider} · read-only<br /><small>{connection.provider_details.permission_status === 'verified' ? translate('integrations.permissionsVerified') : connection.provider_details.permission_status === 'not_validated' ? translate('integrations.permissionsUnchecked') : `Every ${connection.sync_interval_minutes} min`} · {connection.reconciliation_counts.observations ?? 0} records</small></td><td>{connection.active ? connection.health_status : 'paused'}{connection.last_error_code && <><br /><code>{connection.last_error_code}</code></>}</td><td>{connection.last_successful_sync_at ? new Date(connection.last_successful_sync_at).toLocaleString() : 'Not yet'}</td><td>{new Date(connection.next_sync_at).toLocaleString()}{connection.rate_limit_reset_at && <><br /><small>Rate limit resets {new Date(connection.rate_limit_reset_at).toLocaleString()}</small></>}</td><td>{connection.reconciliation_counts.review_required ?? 0}</td><td><div className="table-actions"><button className="secondary-button" type="button" disabled={saving || !connection.active} onClick={() => { void sync(connection) }}><Play size={14} />{translate('integrations.sync')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => beginEdit(connection)}><Pencil size={14} />{translate('common.edit')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => { void toggle(connection) }}>{connection.active ? 'Pause' : 'Resume'}</button><button className="secondary-button" type="button" disabled={saving} aria-label={`Replace the credential for ${connection.name}`} title={`Replace the credential for ${connection.name}`} onClick={() => beginRotate(connection)}><RefreshCw size={15} />{translate('integrations.rotateAction')}</button></div></td></tr>)}</tbody></table></div>}
        {rotating && providerFor(rotating.connection.provider) && <div className="archive-confirmation" role="alertdialog" aria-labelledby="replace-credential-heading" aria-describedby="replace-credential-help"><div><strong id="replace-credential-heading">{translate('integrations.rotateHeading', { name: rotating.connection.name })}</strong><p id="replace-credential-help">{translate('integrations.rotateHelp')}</p><div className="form-grid">{providerFor(rotating.connection.provider)?.credential_fields.map((field) => <label key={field.key}><span>{field.label}</span><input type={field.secret ? 'password' : 'text'} autoComplete={field.secret ? 'new-password' : 'off'} value={rotating.credentials[field.key] ?? ''} onChange={(event) => setRotating({ ...rotating, credentials: { ...rotating.credentials, [field.key]: event.target.value } })} /></label>)}</div></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving || Boolean(providerFor(rotating.connection.provider)?.credential_fields.some((field) => (rotating.credentials[field.key]?.length ?? 0) < field.minimum_length))} onClick={() => { void rotate(rotating.connection, rotating.credentials) }}>{translate('integrations.rotateAction')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setRotating(null)}>{translate('common.cancel')}</button></div></div>}
      </section>
      {editing && <section className="content-section integration-connection-form" aria-labelledby="edit-connection-heading"><form onSubmit={(event) => { event.preventDefault(); void saveConnectionEdit() }}><div className="section-heading"><div><h2 id="edit-connection-heading">{translate('integrations.editHeading', { name: editing.connection.name })}</h2><p>{translate('integrations.editHelp')}</p></div></div><div className="form-grid"><label><span>Name</span><input autoFocus required value={editing.name} maxLength={100} onChange={(event) => setEditing({ ...editing, name: event.target.value })} /></label>{providerFor(editing.connection.provider)?.base_url_editable && <label className="wide-field"><span>API base URL</span><input required type="url" value={editing.base_url} onChange={(event) => setEditing({ ...editing, base_url: event.target.value })} /></label>}<label><span>Sync interval (minutes)</span><input required type="number" min={providerFor(editing.connection.provider)?.minimum_sync_interval_minutes ?? 5} max={providerFor(editing.connection.provider)?.maximum_sync_interval_minutes ?? 10080} value={editing.sync_interval_minutes} onChange={(event) => setEditing({ ...editing, sync_interval_minutes: Number(event.target.value) })} /></label></div><div className="form-actions"><button className="primary-button" disabled={saving || !editing.name.trim() || Boolean(providerFor(editing.connection.provider)?.base_url_editable && !editing.base_url)}>{saving ? 'Saving…' : translate('integrations.saveChanges')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setEditing(null)}>{translate('common.cancel')}</button></div></form></section>}
      {showForm && <section className="content-section integration-connection-form" aria-labelledby="connection-form-heading"><form onSubmit={(event) => { event.preventDefault(); void createConnection() }}><div className="section-heading"><h2 id="connection-form-heading">{translate('integrations.newConnection')}</h2></div><div className="form-grid"><label><span>Name</span><input autoFocus value={draft.name} maxLength={100} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label><span>Provider</span><select value={draft.provider} onChange={(event) => { const provider = providers.find((item) => item.key === event.target.value); setDraft({ ...draft, provider: event.target.value, base_url: provider?.default_base_url ?? '', credentials: {}, sync_interval_minutes: provider?.minimum_sync_interval_minutes ?? 60 }) }}>{providers.map((provider) => <option key={provider.key} value={provider.key}>{provider.label}</option>)}</select></label>{selectedProvider?.base_url_editable && <label className="wide-field"><span>API base URL</span><input type="url" value={draft.base_url} placeholder="https://provider.example/api/" onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} /></label>}{selectedProvider?.credential_fields.map((field) => <label key={field.key} className={field.secret ? 'wide-field' : undefined}><span>{field.label}</span><input aria-label={field.label} type={field.input_type === 'password' ? 'password' : 'text'} autoComplete={field.secret ? 'new-password' : 'off'} value={draft.credentials[field.key] ?? ''} onChange={(event) => setDraft({ ...draft, credentials: { ...draft.credentials, [field.key]: event.target.value } })} />{field.help_text && <small>{field.help_text}</small>}</label>)}{selectedProvider?.setup_help_url && <p className="wide-field form-help">{translate('integrations.providerSetupHelp')} <a href={selectedProvider.setup_help_url} target="_blank" rel="noreferrer">{translate('integrations.providerSetupGuidance', { provider: selectedProvider.label })}</a></p>}<label><span>Sync interval (minutes)</span><input type="number" min={selectedProvider?.minimum_sync_interval_minutes ?? 5} max={selectedProvider?.maximum_sync_interval_minutes ?? 10080} value={draft.sync_interval_minutes} onChange={(event) => setDraft({ ...draft, sync_interval_minutes: Number(event.target.value) })} /></label></div><div className="form-actions"><button className="primary-button" disabled={saving || !draft.name || Boolean(selectedProvider?.base_url_editable && !draft.base_url) || Boolean(selectedProvider?.credential_fields.some((field) => (draft.credentials[field.key]?.length ?? 0) < field.minimum_length))}>{saving ? 'Saving…' : 'Save connection'}</button><button className="secondary-button" type="button" onClick={() => setShowForm(false)}>{translate('common.cancel')}</button></div></form></section>}
      {reauthenticationAction && <form className="content-section integration-reauth-form" onSubmit={(event) => { event.preventDefault(); void confirmReauthentication() }}>
        <div><h2>{translate('integrations.reauthenticationHeading')}</h2><p>{translate('integrations.reauthenticationHelp')}</p></div>
        <label><span>{translate('integrations.currentPassword')}</span><input autoFocus required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <div className="form-actions"><button type="submit" className="primary-button" disabled={saving}>{translate('integrations.confirmAndSave')}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => { setReauthenticationAction(null); setPassword('') }}>{translate('common.cancel')}</button></div>
      </form>}
      <section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.recentUpdates')}</h2><p>{translate('integrations.recentUpdatesHelp')}</p></div></div>{jobs.length === 0 ? <p className="empty-state">No updates have run.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.syncJobTable')} tabIndex={0}><table><thead><tr><th>Started</th><th>Connection</th><th>Started by</th><th>Status</th><th>Attempts</th><th>Result</th><th>Actions</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td>{new Date(job.created_at).toLocaleString()}</td><td>{job.connection_name}</td><td>{job.trigger}</td><td>{job.state.replace('_', ' ')}</td><td>{job.attempts}</td><td>{job.last_error_code || `${job.result_counts.observations ?? 0} records found`}</td><td>{(job.state === 'pending' || job.state === 'processing') ? <button className="secondary-button" type="button" disabled={saving} onClick={() => { void cancelJob(job) }}>{translate('common.cancel')}</button> : '—'}</td></tr>)}</tbody></table></div>}</section>
      <section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.sourceRecords')}</h2><p>{translate('integrations.sourceRecordsHelp')}</p></div></div>
        <form className="collection-toolbar" role="search" onSubmit={(event) => { event.preventDefault(); updateSourceCollection({ page: 1, search: sourceSearchDraft.trim() }) }}>
          <label><span>{translate('integrations.searchSourceRecords')}</span><input type="search" value={sourceSearchDraft} onChange={(event) => setSourceSearchDraft(event.target.value)} /></label>
          <label><span>{translate('integrations.sourceType')}</span><select value={sourceType} onChange={(event) => updateSourceCollection({ page: 1, type: event.target.value })}><option value="">{translate('integrations.allSourceTypes')}</option>{Array.from(new Set(providers.flatMap((provider) => provider.object_types))).sort().map((type) => <option key={type} value={type}>{type.replaceAll('_', ' ')}</option>)}</select></label>
          <button className="secondary-button" type="submit">{translate('collections.searchAction')}</button>
          {(sourceSearch || sourceType) && <button className="row-action" type="button" onClick={() => { setSourceSearchDraft(''); updateSourceCollection({ page: 1, search: '', type: '' }) }}>{translate('collections.clearFilters')}</button>}
        </form>
        {observations.length === 0 ? <p className="empty-state">{sourceSearch || sourceType ? translate('integrations.noFilteredSourceRecords') : translate('integrations.noSourceRecords')}</p> : <><div className="table-scroll" role="group" aria-label={translate('integrations.observationTable')} tabIndex={0}><table><thead><tr><th>Source record</th><th>Type</th><th>Connection</th><th>Updated at source</th><th>TekDocs record</th><th>Status</th></tr></thead><tbody>{observations.map((observation) => { const conflict = observation.open_conflict; const canAdopt = conflict?.difference === 'unmatched' && conflict.connection_provider === 'netbox'; return <tr key={observation.id}><td><strong>{Object.values(observation.safe_projection).filter((value) => value !== null && value !== '').slice(0, 3).map(String).join(' · ') || observation.remote_id}</strong></td><td>{observation.remote_type.replaceAll('_', ' ')}</td><td>{observation.connection_name}</td><td>{observation.stale ? translate('integrations.staleSource', { date: new Date(observation.source_timestamp ?? observation.observed_at).toLocaleString() }) : new Date(observation.source_timestamp ?? observation.observed_at).toLocaleString()}</td><td>{canAdopt ? <button className="secondary-button" type="button" onClick={() => setAdopting(conflict)}>{translate('integrations.linkToTekDocs')}</button> : observation.linked_local_entity_name || conflict?.local_entity_name || observation.linked_local_entity_id || conflict?.local_entity_id || translate('integrations.notLinked')}</td><td>{conflict ? translate('integrations.needsReview') : observation.accepted ? translate('integrations.accepted') : observation.linked_local_entity_id ? translate('integrations.linkedObservation') : translate('integrations.observedOnly')}</td></tr> })}</tbody></table></div><CollectionPagination label={translate('integrations.sourceRecords')} page={observationPage.page} pageSize={observationPage.page_size} count={observationPage.count} hasMore={observationPage.has_more} onPageChange={(page) => updateSourceCollection({ page })} /></>}</section>
      <section className="content-section"><div className="section-heading"><div><h2>Operational log</h2><p>Thirty-day structured events contain allowlisted codes and numeric metrics—not provider messages or response bodies.</p></div></div>{logs.length === 0 ? <p className="empty-state">No provider events have been recorded.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.logTable')} tabIndex={0}><table><thead><tr><th>Time</th><th>Connection</th><th>Level</th><th>Code</th><th>Metrics</th></tr></thead><tbody>{logs.map((event) => <tr key={event.id}><td>{new Date(event.occurred_at).toLocaleString()}</td><td>{event.connection_name}</td><td>{event.level}</td><td><code>{event.code}</code></td><td>{Object.entries(event.metrics).map(([key, value]) => `${key}: ${value}`).join(', ') || '—'}</td></tr>)}</tbody></table></div>}</section>
    </>}
    {section === 'imports' && <Imports workspace={workspace} client={importsClient} />}
    {phase === 'ready' && section === 'reconciliation' && <section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.reviewDifferences')}</h2><p>{translate('integrations.reviewDifferencesHelp')}</p></div></div>
      <form className="collection-toolbar" role="search" onSubmit={(event) => { event.preventDefault(); updateReviewCollection({ page: 1, search: reviewSearchDraft.trim() }) }}>
        <label><span>{translate('integrations.searchReviewQueue')}</span><input type="search" value={reviewSearchDraft} onChange={(event) => setReviewSearchDraft(event.target.value)} /></label>
        <label><span>{translate('integrations.sourceType')}</span><select value={reviewType} onChange={(event) => updateReviewCollection({ page: 1, type: event.target.value })}><option value="">{translate('integrations.allSourceTypes')}</option>{Array.from(new Set(providers.flatMap((provider) => provider.object_types))).sort().map((type) => <option key={type} value={type}>{type.replaceAll('_', ' ')}</option>)}</select></label>
        <button className="secondary-button" type="submit">{translate('collections.searchAction')}</button>
        {(reviewSearch || reviewType) && <button className="row-action" type="button" onClick={() => { setReviewSearchDraft(''); updateReviewCollection({ page: 1, search: '', type: '' }) }}>{translate('collections.clearFilters')}</button>}
      </form>
      {conflicts.length === 0 ? <p className="empty-state">{reviewSearch || reviewType ? translate('integrations.noFilteredDifferences') : translate('integrations.noDifferences')}</p> : <><div className="table-scroll" role="group" aria-label={translate('integrations.reconciliationTable')} tabIndex={0}><table><thead><tr><th>Source record</th><th>Connection</th><th>Source details</th><th>Change</th><th>TekDocs record</th><th>Other actions</th></tr></thead><tbody>{conflicts.map((conflict) => { const canAdopt = conflict.difference === 'unmatched' && conflict.connection_provider === 'netbox'; return <tr key={conflict.id}><td><code>{conflict.remote_type}:{conflict.remote_id}</code></td><td>{conflict.connection_name}</td><td>{Object.entries(conflict.provider_values ?? {}).filter(([, value]) => value !== null && value !== '').slice(0, 4).map(([key, value]) => `${key}: ${String(value)}`).join(' · ') || 'No saved details'}</td><td>{conflict.difference}</td><td>{canAdopt ? <button className="primary-button" type="button" disabled={saving} onClick={() => setAdopting(conflict)}>{translate('integrations.linkToTekDocs')}</button> : conflict.local_entity_name || conflict.local_entity_id || 'Not matched'}</td><td><div className="table-actions">{!canAdopt && <><button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'keep_local') }}>{translate('integrations.keepFlagged')}</button>{conflict.local_entity_id && <button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'accept_remote') }}>{translate('integrations.acknowledgeChange')}</button>}</>}<button className="secondary-button" type="button" disabled={saving} onClick={() => { void reconcile(conflict, 'ignored') }}>{translate('integrations.dismissDifference')}</button></div></td></tr> })}</tbody></table></div><CollectionPagination label={translate('integrations.reviewDifferences')} page={conflictPage.page} pageSize={conflictPage.page_size} count={conflictPage.count} hasMore={conflictPage.has_more} onPageChange={(page) => updateReviewCollection({ page })} /></>}</section>}
    {phase === 'ready' && section === 'exports' && <><section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.createExport')}</h2><p>{translate('integrations.createExportHelp')}</p></div><button className="primary-button" type="button" disabled={saving || (selected.length === 0 && selectedPublications.length === 0)} onClick={() => { void createExport() }}>{translate('integrations.createBundle')}</button></div>{documents.length === 0 ? <p className="empty-state">No documents are available in this workspace.</p> : <><h3>Editable documents</h3><div className="integration-export-choices">{documents.map((document) => <label key={document.id}><input type="checkbox" checked={selected.includes(document.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, document.id] : current.filter((id) => id !== document.id))} /><span>{document.title}</span><small>{document.category}</small></label>)}</div>{documents.some((document) => document.publications.length > 0) && <><h3>Published copies</h3><div className="integration-export-choices">{documents.flatMap((document) => document.publications.map((publication) => <label key={publication.id}><input type="checkbox" checked={selectedPublications.includes(publication.id)} onChange={(event) => setSelectedPublications((current) => event.target.checked ? [...current, publication.id] : current.filter((id) => id !== publication.id))} /><span>{document.title}</span><small>{publication.lifecycle_state.replace('_', ' ')}</small></label>))}</div></>}</>}</section><section className="content-section"><div className="section-heading"><div><h2>{translate('integrations.savedExports')}</h2><p>{translate('integrations.savedExportsHelp')}</p></div></div>{exports.length === 0 ? <p className="empty-state">No exports have been created.</p> : <div className="table-scroll" role="group" aria-label={translate('integrations.bundleTable')} tabIndex={0}><table><thead><tr><th>Created</th><th>Documents</th><th>Published copies</th><th>Size</th><th>File ID</th><th>Download</th></tr></thead><tbody>{exports.map((bundle) => <tr key={bundle.id}><td>{new Date(bundle.created_at).toLocaleString()}</td><td>{bundle.selection_manifest.documents.length}</td><td>{bundle.selection_manifest.publications.length}</td><td>{Math.ceil(bundle.byte_size / 1024)} KiB</td><td><code>{bundle.content_digest.slice(0, 16)}…</code></td><td>{client.gitExportDownloadUrl && <a className="secondary-button" href={client.gitExportDownloadUrl(workspace, bundle)}><Download size={14} />ZIP</a>}</td></tr>)}</tbody></table></div>}</section></>}
    {section === 'webhooks' && <Webhooks workspace={workspace} client={client} embedded />}
    {adopting && <NetBoxAdoptionDrawer workspace={workspace} conflict={adopting} providerClient={providerClient} networksClient={networksClient} inventoryClient={inventoryClient} onClose={() => setAdopting(null)} onSaved={(updated) => { setConflicts((current) => current.filter((item) => item.id !== updated.id)); setConflictPage((current) => ({ ...current, count: Math.max(0, current.count - 1) })); setAdopting(null); if (section === 'connections') setReload((value) => value + 1) }} />}
  </>
}

const NETBOX_TYPES = new Set<NetBoxObjectType>(['dcim.rack', 'dcim.device', 'dcim.macaddress', 'ipam.vlan', 'ipam.prefix', 'ipam.ipaddress'])

function NetBoxAdoptionDrawer({ workspace, conflict, providerClient, networksClient, inventoryClient, onClose, onSaved }: {
  workspace: WorkspaceContext; conflict: IntegrationConflict; providerClient: IntegrationsClient; networksClient: NetworksClient; inventoryClient: InventoryClient
  onClose: () => void; onSaved: (conflict: IntegrationConflict) => void
}) {
  const location = useLocation()
  const objectType = NETBOX_TYPES.has(conflict.remote_type as NetBoxObjectType) ? conflict.remote_type as NetBoxObjectType : null
  const projectedName = conflict.provider_values?.name ?? conflict.provider_values?.display
  const sourceName = typeof projectedName === 'string' || typeof projectedName === 'number'
    ? String(projectedName)
    : `${conflict.remote_type} ${conflict.remote_id}`
  const [mode, setMode] = useState<'link' | 'create'>('link')
  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [page, setPage] = useState(1)
  const [choices, setChoices] = useState<{ results: NetBoxChoice[]; selected: NetBoxChoice | null; count: number; has_more: boolean } | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [name, setName] = useState(sourceName)
  const [site, setSite] = useState<{ id: string; name: string } | null>(null)
  const [place, setPlace] = useState<{ id: string; name: string } | null>(null)
  const [unitCount, setUnitCount] = useState(42)
  const [status, setStatus] = useState<'planned' | 'active' | 'retired'>('active')
  const [modelQuery, setModelQuery] = useState('')
  const [submittedModelQuery, setSubmittedModelQuery] = useState('')
  const [models, setModels] = useState<ModelChoice[] | null>(null)
  const [selectedModelId, setSelectedModelId] = useState('')
  const [vlanId, setVlanId] = useState('')
  const projectedPrefix = conflict.provider_values?.prefix
  const sourceCidr = typeof projectedPrefix === 'string' ? projectedPrefix : conflict.remote_type === 'ipam.prefix' ? sourceName : ''
  const [cidr, setCidr] = useState(sourceCidr)
  const projectedAddress = conflict.provider_values?.address
  const sourceAddressWithMask = typeof projectedAddress === 'string' ? projectedAddress : conflict.remote_type === 'ipam.ipaddress' ? sourceName : ''
  const sourceAddress = sourceAddressWithMask.split('/')[0]
  const [address, setAddress] = useState(sourceAddress)
  const [subnetQuery, setSubnetQuery] = useState('')
  const [submittedSubnetQuery, setSubmittedSubnetQuery] = useState('')
  const [subnetPage, setSubnetPage] = useState(1)
  const [subnetChoices, setSubnetChoices] = useState<{ results: Omit<NetworkSubnet, 'description'>[]; count: number; has_more: boolean } | null>(null)
  const [selectedSubnet, setSelectedSubnet] = useState<Omit<NetworkSubnet, 'description'> | null>(null)
  const [ipStatus, setIpStatus] = useState<'active' | 'reserved' | 'dhcp' | 'deprecated'>('active')
  const [dnsName, setDnsName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = Boolean(selectedId || selectedModelId || vlanId || cidr !== sourceCidr || address !== sourceAddress || selectedSubnet || ipStatus !== 'active' || dnsName || description || site || place || name !== sourceName || unitCount !== 42 || status !== 'active')
  const attempt = useUnsavedChanges(dirty, busy, () => {}, true)

  useEffect(() => {
    if (mode !== 'link' || !objectType) return
    const controller = new AbortController()
    networksClient.netBoxChoiceCollection(workspace, { q: submittedQuery, object_type: objectType, selected_id: selectedId || undefined, page, page_size: 25 }, controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setChoices(value); setError('') } })
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : translate('integrations.adoptFailed')) })
    return () => controller.abort()
  }, [mode, networksClient, objectType, page, selectedId, submittedQuery, workspace])

  useEffect(() => {
    if (mode !== 'create' || conflict.remote_type !== 'dcim.device') return
    const controller = new AbortController()
    inventoryClient.listModelChoices(workspace, submittedModelQuery, controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setModels(value.results.filter((model) => model.kind === 'hardware')); setError('') } })
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : translate('integrations.modelLoadFailed')) })
    return () => controller.abort()
  }, [conflict.remote_type, inventoryClient, mode, submittedModelQuery, workspace])

  useEffect(() => {
    if (mode !== 'create' || conflict.remote_type !== 'ipam.ipaddress') return
    const controller = new AbortController()
    networksClient.subnetCollection(workspace, { q: submittedSubnetQuery, page: subnetPage, page_size: 25, ordering: 'name' }, controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setSubnetChoices(value); setError('') } })
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : translate('integrations.subnetLoadFailed')) })
    return () => controller.abort()
  }, [conflict.remote_type, mode, networksClient, submittedSubnetQuery, subnetPage, workspace])

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!objectType) return
    setBusy(true); setError('')
    try {
      const updated = mode === 'link'
        ? await providerClient.adoptNetBoxConflict(workspace, conflict, { entity_id: selectedId })
        : conflict.remote_type === 'dcim.device'
          ? await providerClient.adoptNetBoxConflict(workspace, conflict, { asset: { name: name.trim(), model_id: selectedModelId } })
          : conflict.remote_type === 'ipam.vlan'
            ? await providerClient.adoptNetBoxConflict(workspace, conflict, { vlan: { name: name.trim(), vlan_id: Number(vlanId), description: description.trim() } })
            : conflict.remote_type === 'ipam.prefix'
              ? await providerClient.adoptNetBoxConflict(workspace, conflict, { prefix: { name: name.trim(), cidr: cidr.trim(), description: description.trim() } })
            : conflict.remote_type === 'ipam.ipaddress'
              ? await providerClient.adoptNetBoxConflict(workspace, conflict, { ip_address: { address: address.trim(), subnet_id: selectedSubnet?.id ?? '', status: ipStatus, dns_name: dnsName.trim(), description: description.trim() } })
            : await providerClient.adoptNetBoxConflict(workspace, conflict, { rack: { name: name.trim(), site_id: site?.id ?? '', location_id: place?.id ?? null, unit_count: unitCount, status } })
      onSaved(updated)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('integrations.adoptFailed'))
    } finally { setBusy(false) }
  }

  const selected = choices?.selected ?? choices?.results.find((choice) => choice.id === selectedId) ?? null
  const canCreate = conflict.remote_type === 'dcim.rack' || conflict.remote_type === 'dcim.device' || conflict.remote_type === 'ipam.vlan' || conflict.remote_type === 'ipam.prefix' || conflict.remote_type === 'ipam.ipaddress'
  const createDisabled = conflict.remote_type === 'dcim.device'
    ? !name.trim() || !selectedModelId
    : conflict.remote_type === 'ipam.vlan'
      ? !name.trim() || !vlanId || Number(vlanId) < 1 || Number(vlanId) > 4094
      : conflict.remote_type === 'ipam.prefix'
        ? !name.trim() || !cidr.trim()
      : conflict.remote_type === 'ipam.ipaddress'
        ? !address.trim() || !selectedSubnet
      : !name.trim() || !site || Number.isNaN(unitCount)
  const linkLabel = conflict.remote_type === 'dcim.device'
    ? 'integrations.linkExistingAsset'
    : conflict.remote_type === 'ipam.vlan'
      ? 'integrations.linkExistingVLAN'
      : conflict.remote_type === 'ipam.prefix'
        ? 'integrations.linkExistingPrefix'
      : conflict.remote_type === 'ipam.ipaddress'
        ? 'integrations.linkExistingIPAddress'
      : 'integrations.linkExisting'
  const createLabel = conflict.remote_type === 'dcim.device'
    ? 'integrations.createAsset'
    : conflict.remote_type === 'ipam.vlan'
      ? 'integrations.createVLAN'
      : conflict.remote_type === 'ipam.prefix'
        ? 'integrations.createPrefix'
      : conflict.remote_type === 'ipam.ipaddress'
        ? 'integrations.createIPAddress'
      : 'integrations.createRack'
  const saveLabel = conflict.remote_type === 'dcim.device'
    ? 'integrations.createAndLinkAsset'
    : conflict.remote_type === 'ipam.vlan'
      ? 'integrations.createAndLinkVLAN'
      : conflict.remote_type === 'ipam.prefix'
        ? 'integrations.createAndLinkPrefix'
      : conflict.remote_type === 'ipam.ipaddress'
        ? 'integrations.createAndLinkIPAddress'
      : 'integrations.createAndLink'
  return <QuickDrawer title={translate('integrations.adoptHeading')} returnLabel={translate('integrations.returnToReview')} returnHref={`${location.pathname}${location.search}`} returnFocusId="integrations-heading" onClose={() => attempt(onClose)}>
    <form onSubmit={(event) => void save(event)}>
      <p>{translate('integrations.adoptIntro', { source: sourceName, type: conflict.remote_type })}</p>
      <p className="field-help">{translate('integrations.localSearchHelp')}</p>
      {error && <p role="alert">{error}</p>}
      {objectType ? <>
        {canCreate && <fieldset><legend>{translate('integrations.adoptMethod')}</legend><label className="collection-choice"><input type="radio" name="adopt-method" checked={mode === 'link'} onChange={() => setMode('link')} /> {translate(linkLabel)}</label><label className="collection-choice"><input type="radio" name="adopt-method" checked={mode === 'create'} onChange={() => { setMode('create'); setSelectedId('') }} /> {translate(createLabel)}</label></fieldset>}
        {mode === 'link' ? <>
          <label>{translate('integrations.searchLocalRecords')}<span className="collection-search"><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /><button className="secondary-button" type="button" onClick={() => { setSubmittedQuery(query.trim()); setPage(1) }}>{translate('collections.searchAction')}</button></span></label>
          {choices === null ? <p role="status">{translate('collections.loading')}</p> : choices.results.length === 0 ? <p className="empty-state">{translate('integrations.noLocalMatches')}</p> : <fieldset><legend>{translate('integrations.chooseLocalRecord')}</legend>{choices.results.map((choice) => <label key={choice.id} className="collection-choice"><input type="radio" name="local-record" checked={selectedId === choice.id} onChange={() => setSelectedId(choice.id)} /> <span><strong>{choice.name}</strong></span></label>)}<CollectionPagination label={translate('integrations.chooseLocalRecord')} page={page} pageSize={25} count={choices.count} hasMore={choices.has_more} onPageChange={setPage} /></fieldset>}
          {selected && <p>{translate('integrations.selectedLocalRecord', { name: selected.name })}</p>}
        </> : conflict.remote_type === 'dcim.device' ? <>
          <label>{translate('integrations.assetName')}<input required maxLength={240} value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>{translate('integrations.searchHardwareModels')}<span className="collection-search"><input type="search" value={modelQuery} onChange={(event) => setModelQuery(event.target.value)} /><button className="secondary-button" type="button" onClick={() => setSubmittedModelQuery(modelQuery.trim())}>{translate('collections.searchAction')}</button></span></label>
          {models === null ? <p role="status">{translate('collections.loading')}</p> : models.length === 0 ? <p className="empty-state">{translate('integrations.noHardwareModels')}</p> : <fieldset><legend>{translate('integrations.chooseHardwareModel')}</legend>{models.map((model) => <label key={model.id} className="collection-choice"><input type="radio" name="hardware-model" checked={selectedModelId === model.id} onChange={() => setSelectedModelId(model.id)} /> <span><strong>{model.supplier_name} · {model.product_name} · {model.name}</strong><small>{model.model_number}</small></span></label>)}</fieldset>}
        </> : conflict.remote_type === 'ipam.vlan' ? <>
          <label>{translate('integrations.vlanName')}<input required maxLength={240} value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>{translate('integrations.vlanId')}<input required type="number" min={1} max={4094} value={vlanId} onChange={(event) => setVlanId(event.target.value)} /></label>
          <label>{translate('integrations.vlanDescription')}<textarea maxLength={4000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <p className="field-help">{translate('integrations.vlanIdHelp')}</p>
        </> : conflict.remote_type === 'ipam.prefix' ? <>
          <label>{translate('integrations.prefixName')}<input required maxLength={240} value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>{translate('integrations.prefixCidr')}<input required maxLength={49} value={cidr} onChange={(event) => setCidr(event.target.value)} /></label>
          <label>{translate('integrations.prefixDescription')}<textarea maxLength={4000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <p className="field-help">{translate('integrations.prefixHelp')}</p>
        </> : conflict.remote_type === 'ipam.ipaddress' ? <>
          <label>{translate('integrations.ipAddress')}<input required maxLength={45} value={address} onChange={(event) => setAddress(event.target.value)} /></label>
          <label>{translate('integrations.searchSubnets')}<span className="collection-search"><input type="search" value={subnetQuery} onChange={(event) => setSubnetQuery(event.target.value)} /><button className="secondary-button" type="button" onClick={() => { setSubmittedSubnetQuery(subnetQuery.trim()); setSubnetPage(1) }}>{translate('collections.searchAction')}</button></span></label>
          {subnetChoices === null ? <p role="status">{translate('collections.loading')}</p> : subnetChoices.results.length === 0 ? <p className="empty-state">{translate('integrations.noSubnets')}</p> : <fieldset><legend>{translate('integrations.chooseSubnet')}</legend>{subnetChoices.results.map((subnet) => <label key={subnet.id} className="collection-choice"><input type="radio" name="ip-subnet" checked={selectedSubnet?.id === subnet.id} onChange={() => setSelectedSubnet(subnet)} /> <span><strong>{subnet.name}</strong><small>{subnet.cidr}</small></span></label>)}<CollectionPagination label={translate('integrations.chooseSubnet')} page={subnetPage} pageSize={25} count={subnetChoices.count} hasMore={subnetChoices.has_more} onPageChange={setSubnetPage} /></fieldset>}
          {selectedSubnet && <p>{translate('integrations.selectedSubnet', { name: selectedSubnet.name, cidr: selectedSubnet.cidr })}</p>}
          <label>{translate('integrations.ipStatus')}<select value={ipStatus} onChange={(event) => setIpStatus(event.target.value as typeof ipStatus)}><option value="active">{translate('integrations.ipStatusActive')}</option><option value="reserved">{translate('integrations.ipStatusReserved')}</option><option value="dhcp">{translate('integrations.ipStatusDhcp')}</option><option value="deprecated">{translate('integrations.ipStatusDeprecated')}</option></select></label>
          <label>{translate('integrations.ipDnsName')}<input maxLength={253} value={dnsName} onChange={(event) => setDnsName(event.target.value)} /></label>
          <label>{translate('integrations.ipDescription')}<textarea maxLength={4000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <p className="field-help">{translate('integrations.ipAddressHelp')}</p>
        </> : <>
          <label>{translate('integrations.rackName')}<input required maxLength={240} value={name} onChange={(event) => setName(event.target.value)} /></label>
          <div className="field-grid"><label>{translate('integrations.rackUnits')}<input required type="number" min={1} max={100} value={unitCount} onChange={(event) => setUnitCount(event.target.valueAsNumber)} /></label><label>{translate('collections.status')}<select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}><option value="planned">{translate('integrations.statusPlanned')}</option><option value="active">{translate('integrations.statusActive')}</option><option value="retired">{translate('integrations.statusRetired')}</option></select></label></div>
          <RackPlaceChoice kind="site" selected={site} workspace={workspace} client={networksClient} onChange={(value) => { setSite(value); setPlace(null) }} />
          {site && <RackPlaceChoice kind="location" siteId={site.id} selected={place} workspace={workspace} client={networksClient} onChange={setPlace} />}
          {!site && <p className="field-help">{translate('integrations.rackSiteRequired')}</p>}
        </>}
        <div className="form-actions"><button className="primary-button" disabled={busy || (mode === 'link' ? !selectedId : createDisabled)}>{busy ? translate('common.saving') : mode === 'link' ? translate('integrations.linkRecord') : translate(saveLabel)}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => attempt(onClose)}>{translate('common.cancel')}</button></div>
      </> : <p role="alert">{translate('integrations.unsupportedNetBoxType')}</p>}
    </form>
  </QuickDrawer>
}

const INTEGRATION_SECTIONS = [
  { id: 'connections', label: 'integrations.sections.connections' },
  { id: 'imports', label: 'integrations.sections.imports' },
  { id: 'reconciliation', label: 'integrations.sections.reconciliation' },
  { id: 'exports', label: 'integrations.sections.exports' },
  { id: 'webhooks', label: 'integrations.sections.webhooks' },
] as const
