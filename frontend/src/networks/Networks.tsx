import { DNSRegister } from './DNSRegister'
import { DeviceRegister } from './DeviceRegister'
import { WirelessWorkspace } from './NetworkWireless'
import { NetworkNetBox } from './NetworkNetBox'
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
import { networkText as t } from './networkText'
import '../collections/collections.css'
import './network-layout.css'

type NetworkResult = Awaited<ReturnType<NetworksClient['collection']>>
const networkColumns = ['cidr', 'vlan', 'subnet_mask'] as const
const labels = { cidr: t('cidr'), vlan: t('vlan'), subnet_mask: t('subnetMask') }

type NetworksProps = { workspace: WorkspaceContext; client?: NetworksClient; preferenceClient?: typeof browserCollectionPreferences; relationshipsClient: RelationshipsClient }
export function Networks(props: NetworksProps) {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const wireless = params.get('view') === 'wireless'
  function href(view: string) {
    const next = new URLSearchParams(params)
    for (const key of ['preview', 'record', 'create', 'section', 'address', 'wireless', 'ssid', 'ssid_full', 'ssid_section', 'vlans', 'vlans_full', 'vlans_section', 'vrfs', 'vrfs_full', 'vrfs_section', 'racks', 'racks_full', 'racks_section', 'racks_device', 'devices', 'devices_full', 'devices_section', 'interface', 'interface_view', 'interface_ip', 'interface_mac', 'dns', 'dns_full', 'dns_section', 'dns_record', 'dns_record_view', 'dns_record_history_page', 'circuits', 'circuits_full', 'circuits_section', 'handoff', 'history_page', 'netbox_q', 'netbox_type', 'netbox_order', 'netbox_page', 'netbox_size', 'netbox_link']) next.delete(key)
    if (view !== 'networks') next.set('view', view); else next.delete('view')
    return `${location.pathname}${next.size ? `?${next}` : ''}`
  }
  const viewIds = ['networks', 'devices', 'dns', 'wireless', 'netbox'] as const
  const requestedView = params.get('view')
  const currentView = viewIds.includes(requestedView as typeof viewIds[number]) ? requestedView as typeof viewIds[number] : 'networks'
  const views = viewIds.map((id) => ({ id, label: id === 'netbox' ? translate('netbox.nav') : id === 'networks' ? t('heading') : t(id), href: href(id) }))
  return <>
    <nav aria-label={t('views')} className="record-sections network-views">
      {views.map((view) => <Link key={view.id} to={view.href} aria-current={currentView === view.id ? 'page' : undefined}>{view.label}</Link>)}
    </nav>
    <label className="record-sections-mobile network-views-mobile">{t('views')}<select aria-label={t('views')} value={currentView} onChange={(event) => {
      const target = views.find((view) => view.id === event.target.value)
      if (target) void navigate(target.href, { state: location.state as unknown })
    }}>{views.map((view) => <option key={view.id} value={view.id}>{view.label}</option>)}</select></label>
    {currentView === 'netbox' ? <NetworkNetBox workspace={props.workspace} client={props.client ?? browserNetworksClient} preferenceClient={props.preferenceClient} /> : currentView === 'dns' ? <DNSRegister workspace={props.workspace} client={props.client ?? browserNetworksClient} preferenceClient={props.preferenceClient} /> : currentView === 'devices' ? <DeviceRegister workspace={props.workspace} client={props.client ?? browserNetworksClient} relationshipsClient={props.relationshipsClient} preferenceClient={props.preferenceClient} /> : wireless ? <WirelessWorkspace workspace={props.workspace} client={props.client ?? browserNetworksClient} preferenceClient={props.preferenceClient} /> : <NetworkCollection {...props} />}
  </>
}

function NetworkCollection({ workspace, client = browserNetworksClient, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; client?: NetworksClient; preferenceClient?: typeof browserCollectionPreferences; relationshipsClient: RelationshipsClient }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const guarded = useContext(NavigationGuardContext)!.isGuarded
  const [preferences, setPreferences] = useState<CollectionPreferences | null>(null)
  const [response, setResponse] = useState<{ key: string; result?: NetworkResult } | null>(null)
  const [detail, setDetail] = useState<{ key: string; record?: NetworkRecord } | null>(null)
  const [reload, setReload] = useState(0)
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
  const queryText = JSON.stringify({ q: params.get('q') ?? '', page, page_size: pageSize, ordering: params.get('ordering') ?? 'cidr', ...(params.get('vlan') ? { vlan: params.get('vlan') } : {}) })
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
      <label className="collection-mobile-order">{t('ordering')}<select value={query.ordering} onChange={(event) => browse({ ordering: event.target.value })}>{(['cidr', 'vlan'] as const).flatMap((column) => [<option key={column} value={column}>{labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{labels[column]} ↓</option>])}</select></label>
      {!response || response.key !== key ? <p role="status">{translate('collections.loading')}</p> : !result ? <p role="alert">{t('loadFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        <p>{t('count', { count: result.count })}</p>
        {result.results.length ? <CollectionTable<NetworkSummary> label={t('heading')} rows={result.results} selectable={false} selected={new Set()} onSelection={() => {}} ordering={query.ordering} onOrder={(ordering) => browse({ ordering })} columns={(preferences?.columns ?? networkColumns).map((column) => ({ id: column, label: labels[column as keyof typeof labels], identity: column === 'cidr', sortable: column !== 'subnet_mask', render: (row) => column === 'cidr' ? <button type="button" id={`network-cidr-${row.id}`} className="collection-name" onClick={() => { position.current = { y: window.scrollY, focus: `network-cidr-${row.id}` }; void navigate(href(row.id, 'overview', true), { state: { networkPosition: position.current } }) }}>{row.cidr}</button> : String(row[column as 'vlan' | 'subnet_mask'] ?? translate('collections.missing')) }))} /> : <p>{t('empty')}</p>}
        <CollectionPagination label={t('heading')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(next) => browse({ page: String(next) })} />
      </>}
    </>}
    {previewId && <QuickDrawer title={current?.cidr ?? t('heading')} returnLabel={t('return')} returnHref={href(null)} returnFocusId={result?.results.some((record) => record.id === previewId) ? `network-cidr-${previewId}` : 'networks-heading'} onClose={() => void navigate(href(null), { replace: true, state: navigationState })}><Link className="collection-record-link" to={href(activeId, section)} state={navigationState}>{translate('collections.openFullPage')}</Link>{recordContent}</QuickDrawer>}
    {creating && <QuickDrawer title={t('new')} returnLabel={t('return')} returnHref={href(null)} returnFocusId="networks-heading" onClose={() => void navigate(href(null), { replace: true, state: navigationState })}><NetworkRecordView record={null} workspace={workspace} client={client} canManage={Boolean(result?.can_manage)} embedded section="overview" href={() => href(null)} onCancel={() => void navigate(href(null), { replace: true, state: navigationState })} onSaved={(record) => { setDetail({ key: `${workspace.kind}:${workspace.id}:${record.id}`, record }); setPending(href(record.id, 'overview', true)); setReload(reload + 1) }} /></QuickDrawer>}
  </>
}
