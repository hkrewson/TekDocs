import { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { translate } from '../i18n/localization'
import { NavigationGuardContext } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import { browserCommercialClient } from './api'
import type { CommercialClient, CommercialContract, CommercialResult, ContractCollectionQuery } from './api'
import { CollectionTable } from '../collections/CollectionTable'
import { CollectionPagination } from '../CollectionPagination'
import { ColumnChooser } from '../collections/ColumnChooser'
import { QuickDrawer } from '../collections/QuickDrawer'
import { browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { FilterMenu } from '../FilterMenu'
import { ContractCreate, ContractRecord } from './ContractRecord'
import { contractText as t } from './contractText'
import '../collections/collections.css'
import './contracts.css'

const contractColumns = ['name', 'provider', 'kind', 'status', 'renews_on', 'ends_on'] as const
const labels = { name: t('contractName'), provider: t('provider'), kind: t('kind'), status: t('status'), renews_on: t('renewsOn'), ends_on: t('endsOn') }

export function Contracts({ workspace, client = browserCommercialClient, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; client?: CommercialClient; preferenceClient?: typeof browserCollectionPreferences }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const guarded = useContext(NavigationGuardContext)!.isGuarded
  const [preferences, setPreferences] = useState<CollectionPreferences | null>(null)
  const [response, setResponse] = useState<{ key: string; result?: CommercialResult } | null>(null)
  const [detail, setDetail] = useState<{ key: string; record?: CommercialContract } | null>(null)
  const [reload, setReload] = useState(0)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const changed = useRef<string | null>(null)
  const position = useRef({ y: 0, focus: '' })
  const previousFullPage = useRef(false)
  const navigationState = location.state as { contractPosition?: { y: number; focus: string } } | null
  const recordId = params.get('record')
  const previewId = recordId ? null : params.get('preview')
  const activeId = recordId ?? previewId
  const creating = params.get('create') === 'true' && !activeId
  const section = params.get('section') ?? 'overview'
  const requestedPage = Number(params.get('page') ?? 1)
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const pageSize = [25, 50, 100].includes(Number(params.get('page_size'))) ? Number(params.get('page_size')) : preferences?.page_size ?? 25
  const queryText = JSON.stringify({ q: params.get('q') ?? '', page, page_size: pageSize, ordering: params.get('ordering') ?? 'name', ...(params.get('status') ? { status: params.get('status') } : {}), ...(params.get('kind') ? { kind: params.get('kind') } : {}) })
  const query = useMemo(() => JSON.parse(queryText) as ContractCollectionQuery, [queryText])
  const key = `${workspace.kind}:${workspace.id}:${queryText}`
  const detailKey = `${workspace.kind}:${workspace.id}:${activeId}`
  const result = response?.key === key ? response.result : null
  const current = detail?.key === detailKey ? detail.record : null
  useEffect(() => { const controller = new AbortController(); preferenceClient.load(workspace, 'contracts', contractColumns, controller.signal).then((value) => { if (!controller.signal.aborted) setPreferences(value) }).catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(contractColumns)) }); return () => controller.abort() }, [workspace, preferenceClient])
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
    const frame = requestAnimationFrame(() => { void navigate(pending, { replace: true, state: { contractPosition: navigationState?.contractPosition ?? position.current } }); setPending(null) })
    return () => cancelAnimationFrame(frame)
  }, [pending, guarded, navigate, navigationState])
  useEffect(() => {
    if (recordId) { previousFullPage.current = true; window.scrollTo({ top: 0 }) }
    else if (previousFullPage.current && result) { previousFullPage.current = false; const saved = navigationState?.contractPosition ?? position.current; window.scrollTo({ top: saved.y }); (document.getElementById(saved.focus) ?? document.getElementById('contracts-heading'))?.focus({ preventScroll: true }) }
  }, [recordId, result, navigationState])
  function href(id: string | null, nextSection = 'overview', preview = false) {
    const next = new URLSearchParams(params); next.delete('record'); next.delete('preview'); next.delete('section'); next.delete('create')
    if (id !== activeId) next.delete('history_page')
    if (id) { next.set(preview ? 'preview' : 'record', id); if (nextSection !== 'overview') next.set('section', nextSection) }
    return `${location.pathname}${next.size ? `?${next}` : ''}`
  }
  function browse(values: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [name, value] of Object.entries(values)) { if (value) next.set(name, value); else next.delete(name) } if (!('page' in values)) next.delete('page'); setParams(next) }
  function update(record: CommercialContract) { setDetail({ key: detailKey, record }); changed.current = record.id; setNotice(translate('collections.updated')); setReload(reload + 1) }
  const recordContent = current ? <ContractRecord key={`${current.id}:${section}`} record={current} workspace={workspace} client={client} canManage={Boolean(result?.can_manage)} canViewCosts={Boolean(result?.can_view_costs)} canViewRelationships={Boolean(result?.can_view_relationships)} section={section} href={(next) => href(activeId, next, Boolean(previewId))} embedded={Boolean(previewId)} onChange={update} onArchive={() => { setDetail(null); setPending(href(null)); setReload(reload + 1) }} /> : detail?.key === detailKey ? <p role="alert">{translate('collections.recordUnavailable')}</p> : <p role="status">{translate('collections.loading')}</p>
  return <>
    <header className="page-header"><div>{!recordId && <h1 id="contracts-heading" tabIndex={-1}>{translate('contracts.heading')}</h1>}</div>{result?.can_manage && <button type="button" className="primary-button" onClick={() => { const next = new URLSearchParams(); next.set('create', 'true'); void navigate(`${href(null)}${href(null).includes('?') ? '&' : '?'}${next}`, { state: { contractPosition: { y: window.scrollY, focus: 'contracts-heading' } } }) }}>{translate('contracts.new')}</button>}</header>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    {recordId ? <><Link to={href(null)} state={navigationState}>{t('return')}</Link>{recordContent}</> : <>
      <div className="collection-toolbar">
        <form key={query.q} className="collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ q: typeof value === 'string' ? value : '' }) }}><input type="search" name="q" defaultValue={query.q} aria-label={t('search')} /><button type="submit" className="secondary-button">{t('searchAction')}</button></form>
        <FilterMenu groups={[{ kind: 'choices', label: t('status'), value: query.status ?? '', choices: [{ value: '', label: translate('collections.all') }, ...['draft', 'active', 'expired', 'terminated'].map((value) => ({ value, label: value }))], onChange: (status) => browse({ status: status || null }) }, { kind: 'choices', label: t('kind'), value: query.kind ?? '', choices: [{ value: '', label: translate('collections.all') }, ...['service', 'support', 'lease', 'subscription', 'other'].map((value) => ({ value, label: value }))], onChange: (kind) => browse({ kind: kind || null }) }]} activeCount={Number(Boolean(query.kind)) + Number(Boolean(query.status))} onClear={() => browse({ kind: null, status: null })} />
        {preferences && <ColumnChooser preferences={preferences} labels={labels} onSave={async (columns) => setPreferences(await preferenceClient.save(workspace, 'contracts', { columns, page_size: pageSize as 25 | 50 | 100 }))} onReset={async () => { setPreferences(await preferenceClient.reset(workspace, 'contracts')); const next = new URLSearchParams(params); next.delete('page'); next.delete('page_size'); setPending(`${location.pathname}${next.size ? `?${next}` : ''}`) }} />}
        <label className="collection-page-size">{translate('collections.pageSize')}<select disabled={guarded} value={pageSize} onChange={(event) => { const size = Number(event.target.value) as 25 | 50 | 100; browse({ page_size: String(size) }); void preferenceClient.save(workspace, 'contracts', { columns: preferences?.columns ?? [...contractColumns], page_size: size }).then(setPreferences).catch(() => setError(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
      </div>
      <div className="collection-active-filters">{(['kind', 'status'] as const).filter((field) => query[field]).map((field) => <button key={field} type="button" className="row-action" aria-label={translate('collections.removeFilter', { label: field })} onClick={() => browse({ [field]: null })}>{t(field)}: {query[field]} ×</button>)}</div>
      <label className="collection-mobile-order">{t('ordering')}<select value={query.ordering} onChange={(event) => browse({ ordering: event.target.value })}>{contractColumns.flatMap((column) => [<option key={column} value={column}>{labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{labels[column]} ↓</option>])}</select></label>
      {!response || response.key !== key ? <p role="status">{translate('collections.loading')}</p> : !result ? <p role="alert">{translate('contracts.loadFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        <p>{t('count', { count: result.count })}</p>
        {result.results.length ? <CollectionTable<CommercialContract> label={translate('contracts.heading')} rows={result.results} selectable={false} selected={new Set()} onSelection={() => {}} ordering={query.ordering} onOrder={(ordering) => browse({ ordering })} columns={(preferences?.columns ?? contractColumns).map((column) => ({ id: column, label: labels[column as keyof typeof labels], render: (row) => column === 'name' ? <button type="button" id={`contract-name-${row.id}`} className="collection-name" onClick={() => { position.current = { y: window.scrollY, focus: `contract-name-${row.id}` }; void navigate(href(row.id, 'overview', true), { state: { contractPosition: position.current } }) }}>{row.name}</button> : column === 'provider' ? row.provider_name : row[column as 'kind' | 'status' | 'renews_on' | 'ends_on'] || translate('collections.missing') }))} /> : <p>{t('empty')}</p>}
        <CollectionPagination label={translate('contracts.heading')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(next) => browse({ page: String(next) })} />
      </>}
    </>}
    {previewId && <QuickDrawer title={current?.name ?? translate('contracts.heading')} returnLabel={t('return')} returnHref={href(null)} returnFocusId="contracts-heading" onClose={() => void navigate(href(null), { replace: true, state: navigationState })}><Link className="collection-record-link" to={href(activeId, section)} state={navigationState}>{translate('collections.openFullPage')}</Link>{recordContent}</QuickDrawer>}
    {creating && <QuickDrawer title={translate('contracts.new')} returnLabel={t('return')} returnHref={href(null)} returnFocusId="contracts-heading" onClose={() => void navigate(href(null), { replace: true, state: navigationState })}><ContractCreate workspace={workspace} client={client} onCancel={() => void navigate(href(null), { replace: true, state: navigationState })} onCreated={(record) => { setDetail({ key: `${workspace.kind}:${workspace.id}:${record.id}`, record }); setPending(href(record.id, 'overview', true)); setReload(reload + 1) }} /></QuickDrawer>}
  </>
}
