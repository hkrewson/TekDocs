import { DeviceRegister } from './DeviceRegister'
import { RackRegister } from './RackRegister'
import { AddressingRegister } from './AddressingRegister'
import { WirelessWorkspace } from './NetworkWireless'
import { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { translate } from '../i18n/localization'
import { NavigationGuardContext } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import { browserNetworksClient } from './api'
import type { NetworksClient, NetworkRecord, NetworkSummary, NetworkQuery } from './api'
import { CollectionTable } from '../collections/CollectionTable'
import { CollectionPagination } from '../CollectionPagination'
import { ColumnChooser } from '../collections/ColumnChooser'
import { QuickDrawer } from '../collections/QuickDrawer'
import { browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { FilterMenu } from '../FilterMenu'
import { NetworkRecordView } from './NetworkRecordView'
import type { RelationshipsClient } from '../relationships/api'
import { RelationshipGraph } from '../relationships/RelationshipGraph'
import { networkText as t } from './networkText'
import '../collections/collections.css'
import './network-layout.css'

type NetworkResult = Awaited<ReturnType<NetworksClient['collection']>>
const networkColumns = ['name', 'location', 'vlan', 'cidr'] as const
const labels = { name: t('name'), location: t('location'), vlan: t('vlan'), cidr: t('cidr') }

type NetworksProps = { workspace: WorkspaceContext; client?: NetworksClient; preferenceClient?: typeof browserCollectionPreferences; relationshipsClient: RelationshipsClient }
export function Networks(props: NetworksProps) {
  const [params] = useSearchParams()
  const location = useLocation()
  const wireless = params.get('view') === 'wireless'
  function href(view: string) {
    const next = new URLSearchParams(params)
    for (const key of ['preview', 'record', 'create', 'section', 'address', 'wireless', 'ssid', 'ssid_full', 'ssid_section', 'vlans', 'vlans_full', 'vlans_section', 'vrfs', 'vrfs_full', 'vrfs_section', 'racks', 'racks_full', 'racks_section', 'racks_device', 'devices', 'devices_full', 'devices_section', 'history_page']) next.delete(key)
    if (view !== 'networks') next.set('view', view); else next.delete('view')
    return `${location.pathname}${next.size ? `?${next}` : ''}`
  }
  return <>
    <nav aria-label={t('views')} className="collection-toolbar"><Link to={href('networks')} aria-current={!['wireless', 'vlans', 'vrfs', 'racks', 'devices'].includes(params.get('view') ?? '') ? 'page' : undefined}>{t('heading')}</Link><Link to={href('wireless')} aria-current={wireless ? 'page' : undefined}>{t('wireless')}</Link>{(['vlans', 'vrfs', 'racks', 'devices'] as const).map((kind) => <Link key={kind} to={href(kind)} aria-current={params.get('view') === kind ? 'page' : undefined}>{t(kind)}</Link>)}</nav>
    {params.get('view') === 'devices' ? <DeviceRegister workspace={props.workspace} client={props.client ?? browserNetworksClient} preferenceClient={props.preferenceClient} /> : params.get('view') === 'racks' ? <RackRegister workspace={props.workspace} client={props.client ?? browserNetworksClient} preferenceClient={props.preferenceClient} /> : params.get('view') === 'vlans' || params.get('view') === 'vrfs' ? <AddressingRegister kind={params.get('view') as 'vlans' | 'vrfs'} workspace={props.workspace} client={props.client ?? browserNetworksClient} preferenceClient={props.preferenceClient} /> : wireless ? <WirelessWorkspace workspace={props.workspace} client={props.client ?? browserNetworksClient} preferenceClient={props.preferenceClient} /> : <NetworkCollection {...props} />}
  </>
}

function NetworkCollection({ workspace, client = browserNetworksClient, preferenceClient = browserCollectionPreferences, relationshipsClient }: { workspace: WorkspaceContext; client?: NetworksClient; preferenceClient?: typeof browserCollectionPreferences; relationshipsClient: RelationshipsClient }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const guarded = useContext(NavigationGuardContext)!.isGuarded
  const [preferences, setPreferences] = useState<CollectionPreferences | null>(null)
  const [response, setResponse] = useState<{ key: string; result?: NetworkResult } | null>(null)
  const [detail, setDetail] = useState<{ key: string; record?: NetworkRecord } | null>(null)
  const [reload, setReload] = useState(0)
  const [showMap, setShowMap] = useState(false)
  const relationshipScope = useMemo(() => workspace.kind === 'organization' ? { organizationId: workspace.id } : {}, [workspace])
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const changed = useRef<string | null>(null)
  const position = useRef({ y: 0, focus: '' })
  const previousFullPage = useRef(false)
  const navigationState = location.state as { networkPosition?: { y: number; focus: string } } | null
  const recordId = params.get('record')
  const previewId = recordId ? null : params.get('preview')
  const activeId = recordId ?? previewId
  const creating = params.get('create') === 'true' && !activeId
  const section = params.get('section') ?? 'overview'
  const requestedPage = Number(params.get('page') ?? 1)
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const pageSize = [25, 50, 100].includes(Number(params.get('page_size'))) ? Number(params.get('page_size')) : preferences?.page_size ?? 25
  const queryText = JSON.stringify({ q: params.get('q') ?? '', page, page_size: pageSize, ordering: params.get('ordering') ?? 'name', ...(params.get('vlan') ? { vlan: params.get('vlan') } : {}) })
  const query = useMemo(() => JSON.parse(queryText) as NetworkQuery, [queryText])
  const key = `${workspace.kind}:${workspace.id}:${queryText}`
  const detailKey = `${workspace.kind}:${workspace.id}:${activeId}`
  const result = response?.key === key ? response.result : null
  const current = detail?.key === detailKey ? detail.record : null
  useEffect(() => { const controller = new AbortController(); preferenceClient.load(workspace, 'networks', networkColumns, controller.signal).then((value) => { if (!controller.signal.aborted) setPreferences(value) }).catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(networkColumns)) }); return () => controller.abort() }, [workspace, preferenceClient])
  useEffect(() => {
    if (!preferences) return
    const controller = new AbortController()
    client.collection(workspace, query, controller.signal).then((value) => {
      if (controller.signal.aborted) return
      setResponse({ key, result: value })
      if (changed.current && !value.results.some((record) => record.id === changed.current)) setNotice(translate('collections.updatedOutside'))
      changed.current = null
    }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [client, workspace, query, key, preferences, reload])
  useEffect(() => {
    if (!activeId) return
    const controller = new AbortController()
    client.detail(workspace, activeId, controller.signal).then((record) => { if (!controller.signal.aborted) setDetail({ key: detailKey, record }) }).catch(() => { if (!controller.signal.aborted) setDetail({ key: detailKey }) })
    return () => controller.abort()
  }, [client, workspace, activeId, detailKey])
  useEffect(() => {
    if (!pending || guarded) return
    const frame = requestAnimationFrame(() => { void navigate(pending, { replace: true, state: { networkPosition: navigationState?.networkPosition ?? position.current } }); setPending(null) })
    return () => cancelAnimationFrame(frame)
  }, [pending, guarded, navigate, navigationState])
  useEffect(() => {
    if (recordId) { previousFullPage.current = true; window.scrollTo({ top: 0 }) }
    else if (previousFullPage.current && result) { previousFullPage.current = false; const saved = navigationState?.networkPosition ?? position.current; window.scrollTo({ top: saved.y }); (document.getElementById(saved.focus) ?? document.getElementById('networks-heading'))?.focus({ preventScroll: true }) }
  }, [recordId, result, navigationState])
  function href(id: string | null, nextSection = 'overview', preview = false) {
    const next = new URLSearchParams(params); next.delete('record'); next.delete('preview'); next.delete('section'); next.delete('create')
    if (id !== activeId) { next.delete('history_page'); for (const key of ['address', 'address_page', 'address_size', 'address_q', 'address_status', 'address_order', 'wireless', 'wireless_page', 'wireless_size', 'wireless_q', 'wireless_status', 'wireless_order']) next.delete(key) }
    if (id) { next.set(preview ? 'preview' : 'record', id); if (nextSection !== 'overview') next.set('section', nextSection) }
    return `${location.pathname}${next.size ? `?${next}` : ''}`
  }
  function browse(values: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [name, value] of Object.entries(values)) { if (value) next.set(name, value); else next.delete(name) } if (!('page' in values)) next.delete('page'); setParams(next) }
  function update(record: NetworkRecord) { setDetail({ key: detailKey, record }); changed.current = record.id; setNotice(translate('collections.updated')); setReload(reload + 1) }
  const recordContent = current ? <NetworkRecordView key={`${current.id}:${section}`} record={current} workspace={workspace} client={client} canManage={Boolean(result?.can_manage)} section={section} href={(next) => href(activeId, next, Boolean(previewId))} embedded={Boolean(previewId)} onSaved={update} onCancel={() => {}} /> : detail?.key === detailKey ? <p role="alert">{translate('collections.recordUnavailable')}</p> : <p role="status">{translate('collections.loading')}</p>
  return <>
    <header className="page-header"><div>{!recordId && <h1 id="networks-heading" tabIndex={-1}>{t('heading')}</h1>}</div>{result?.can_manage && <button type="button" className="primary-button" onClick={() => { const next = new URLSearchParams(); next.set('create', 'true'); void navigate(`${href(null)}${href(null).includes('?') ? '&' : '?'}${next}`, { state: { networkPosition: { y: window.scrollY, focus: 'networks-heading' } } }) }}>{t('new')}</button>}</header>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    {recordId ? <><Link to={href(null)} state={navigationState}>{t('return')}</Link>{recordContent}</> : <>
      <div className="collection-toolbar">
        <form key={query.q} className="collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ q: typeof value === 'string' ? value : '' }) }}><input type="search" name="q" defaultValue={query.q} aria-label={t('search')} /><button type="submit" className="secondary-button">{t('searchAction')}</button></form>
        <FilterMenu groups={[{ kind: 'custom', label: t('vlan'), valueLabel: query.vlan ?? '', content: <form onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('vlan'); browse({ vlan: typeof value === 'string' && value ? value : null }) }}><label>{t('vlan')}<input name="vlan" type="number" min="1" max="4094" defaultValue={query.vlan ?? ''} /></label><button type="submit">{t('searchAction')}</button></form> }]} activeCount={Number(Boolean(query.vlan))} onClear={() => browse({ vlan: null })} />
        {preferences && <ColumnChooser preferences={preferences} labels={labels} onSave={async (columns) => setPreferences(await preferenceClient.save(workspace, 'networks', { columns, page_size: pageSize as 25 | 50 | 100 }))} onReset={async () => { setPreferences(await preferenceClient.reset(workspace, 'networks')); const next = new URLSearchParams(params); next.delete('page'); next.delete('page_size'); setPending(`${location.pathname}${next.size ? `?${next}` : ''}`) }} />}
        <label className="collection-page-size">{translate('collections.pageSize')}<select disabled={guarded} value={pageSize} onChange={(event) => { const size = Number(event.target.value) as 25 | 50 | 100; browse({ page_size: String(size) }); void preferenceClient.save(workspace, 'networks', { columns: preferences?.columns ?? [...networkColumns], page_size: size }).then(setPreferences).catch(() => setError(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
      </div>
      <div className="collection-active-filters">{query.vlan && <button type="button" className="row-action" onClick={() => browse({ vlan: null })}>{t('vlan')}: {query.vlan} ×</button>}</div>
      <label className="collection-mobile-order">{t('ordering')}<select value={query.ordering} onChange={(event) => browse({ ordering: event.target.value })}>{networkColumns.flatMap((column) => [<option key={column} value={column}>{labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{labels[column]} ↓</option>])}</select></label>
      {!response || response.key !== key ? <p role="status">{translate('collections.loading')}</p> : !result ? <p role="alert">{t('loadFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        <p>{t('count', { count: result.count })}</p>
        {result.results.length ? <CollectionTable<NetworkSummary> label={t('heading')} rows={result.results} selectable={false} selected={new Set()} onSelection={() => {}} ordering={query.ordering} onOrder={(ordering) => browse({ ordering })} columns={(preferences?.columns ?? networkColumns).map((column) => ({ id: column, label: labels[column as keyof typeof labels], render: (row) => column === 'name' ? <button type="button" id={`network-name-${row.id}`} className="collection-name" onClick={() => { position.current = { y: window.scrollY, focus: `network-name-${row.id}` }; void navigate(href(row.id, 'overview', true), { state: { networkPosition: position.current } }) }}>{row.name}</button> : column === 'location' ? [row.site_name, row.location_name].filter(Boolean).join(' · ') || t('unassigned') : String(row[column as 'vlan' | 'cidr'] ?? translate('collections.missing')) }))} /> : <p>{t('empty')}</p>}
        <CollectionPagination label={t('heading')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(next) => browse({ page: String(next) })} />
      </>}
    </>}
    {previewId && <QuickDrawer title={current?.name ?? t('heading')} returnLabel={t('return')} returnHref={href(null)} returnFocusId="networks-heading" onClose={() => void navigate(href(null), { replace: true, state: navigationState })}><Link className="collection-record-link" to={href(activeId, section)} state={navigationState}>{translate('collections.openFullPage')}</Link>{recordContent}</QuickDrawer>}
    {creating && <QuickDrawer title={t('new')} returnLabel={t('return')} returnHref={href(null)} returnFocusId="networks-heading" onClose={() => void navigate(href(null), { replace: true, state: navigationState })}><NetworkRecordView record={null} workspace={workspace} client={client} canManage={Boolean(result?.can_manage)} embedded section="overview" href={() => href(null)} onCancel={() => void navigate(href(null), { replace: true, state: navigationState })} onSaved={(record) => { setDetail({ key: `${workspace.kind}:${workspace.id}:${record.id}`, record }); setPending(href(record.id, 'overview', true)); setReload(reload + 1) }} /></QuickDrawer>}
    {!recordId && <><button className="secondary-button" type="button" onClick={() => setShowMap(!showMap)}>{t(showMap ? 'hideMap' : 'showMap')}</button>{showMap && <RelationshipGraph scope={relationshipScope} family="network" client={relationshipsClient} heading={t('map')} />}</>}
  </>
}
