import { useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { Archive, Plus, Search } from 'lucide-react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges, NavigationGuardContext } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import { browserAssetCollectionClient } from './api'
import type { AssetCollectionClient, AssetCollectionQuery, AssetCollectionResult, ClientAsset, InventoryClient, ModelChoice } from './api'
import { AssetSiteFilter } from './AssetSiteFilter'
import { useAssetSiteLabel } from './useAssetSiteLabel'
import { AssetCsvTransfer } from './AssetCsvTransfer'
import { AssetRecord } from './AssetRecord'
import { CollectionTable } from '../collections/CollectionTable'
import { ColumnChooser } from '../collections/ColumnChooser'
import { QuickDrawer } from '../collections/QuickDrawer'
import { assetColumns, browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import '../collections/collections.css'

const filterKeys = ['kind', 'status', 'assigned', 'warranty', 'site'] as const
const labels = Object.fromEntries(assetColumns.map((column) => [column, translate(`collections.${column}`)]))
const emptyResult: AssetCollectionResult = { results: [], page: 1, page_size: 25, count: 0, has_more: false, can_manage: false, can_view_relationships: false, can_create_relationships: false, can_archive_relationships: false }

export function Assets({ workspace, client, collectionClient = browserAssetCollectionClient, preferenceClient = browserCollectionPreferences }: {
  workspace: WorkspaceContext; client: InventoryClient; collectionClient?: AssetCollectionClient; preferenceClient?: typeof browserCollectionPreferences
}) {
  const [params, setParams] = useSearchParams()
  const guarded = useContext(NavigationGuardContext)!.isGuarded
  const pendingPreferenceReset = useRef(false)

  const location = useLocation()
  const navigate = useNavigate()
  const navigationState = location.state as { assetListPosition?: { y: number; focus: string | null } } | null
  const siteLabel = useAssetSiteLabel(workspace, params.get('site') ?? '')
  const recordId = params.get('record')
  const previewId = recordId ? null : params.get('preview')
  const activeId = recordId ?? previewId
  const ownerLabel = workspace.kind === 'msp' ? 'MSP' : 'client'
  const [preferences, setPreferences] = useState<CollectionPreferences | null>(null)
  useEffect(() => {
    if (!pendingPreferenceReset.current || guarded) return
    // React Router installs its blocker predicate in a parent effect. Finish the
    // URL reset after that commit, not from this earlier child effect.
    const frame = requestAnimationFrame(() => {
      pendingPreferenceReset.current = false
      const next = new URLSearchParams(params); next.delete('page_size'); next.delete('page')
      void setParams(next)
    })
    return () => cancelAnimationFrame(frame)
  }, [guarded, params, setParams, preferences])

  const [result, setResult] = useState<AssetCollectionResult>(emptyResult)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [detail, setDetail] = useState<{ owner: string; asset: ClientAsset } | null>(null)
  const [loadedQuery, setLoadedQuery] = useState('')
  const [createdId, setCreatedId] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [creating, setCreating] = useState(false)
  const [modelQuery, setModelQuery] = useState('')
  const [modelChoices, setModelChoices] = useState<ModelChoice[]>([])
  const [modelId, setModelId] = useState('')
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [bulkAction, setBulkAction] = useState<'set_hardware_state' | 'archive'>('set_hardware_state')
  const [bulkState, setBulkState] = useState<NonNullable<ClientAsset['hardware']>['lifecycle_state']>('in_stock')
  const [confirmingArchive, setConfirmingArchive] = useState(false)
  const [selection, setSelection] = useState({ key: '', ids: new Set<string>() })
  const [notice, setNotice] = useState('')
  const changedId = useRef<string | null>(null)
  const listPosition = useRef<{ y: number; focus: string | null }>({ y: 0, focus: null })
  const wasRecord = useRef(false)
  const pageSize = [25, 50, 100].includes(Number(params.get('page_size'))) ? Number(params.get('page_size')) as 25 | 50 | 100 : preferences?.page_size ?? 25
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1)
  const queryText = JSON.stringify({ page, page_size: pageSize, search: params.get('search') ?? '', ordering: params.get('ordering') ?? 'name', ...Object.fromEntries(filterKeys.filter((key) => params.has(key)).map((key) => [key, key === 'assigned' ? params.get(key) === 'true' : params.get(key)])) })
  const query = useMemo(() => JSON.parse(queryText) as AssetCollectionQuery, [queryText])
  const selectionKey = `${workspace.id}:${queryText}`
  if (selection.key !== selectionKey) { setSelection({ key: selectionKey, ids: new Set() }); setConfirmingArchive(false) }
  const selectedIds = selection.key === selectionKey ? selection.ids : new Set<string>()
  function setSelectedIds(update: Set<string> | ((current: Set<string>) => Set<string>)) { setSelection((current) => ({ key: selectionKey, ids: typeof update === 'function' ? update(current.ids) : update })) }
  const listReady = phase === 'ready' && loadedQuery === selectionKey
  const canManage = listReady && result.can_manage
  const relationshipAccess = { view: listReady && result.can_view_relationships, create: listReady && result.can_create_relationships, archive: listReady && result.can_archive_relationships }
  const choice = modelChoices.find((item) => item.id === modelId)
  const attempt = useUnsavedChanges(creating && Boolean(name || modelId), saving, () => { setCreating(false); setName(''); setModelId(''); setModelQuery('') }, creating)

  useEffect(() => {
    const controller = new AbortController()
    preferenceClient.load(workspace, 'assets', assetColumns, controller.signal).then((value) => { if (!controller.signal.aborted) setPreferences(value) }).catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(assetColumns)) })
    return () => controller.abort()
  }, [workspace, preferenceClient])
  useEffect(() => {
    if (!preferences) return
    const controller = new AbortController()
    collectionClient.list(workspace, query, controller.signal).then((value) => {
      if (controller.signal.aborted) return
      setResult(value); setLoadedQuery(selectionKey); setPhase('ready')
      if (changedId.current && !value.results.some((row) => row.id === changedId.current)) setNotice(translate('collections.updatedOutside'))
      changedId.current = null
    }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [workspace, collectionClient, query, reload, preferences, selectionKey])
  useEffect(() => {
    const controller = new AbortController()
    if (activeId) {
      collectionClient.detail(workspace, activeId, controller.signal).then((asset) => { if (!controller.signal.aborted) { setDetail({ owner: workspace.id, asset }); setDetailError(null) } }).catch(() => { if (!controller.signal.aborted) setDetailError(`${workspace.id}:${activeId}`) })
    }
    return () => controller.abort()
  }, [workspace, collectionClient, activeId])
  useEffect(() => {
    if (recordId) { wasRecord.current = true; window.scrollTo({ top: 0 }) }
    else if (wasRecord.current && phase === 'ready') {
      wasRecord.current = false
      const position = navigationState?.assetListPosition ?? listPosition.current
      window.scrollTo({ top: Number.isFinite(position.y) ? position.y : 0 })
      const target = typeof position.focus === 'string' ? document.getElementById(position.focus) : null
      ;(target ?? document.getElementById('assets-collection-heading'))?.focus({ preventScroll: true })
    }
  }, [recordId, phase, navigationState])
  useEffect(() => {
    if (!creating) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => { client.listModelChoices(workspace, modelQuery, controller.signal).then((value) => { if (!controller.signal.aborted) setModelChoices(value.results) }).catch(() => { if (!controller.signal.aborted) setError(translate('assets.modelsLoadFailed')) }) }, 150)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [creating, client, workspace, modelQuery])

  function href(id: string | null, section = 'overview', preview = false) {
    const next = new URLSearchParams(params)
    next.delete('record'); next.delete('preview'); next.delete('section')
    if (id !== activeId) next.delete('history_page')
    if (id) { next.set(preview ? 'preview' : 'record', id); if (section !== 'overview') next.set('section', section) }
    return `${location.pathname}${next.size ? `?${next}` : ''}`
  }
  function remember(id: string) { listPosition.current = { y: window.scrollY, focus: `asset-name-${id}` } }
  function openRecord(event: MouseEvent<HTMLAnchorElement>, id: string) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return
    event.preventDefault()
    const position = navigationState?.assetListPosition ?? listPosition.current
    void navigate(href(id, params.get('section') ?? 'overview'), { state: { assetListPosition: position } })
  }
  function browse(values: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    next.delete('preview'); next.delete('record'); next.delete('section')
    for (const [key, value] of Object.entries(values)) { if (value) next.set(key, value); else next.delete(key) }
    if (!('page' in values)) next.delete('page')
    void setParams(next)
  }
  async function savePreferences(columns: string[], size = pageSize) {
    const value = await preferenceClient.save(workspace, 'assets', { columns, page_size: size })
    setPreferences(value); setNotice(translate('collections.saved'))
  }
  async function createAsset() {
    if (!modelId) return
    setSaving(true); setError(null)
    try {
      const created = await client.createAsset(workspace, modelId, name)
      setDetail({ owner: workspace.id, asset: created }); setCreatedId(created.id); setDetailError(null); setCreating(false); setModelId(''); setName(''); setModelQuery(''); setReload((value) => value + 1)
      setNotice(translate('collections.updated'))
    } catch (caught) { setError(caught instanceof Error ? caught.message : translate('assets.createFailed')) }
    finally { setSaving(false) }
  }
  async function applyBulkAction() {
    const ids = [...selectedIds].filter((id) => result.results.some((row) => row.id === id))
    if (!ids.length) return
    setSaving(true); setError(null)
    try { await client.bulkAssets(workspace, ids, bulkAction, bulkAction === 'set_hardware_state' ? bulkState : undefined); setSelectedIds(new Set()); setConfirmingArchive(false); setReload((value) => value + 1) }
    catch (caught) { setError(caught instanceof Error ? caught.message : translate('assets.bulkFailed')) }
    finally { setSaving(false) }
  }
  function update(asset: ClientAsset) { setDetail({ owner: workspace.id, asset }); changedId.current = asset.id; setNotice(translate('collections.updated')); setReload((value) => value + 1) }
  const current = detail?.owner === workspace.id && detail.asset.id === activeId ? detail.asset : null
  const filterGroups = [
    { key: 'kind', label: translate('collections.kind'), values: ['hardware', 'software'] },
    { key: 'status', label: translate('collections.status'), values: ['in_stock', 'in_service', 'repair', 'retired', 'disposed', 'planned', 'installed', 'removed'] },
    { key: 'assigned', label: translate('collections.assignment'), values: ['true', 'false'] },
    { key: 'warranty', label: translate('collections.warranty'), values: ['current', 'expired', 'missing'] },
  ]
  const filterLabel = (value: string) => value === 'hardware' || value === 'software' || value === 'current' || value === 'expired' || value === 'missing' ? translate(`collections.${value}`) : value === 'true' ? translate('collections.assigned') : value === 'false' ? translate('collections.unassigned') : value.replaceAll('_', ' ')
  return <>
    <header className="page-header"><div>{!recordId && <h1 id="assets-collection-heading" tabIndex={-1}>{translate('assets.heading')}</h1>}</div><div className="page-header-actions"><AssetCsvTransfer workspace={workspace} client={client} canManage={canManage} onApplied={() => setReload((value) => value + 1)} />{canManage && <button type="button" className="primary-button" aria-label={translate('assets.new')} title={translate('assets.new')} onClick={() => attempt(() => setCreating(true))}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('assets.new')}</span></button>}</div></header>
    {error && !creating && <div className="form-message error" role="alert">{error}</div>}
    {creating && <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="new-asset-heading"><form className="record-form asset-create-form" onSubmit={(event) => { event.preventDefault(); void createAsset() }}><div className="section-heading"><div><h2 id="new-asset-heading">{translate('assets.new')}</h2><p>{translate('assets.newHelp')}</p></div></div>{error && <div className="form-message error" role="alert">{error}</div>}<label className="inventory-model-search"><span>Find a supplier model</span><div><Search size={16} /><input autoFocus type="search" value={modelQuery} onChange={(event) => setModelQuery(event.target.value)} placeholder="Search supplier, product, model, or SKU" /></div></label><label><span>Supplier model</span><select value={modelId} onChange={(event) => setModelId(event.target.value)}><option value="">Choose a model…</option>{modelChoices.map((model) => <option key={model.id} value={model.id}>{model.supplier_name} · {model.product_name} · {model.name} ({model.model_number})</option>)}</select></label>{choice && <p className="inventory-choice-note">Revision {choice.revision} · {Object.keys(choice.specifications).length} saved specifications</p>}<label><span>Asset name (optional)</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder={choice?.name ?? 'Asset display name'} /></label><div className="form-actions"><button type="submit" className="primary-button" disabled={saving || !modelId}>{saving ? 'Creating…' : 'Create asset'}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => attempt(() => setCreating(false))}>{translate('common.cancel')}</button></div></form></section>}
    {!recordId && canManage && selectedIds.size > 0 && <section className="content-section asset-bulk-toolbar" aria-label="Bulk asset actions"><strong>{selectedIds.size} selected</strong><label><span>Action</span><select value={bulkAction} onChange={(event) => { setBulkAction(event.target.value as 'set_hardware_state' | 'archive'); setConfirmingArchive(false) }}><option value="set_hardware_state">Change hardware state</option><option value="archive">Archive assets</option></select></label>{bulkAction === 'set_hardware_state' && <label><span>State</span><select value={bulkState} onChange={(event) => setBulkState(event.target.value as typeof bulkState)}><option value="in_stock">In stock</option><option value="in_service">In service</option><option value="repair">Repair</option><option value="retired">Retired</option></select></label>}{bulkAction === 'archive' && confirmingArchive ? <><span role="status">Archive {selectedIds.size} selected assets? They can be restored from the recycle bin.</span><button className="secondary-button danger" type="button" disabled={saving} onClick={() => attempt(() => { void applyBulkAction() })}><Archive size={15} />{saving ? 'Archiving…' : 'Confirm archive'}</button><button className="row-action" type="button" disabled={saving} onClick={() => setConfirmingArchive(false)}>{translate('common.cancel')}</button></> : <button className={bulkAction === 'archive' ? 'secondary-button danger' : 'secondary-button'} type="button" disabled={saving} onClick={() => { if (bulkAction === 'archive') setConfirmingArchive(true); else attempt(() => { void applyBulkAction() }) }}>{bulkAction === 'archive' ? <Archive size={15} /> : null}{saving ? 'Applying…' : bulkAction === 'archive' ? 'Review archive' : 'Apply'}</button>}<button className="row-action" type="button" disabled={saving} onClick={() => { setSelectedIds(new Set()); setConfirmingArchive(false) }}>{translate('common.clear')}</button></section>}
    {notice && <p role="status">{notice}</p>}{createdId && <Link to={href(createdId)} onClick={() => setCreatedId(null)}>{translate('collections.openCreated')}</Link>}
    {recordId ? <>
      <Link className="collection-record-link" to={href(null)} state={navigationState}>{translate('collections.return')}</Link>
      {current ? <AssetRecord key={current.id} asset={current} workspace={workspace} client={client} canManage={canManage} access={relationshipAccess} section={params.get('section') ?? 'overview'} href={(section) => href(recordId, section)} onChange={update} /> : detailError === `${workspace.id}:${activeId}` ? <p role="alert">{translate('collections.recordUnavailable')}</p> : <p role="status">{translate('collections.loading')}</p>}
    </> : <>
      <div className="collection-toolbar">
        <form key={params.get('search') ?? ''} className="collection-search" onSubmit={(event) => { event.preventDefault(); const search = new FormData(event.currentTarget).get('search'); browse({ search: typeof search === 'string' ? search : '' }) }}><input type="search" name="search" aria-label={translate('collections.search')} defaultValue={params.get('search') ?? ''} /><button className="secondary-button">{translate('collections.searchAction')}</button></form>
        <FilterMenu groups={[...filterGroups.map(({ key, label, values }) => ({ kind: 'choices' as const, label, value: params.get(key) ?? '', choices: [{ value: '', label: translate('collections.all') }, ...values.map((value) => ({ value, label: filterLabel(value) }))], onChange: (value: string) => browse({ [key]: value || null }) })), { kind: 'custom', label: translate('collections.site'), valueLabel: siteLabel, content: <AssetSiteFilter workspace={workspace} value={params.get('site') ?? ''} onChange={(site) => browse({ site: site || null })} /> }]} activeCount={filterKeys.filter((key) => params.has(key)).length} onClear={() => browse(Object.fromEntries(filterKeys.map((key) => [key, null])))} />
        {preferences && <ColumnChooser preferences={preferences} labels={labels} onSave={savePreferences} onReset={async () => { const value = await preferenceClient.reset(workspace, 'assets'); pendingPreferenceReset.current = true; setPreferences(value) }} />}
        <label className="collection-page-size">{translate('collections.pageSize')}<select disabled={guarded} value={pageSize} onChange={(event) => { const size = Number(event.target.value) as 25 | 50 | 100; browse({ page_size: String(size) }); void savePreferences([...(preferences?.columns ?? assetColumns)], size).catch(() => setError(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
      </div>
      <div className="collection-active-filters">{filterKeys.filter((key) => params.has(key)).map((key) => <button type="button" className="row-action" key={key} aria-label={translate('collections.removeFilter', { label: key })} onClick={() => browse({ [key]: null })}>{translate(`collections.${key === 'assigned' ? 'assignment' : key}`)}: {key === 'site' ? siteLabel : filterLabel(params.get(key) ?? '')} ×</button>)}</div>
      <label className="collection-mobile-order">{translate('collections.ordering')}<select value={params.get('ordering') ?? 'name'} onChange={(event) => browse({ ordering: event.target.value })}>{assetColumns.flatMap((column) => [<option key={column} value={column}>{labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{labels[column]} ↓</option>])}</select></label>
      {(phase === 'loading' || (phase === 'ready' && !listReady)) && <p role="status">{translate('collections.loading')}</p>}
      {phase === 'error' && <p role="alert">{translate('assets.loadFailed', { workspace: ownerLabel })} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p>}
      {listReady && <>
        <p>{translate('collections.count', { count: result.count })}</p>
        {result.results.length === 0 ? <p>{translate('collections.empty')}</p> : <CollectionTable<AssetCollectionResult['results'][number]> label={translate('assets.heading')} rows={result.results} selectable={canManage} selected={selectedIds} onSelection={setSelectedIds} ordering={query.ordering} onOrder={(ordering) => browse({ ordering })} columns={(preferences?.columns ?? assetColumns).map((column) => ({ id: column, label: labels[column], render: (row) => column === 'name' ? <><button id={`asset-name-${row.id}`} type="button" className="collection-name" onClick={() => { remember(row.id); setDetailError(null); void navigate(href(row.id, 'overview', true), { state: { assetListPosition: listPosition.current } }) }}>{row.name}</button></> : column === 'model' ? `${row.model_name} · ${row.kind}` : column === 'warranty' ? row.warranty_ends_on || translate('collections.missing') : (row[column as 'status' | 'assignment' | 'site'] || translate('collections.missing')).replaceAll('_', ' ') }))} />}
        <CollectionPagination label={translate('assets.heading')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(next) => browse({ page: String(next) })} />
      </>}
    </>}
    {previewId && <QuickDrawer returnLabel={translate('collections.return')} returnHref={href(null)} returnFocusId="assets-collection-heading" title={current?.name ?? translate('collections.preview')} onClose={() => { void navigate(href(null), { replace: true, state: { assetListPosition: navigationState?.assetListPosition ?? listPosition.current } }) }}>
      {current ? <><Link className="collection-record-link" to={href(previewId, params.get('section') ?? 'overview')} onClick={(event) => openRecord(event, previewId)}>{translate('collections.openFullPage')}</Link><AssetRecord embedded key={current.id} asset={current} workspace={workspace} client={client} canManage={canManage} access={relationshipAccess} section={params.get('section') ?? 'overview'} href={(section) => href(previewId, section, true)} onChange={update} /></> : detailError === `${workspace.id}:${activeId}` ? <p role="alert">{translate('collections.recordUnavailable')}</p> : <p role="status">{translate('collections.loading')}</p>}
    </QuickDrawer>}
  </>
}
