import type { ComponentType, ReactNode } from 'react'
import { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { translate } from '../i18n/localization'
import { QuickDrawer } from '../collections/QuickDrawer'
import { CollectionTable } from '../collections/CollectionTable'
import { CollectionPagination } from '../CollectionPagination'
import { ColumnChooser } from '../collections/ColumnChooser'
import { browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { FilterMenu } from '../FilterMenu'
import { NavigationGuardContext } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { AddressQuery, ListResult, NetworksClient } from './api'

type ChildRecord = { id: string; subnet_id?: string | null }
export type ChildRecordProps<D> = { record: D | null; canManage: boolean; onSaved: (record: D) => void; onReturn: () => void }
export type ChildCollectionConfig<S extends ChildRecord, D extends S> = {
  key: string; feature: string; columns: readonly string[]; labels: Record<string, string>
  title: string; back: string; create: string; search: string; order: string; failed: string; empty: string
  count: (count: number) => string
  association?: { label: string; choices: { value: string; label: string }[] }
  statuses: { value: string; label: string }[]
  identity: (row: S) => string
  value: (row: S, column: string) => ReactNode
  load: (client: NetworksClient, workspace: WorkspaceContext, query: AddressQuery, signal: AbortSignal) => Promise<ListResult<S>>
  read: (client: NetworksClient, workspace: WorkspaceContext, id: string, signal: AbortSignal) => Promise<D>
}

export function NetworkChildCollection<S extends ChildRecord, D extends S>({ workspace, subnetId, client, config, RecordComponent, standalone = false, preferenceClient = browserCollectionPreferences }: {
  standalone?: boolean; workspace: WorkspaceContext; subnetId: string; client: NetworksClient; config: ChildCollectionConfig<S, D>
  RecordComponent: ComponentType<ChildRecordProps<D> & { workspace: WorkspaceContext; subnetId: string; client: NetworksClient }>; preferenceClient?: typeof browserCollectionPreferences
}) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const [preferences, setPreferences] = useState<CollectionPreferences | null>(null)
  const [response, setResponse] = useState<{ key: string; result?: Awaited<ReturnType<ChildCollectionConfig<S, D>['load']>> } | null>(null)
  const [detail, setDetail] = useState<{ key: string; record?: D } | null>(null)
  const [reload, setReload] = useState(0)
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState<URLSearchParams | null>(null)
  const guarded = useContext(NavigationGuardContext)!.isGuarded
  const changed = useRef<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const previousAddress = useRef<string | null>(null)
  const selected = params.get(config.key)
  const fullPage = standalone && params.get(`${config.key}_full`) === 'true' && Boolean(selected)
  const Heading = standalone ? 'h1' : 'h2'
  const association = config.association ? params.get(`${config.key}_association`) ?? '' : ''
  const requested = Number(params.get(`${config.key}_page`) ?? 1)
  const page = Number.isSafeInteger(requested) && requested > 0 ? requested : 1
  const size = Number(params.get(`${config.key}_size`))
  const pageSize = [25, 50, 100].includes(size) ? size : preferences?.page_size ?? 25
  const queryText = JSON.stringify({ ...(!standalone ? { subnet_id: subnetId } : {}), ...(association ? { association } : {}), q: params.get(`${config.key}_q`) ?? '', page, page_size: pageSize, ordering: params.get(`${config.key}_order`) ?? 'name', ...(config.statuses.length && params.get(`${config.key}_status`) ? { status: params.get(`${config.key}_status`) } : {}) })
  const query = useMemo(() => JSON.parse(queryText) as AddressQuery, [queryText])
  const key = `${config.feature}:${workspace.kind}:${workspace.id}:${queryText}`
  const detailKey = `${config.feature}:${workspace.kind}:${workspace.id}:${subnetId}:${selected}`
  const result = response?.key === key ? response.result : null
  const record = detail?.key === detailKey ? detail.record : null
  useEffect(() => { const controller = new AbortController(); preferenceClient.load(workspace, config.feature, config.columns, controller.signal).then((value) => { if (!controller.signal.aborted) setPreferences(value) }).catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(config.columns)) }); return () => controller.abort() }, [workspace, preferenceClient, config])
  useEffect(() => { if (!preferences) return; const controller = new AbortController(); config.load(client, workspace, query, controller.signal).then((value) => { if (controller.signal.aborted) return; setResponse({ key, result: value }); if (changed.current) { setNotice(translate(value.results.some((row) => row.id === changed.current) ? 'networkLayout.recordUpdated' : 'networkLayout.updatedOutside')); changed.current = null } }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) }); return () => controller.abort() }, [workspace, client, key, query, preferences, reload, config])
  useEffect(() => { if (!selected || selected === 'new') return; const controller = new AbortController(); config.read(client, workspace, selected, controller.signal).then((value) => { if (!controller.signal.aborted) setDetail({ key: detailKey, ...((standalone || value.subnet_id === subnetId) ? { record: value } : {}) }) }).catch(() => { if (!controller.signal.aborted) setDetail({ key: detailKey }) }); return () => controller.abort() }, [workspace, client, selected, detailKey, subnetId, config, standalone])
  useEffect(() => { if (!pending || guarded) return; const frame = requestAnimationFrame(() => { setParams(pending, { replace: true, state: location.state as unknown }); setPending(null) }); return () => cancelAnimationFrame(frame) }, [pending, guarded, setParams, location.state])
  useEffect(() => { if (selected) previousAddress.current = selected; else if (result && previousAddress.current) { if (standalone) window.scrollTo({ top: (location.state as { childListY?: number } | null)?.childListY ?? 0 }); (document.getElementById(`${config.key}-${previousAddress.current}`) ?? heading.current)?.focus({ preventScroll: standalone }); previousAddress.current = null } }, [selected, result, config.key, standalone, location.state])
  function next(values: Record<string, string | null>) { const changedParams = new URLSearchParams(params); for (const [name, value] of Object.entries(values)) { if (value) changedParams.set(name, value); else changedParams.delete(name) } return changedParams }
  function browse(values: Record<string, string | null>) {
    const updated = next({ ...(!(`${config.key}_page` in values) && !(config.key in values) ? { [`${config.key}_page`]: null } : {}), ...values })
    if (standalone && config.key in values) { updated.delete(`${config.key}_full`); updated.delete(`${config.key}_section`); updated.delete('history_page') }
    setParams(updated, { state: standalone && values[config.key] ? { childListY: window.scrollY } : location.state as unknown })
  }
  function href(values: Record<string, string | null>) { return `${location.pathname}?${next(values)}` }
  function saved(value: D) {
    changed.current = value.id
    setDetail({ key: `${config.feature}:${workspace.kind}:${workspace.id}:${subnetId}:${value.id}`, record: value })
    const destination = !standalone && value.subnet_id !== subnetId ? null : value.id
    // Only creation or a move out of this parent changes selection. Queuing the
    // same URL after an ordinary save can race a subsequent drawer dismissal.
    if (destination !== selected) setPending(next({ [config.key]: destination }))
    setReload(reload + 1)
  }
  const recordContent = <>
      {standalone && notice && <p role="status">{notice}</p>}
      {selected === 'new' || record ? <RecordComponent key={selected} record={record ?? null} workspace={workspace} subnetId={subnetId} client={client} canManage={Boolean(result?.can_manage)} onSaved={saved} onReturn={() => browse({ [config.key]: null })} /> : <><button type="button" className="secondary-button" onClick={() => browse({ [config.key]: null })}>{config.back}</button><p role={detail?.key === detailKey ? 'alert' : 'status'}>{translate(detail?.key === detailKey ? 'collections.recordUnavailable' : 'collections.loading')}</p></>}
  </>
  const collectionContent = <>
      <Heading id={`network-child-${config.key}`} ref={heading} tabIndex={-1}>{config.title}</Heading>
      {result?.can_manage && <button type="button" className="primary-button" onClick={() => browse({ [config.key]: 'new' })}>{config.create}</button>}
      <div className="collection-toolbar">
        <form key={query.q} className="address-search collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ [`${config.key}_q`]: typeof value === 'string' ? value : '' }) }}><input type="search" name="q" defaultValue={query.q} aria-label={config.search} /><button type="submit" className="secondary-button">{translate('collections.searchAction')}</button></form>
        {(config.statuses.length > 0 || config.association) && <FilterMenu groups={[{ kind: 'choices', label: translate('collections.status'), value: query.status ?? '', choices: [{ value: '', label: translate('collections.all') }, ...config.statuses], onChange: (value) => browse({ [`${config.key}_status`]: value || null }) }, ...(config.association ? [{ kind: 'choices' as const, label: config.association.label, value: association, choices: [{ value: '', label: translate('collections.all') }, ...config.association.choices], onChange: (value: string) => browse({ [`${config.key}_association`]: value || null }) }] : [])]} activeCount={Number(Boolean(query.status)) + Number(Boolean(association))} onClear={() => browse({ [`${config.key}_status`]: null, [`${config.key}_association`]: null })} />}
        {preferences && <ColumnChooser preferences={preferences} labels={config.labels} onSave={async (selectedColumns) => setPreferences(await preferenceClient.save(workspace, config.feature, { columns: selectedColumns, page_size: pageSize as 25 | 50 | 100 }))} onReset={async () => { setPreferences(await preferenceClient.reset(workspace, config.feature)); setPending(next({ [`${config.key}_size`]: null, [`${config.key}_page`]: null })) }} />}
        <label>{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => { const value = Number(event.target.value) as 25 | 50 | 100; browse({ [`${config.key}_size`]: String(value) }); void preferenceClient.save(workspace, config.feature, { columns: preferences?.columns ?? [...config.columns], page_size: value }).then(setPreferences).catch(() => setNotice(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((value) => <option key={value}>{value}</option>)}</select></label>
      </div>
      {query.status && <button className="row-action" type="button" onClick={() => browse({ [`${config.key}_status`]: null })}>{translate('collections.status')}: {config.statuses.find((item) => item.value === query.status)?.label ?? query.status} ×</button>}
      {association && config.association && <button className="row-action" type="button" onClick={() => browse({ [`${config.key}_association`]: null })}>{config.association.label}: {config.association.choices.find((item) => item.value === association)?.label ?? association} ×</button>}
      <label className="collection-mobile-order">{config.order}<select value={query.ordering} onChange={(event) => browse({ [`${config.key}_order`]: event.target.value })}>{config.columns.flatMap((column) => [<option key={column} value={column}>{config.labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{config.labels[column]} ↓</option>])}</select></label>
      {!response || response.key !== key ? <p role="status">{translate('collections.loading')}</p> : !result ? <p role="alert">{config.failed} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        <p>{config.count(result.count)}</p>
        {result.results.length ? <CollectionTable<S & { name: string }> label={config.title} rows={result.results.map((row) => ({ ...row, name: config.identity(row) }))} columns={(preferences?.columns ?? config.columns).map((column) => ({ id: column, label: config.labels[column], render: (row) => column === 'name' ? <button className="collection-name" id={`${config.key}-${row.id}`} type="button" onClick={() => browse({ [config.key]: row.id })}>{config.identity(row)}</button> : config.value(row, column) }))} ordering={query.ordering} onOrder={(value) => browse({ [`${config.key}_order`]: value })} selectable={false} selected={new Set()} onSelection={() => {}} /> : <p>{config.empty}</p>}
        <CollectionPagination label={config.title} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(value) => browse({ [`${config.key}_page`]: String(value) })} />
      </>}
  </>
  return <section aria-label={config.title}>
    {notice && !(standalone && selected) && <p role="status">{notice}</p>}
    {standalone ? <>
      {fullPage ? <><Link to={href({ [config.key]: null, [`${config.key}_full`]: null, [`${config.key}_section`]: null, history_page: null })} state={location.state as unknown}>{config.back}</Link>{recordContent}</> : collectionContent}
      {selected && !fullPage && <QuickDrawer title={record ? config.identity(record) : selected === 'new' ? config.create : config.title} onClose={() => browse({ [config.key]: null })} returnHref={href({ [config.key]: null })} returnLabel={config.back} returnFocusId={selected === 'new' ? `network-child-${config.key}` : `${config.key}-${selected}`}>
        <Link to={href({ [`${config.key}_full`]: 'true' })} state={location.state as unknown}>{translate('collections.openFullPage')}</Link>
        {recordContent}
      </QuickDrawer>}
    </> : selected ? recordContent : collectionContent}
  </section>
}
