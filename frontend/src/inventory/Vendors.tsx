import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ExternalLink, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { DerivedVendor, InventoryClient, VendorOrdering, VendorQuery, VendorResult } from './api'

const initialQuery: VendorQuery = { q: '', ordering: 'name', page: 1, page_size: 25 }

function classificationLabel(classification: string) {
  if (classification === 'vendor') return translate('products.vendor')
  if (classification === 'manufacturer') return translate('products.manufacturer')
  return classification
}

function initialQueryFrom(parameters: URLSearchParams): VendorQuery {
  const ordering = parameters.get('vendor_order')
  const page = Number(parameters.get('vendor_page'))
  return { ...initialQuery, q: parameters.get('q') ?? '', ordering: ['name', '-name', 'asset_count', '-asset_count'].includes(ordering ?? '') ? ordering as VendorOrdering : 'name', page: Number.isInteger(page) && page > 0 ? page : 1 }
}

export function Vendors({ workspace, client }: { workspace: WorkspaceContext; client: InventoryClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState<VendorQuery>(() => initialQueryFrom(searchParams))
  const [loaded, setLoaded] = useState<{ scope: string; result: VendorResult } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selected, setSelected] = useState<{ scope: string; record: DerivedVendor } | null>(null)
  const [drawerErrorId, setDrawerErrorId] = useState<string | null>(null)
  const scope = `${workspace.kind}:${workspace.id}`
  const drawerId = searchParams.get('vendor')
  const result = loaded?.scope === scope ? loaded.result : null
  const visiblePhase = loaded && loaded.scope !== scope ? 'loading' : phase
  const listedVendor = drawerId ? result?.results.find((vendor) => vendor.id === drawerId) : null
  const drawerRecord = listedVendor ?? (selected?.scope === scope && selected.record.id === drawerId ? selected.record : null)
  const drawerPhase = drawerErrorId === drawerId ? 'error' : drawerRecord ? 'ready' : 'loading'

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.listVendors(workspace, query, controller.signal)
        .then((next) => { if (!controller.signal.aborted) { setLoaded({ scope, result: next }); setPhase('ready') } })
        .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, scope, workspace])

  useEffect(() => {
    if (!drawerId || listedVendor) return
    const controller = new AbortController()
    client.retrieveVendor(workspace, drawerId, controller.signal)
      .then((record) => { if (!controller.signal.aborted) { setSelected({ scope, record }); setDrawerErrorId(null) } })
      .catch(() => { if (!controller.signal.aborted) setDrawerErrorId(drawerId) })
    return () => controller.abort()
  }, [client, drawerId, listedVendor, scope, workspace])

  const updateDrawerUrl = useCallback((id: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('vendor', id); else next.delete('vendor')
    setSearchParams(next)
  }, [searchParams, setSearchParams])

  const changeQuery = (changes: Partial<VendorQuery>) => {
    const nextQuery = { ...query, ...changes, page: changes.page ?? 1 }
    const nextParameters = new URLSearchParams(searchParams)
    if (nextQuery.q) nextParameters.set('q', nextQuery.q); else nextParameters.delete('q')
    if (nextQuery.ordering !== 'name') nextParameters.set('vendor_order', nextQuery.ordering); else nextParameters.delete('vendor_order')
    if (nextQuery.page > 1) nextParameters.set('vendor_page', String(nextQuery.page)); else nextParameters.delete('vendor_page')
    setQuery(nextQuery); setSearchParams(nextParameters, { replace: true })
  }
  const sort = (field: 'name' | 'asset_count') => changeQuery({ ordering: query.ordering === field ? `-${field}` : field })
  const sortIndicator = (field: string) => query.ordering === field ? <ArrowUp size={13} aria-hidden="true" /> : query.ordering === `-${field}` ? <ArrowDown size={13} aria-hidden="true" /> : null
  const openVendor = (vendor: DerivedVendor) => { setSelected({ scope, record: vendor }); setDrawerErrorId(null); updateDrawerUrl(vendor.id) }
  const intro = workspace.kind === 'msp' ? translate('vendors.introMsp') : translate('vendors.introClient')
  const returnHref = workspace.kind === 'msp' ? '/vendors' : `/workspaces/organizations/${workspace.id}/vendors`
  const organizationPath = drawerRecord ? `/workspaces/organizations/${drawerRecord.id}` : ''
  const rangeStart = result && result.count ? (result.page - 1) * result.page_size + 1 : 0
  const rangeEnd = result ? Math.min(result.page * result.page_size, result.count) : 0
  const countLabel = useMemo(() => result ? translate('pagination.range', { first: rangeStart, last: rangeEnd, count: result.count }) : translate('common.loading'), [rangeEnd, rangeStart, result])

  return <>
    <header className="page-header"><div><h1>{translate('vendors.heading')}</h1><p>{intro}</p></div></header>
    {drawerId && <QuickDrawer title={drawerRecord?.name ?? translate('vendors.supplierRecord')} onClose={() => updateDrawerUrl(null)} returnFocusId={`vendor-row-${drawerId}`} returnHref={returnHref} returnLabel={translate('vendors.back')}>
      {drawerPhase === 'loading' && <p role="status">{translate('vendors.loadingSupplier')}</p>}
      {drawerPhase === 'error' && <div className="workspace-error" role="alert"><h3>{translate('vendors.supplierUnavailable')}</h3><p>{translate('vendors.supplierUnavailableHelp')}</p></div>}
      {drawerPhase === 'ready' && drawerRecord && <div className="operational-record"><p>{translate('vendors.recordHelp')}</p><dl className="record-facts">
        <div><dt>{translate('vendors.typeColumn')}</dt><dd>{drawerRecord.classifications.map(classificationLabel).join(' · ')}</dd></div>
        <div><dt>{translate('vendors.legalNameColumn')}</dt><dd>{drawerRecord.legal_name || translate('vendors.notProvided')}</dd></div>
        <div><dt>{translate('vendors.assetsColumn')}</dt><dd>{translate(drawerRecord.asset_count === 1 ? 'vendors.assetCount' : 'vendors.assetCountPlural', { count: drawerRecord.asset_count })}</dd></div>
        <div><dt>{translate('vendors.websiteColumn')}</dt><dd>{drawerRecord.website ? <a href={drawerRecord.website} rel="noreferrer" target="_blank">{drawerRecord.website}<ExternalLink size={13} aria-hidden="true" /></a> : translate('vendors.notProvided')}</dd></div>
      </dl><div className="operational-record-actions"><Link className="primary-button" to={`${organizationPath}/overview`}>{translate('vendors.openWorkspace')}</Link><Link className="secondary-button" to={`${organizationPath}/products`}>{translate('vendors.openProducts')}</Link></div></div>}
    </QuickDrawer>}
    <section className="content-section" aria-labelledby="vendor-list-heading">
      <div className="section-heading"><h2 id="vendor-list-heading">{translate('vendors.directory')}</h2><span>{countLabel}</span></div>
      <label className="site-search"><Search size={16} aria-hidden="true" /><span className="sr-only">{translate('vendors.search')}</span><input type="search" aria-label={translate('vendors.search')} value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} placeholder={translate('vendors.searchPlaceholder')} /></label>
      {visiblePhase === 'loading' && <p role="status">{translate('vendors.loading')}</p>}
      {visiblePhase === 'error' && <div className="workspace-error" role="alert"><h2>{translate('vendors.unavailable')}</h2><p>{translate('vendors.loadFailed')}</p></div>}
      {visiblePhase === 'ready' && result?.results.length === 0 && <p className="empty-state">{query.q ? translate('vendors.noMatches') : translate('vendors.empty')}</p>}
      {visiblePhase === 'ready' && result && result.results.length > 0 && <div className="people-table-wrap" role="group" aria-label={translate('vendors.itemsTable')} tabIndex={0}><table className="people-table"><thead><tr><th scope="col" aria-sort={query.ordering === 'name' ? 'ascending' : query.ordering === '-name' ? 'descending' : 'none'}><button type="button" onClick={() => sort('name')}>{translate('vendors.supplierColumn')}{sortIndicator('name')}</button></th><th scope="col">{translate('vendors.typeColumn')}</th><th scope="col">{translate('vendors.legalNameColumn')}</th><th scope="col" aria-sort={query.ordering === 'asset_count' ? 'ascending' : query.ordering === '-asset_count' ? 'descending' : 'none'}><button type="button" onClick={() => sort('asset_count')}>{translate('vendors.assetsColumn')}{sortIndicator('asset_count')}</button></th><th scope="col">{translate('vendors.websiteColumn')}</th></tr></thead><tbody>{result.results.map((vendor) => <tr key={vendor.id}><td data-label={translate('vendors.supplierColumn')}><button id={`vendor-row-${vendor.id}`} className="collection-name" type="button" onClick={() => openVendor(vendor)}>{vendor.name}</button></td><td data-label={translate('vendors.typeColumn')}>{vendor.classifications.map(classificationLabel).join(' · ')}</td><td data-label={translate('vendors.legalNameColumn')}>{vendor.legal_name || translate('vendors.notProvided')}</td><td data-label={translate('vendors.assetsColumn')}>{vendor.asset_count}</td><td data-label={translate('vendors.websiteColumn')}>{vendor.website ? <a href={vendor.website} rel="noreferrer" target="_blank">{translate('vendors.website')}<ExternalLink size={13} aria-hidden="true" /></a> : translate('vendors.notProvided')}</td></tr>)}</tbody></table></div>}
      {visiblePhase === 'ready' && result && result.count > result.page_size && <nav className="people-pagination" aria-label={translate('vendors.pages')}><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}><ChevronLeft size={15} aria-hidden="true" />{translate('pagination.previous')}</button><span>{translate('pagination.page', { page: result.page })}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>{translate('pagination.next')}<ChevronRight size={15} aria-hidden="true" /></button></nav>}
    </section>
  </>
}
