import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { CollectionPagination } from '../CollectionPagination'
import { FilterMenu } from '../FilterMenu'
import { CollectionTable } from '../collections/CollectionTable'
import { ColumnChooser } from '../collections/ColumnChooser'
import { browserCollectionPreferences, defaultPreferences } from '../collections/preferences'
import type { CollectionPreferences } from '../collections/preferences'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetBoxObjectType, NetBoxReference, NetBoxReferenceQuery, NetBoxReferenceResult, NetworksClient } from './api'

const columns = ['name', 'type', 'object', 'observation'] as const
const labels = { name: translate('netbox.record'), type: translate('netbox.type'), object: translate('netbox.objectId'), observation: translate('netbox.observation') }
const objectTypes: NetBoxObjectType[] = ['dcim.device', 'ipam.prefix']
const typeLabel: Partial<Record<NetBoxObjectType, string>> = {
  'dcim.device': translate('netbox.type.device'),
  'ipam.prefix': translate('netbox.type.prefix'),
}
const orderingFields = { name: 'name', type: 'object_type', object: 'object_id', observation: 'observed' } as const

function apiOrdering(value: string): NetBoxReferenceQuery['ordering'] {
  const descending = value.startsWith('-')
  const column = value.replace(/^-/, '') as keyof typeof orderingFields
  return `${descending ? '-' : ''}${orderingFields[column] ?? 'name'}`
}

function tableOrdering(value: NetBoxReferenceQuery['ordering']) {
  const descending = value.startsWith('-')
  const field = value.replace(/^-/, '')
  const column = Object.entries(orderingFields).find(([, api]) => api === field)?.[0] ?? 'name'
  return `${descending ? '-' : ''}${column}`
}

export function NetworkNetBox({ workspace, client, preferenceClient = browserCollectionPreferences }: {
  workspace: WorkspaceContext; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences
}) {
  const [params, setParams] = useSearchParams()
  const [preferences, setPreferences] = useState<CollectionPreferences>(() => defaultPreferences(columns))
  const [response, setResponse] = useState<{ key: string; result?: NetBoxReferenceResult } | null>(null)
  const [reload, setReload] = useState(0)
  const [error, setError] = useState('')
  const requestedPage = Number(params.get('netbox_page') ?? 1)
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const pageSize = [25, 50, 100].includes(Number(params.get('netbox_size'))) ? Number(params.get('netbox_size')) as 25 | 50 | 100 : preferences.page_size
  const query = useMemo<NetBoxReferenceQuery>(() => ({
    q: params.get('netbox_q') ?? '',
    ...(params.get('netbox_type') ? { object_type: params.get('netbox_type') as NetBoxObjectType } : {}),
    ordering: (params.get('netbox_order') ?? 'name') as NetBoxReferenceQuery['ordering'], page, page_size: pageSize,
  }), [params, page, pageSize])
  const key = `${workspace.kind}:${workspace.id}:${JSON.stringify(query)}`
  const result = response?.key === key ? response.result : null

  useEffect(() => {
    const controller = new AbortController()
    preferenceClient.load(workspace, 'network-netbox', columns, controller.signal).then((value) => {
      if (!controller.signal.aborted) setPreferences(value)
    }).catch(() => { if (!controller.signal.aborted) setPreferences(defaultPreferences(columns)) })
    return () => controller.abort()
  }, [preferenceClient, workspace])

  useEffect(() => {
    const controller = new AbortController()
    client.netBoxReferenceCollection(workspace, query, controller.signal).then((value) => {
      if (!controller.signal.aborted) setResponse({ key, result: value })
    }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [client, key, query, reload, workspace])

  function browse(values: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [name, value] of Object.entries(values)) {
      if (value) next.set(name, value)
      else next.delete(name)
    }
    const collectionChanged = Object.keys(values).some((name) => ['netbox_q', 'netbox_type', 'netbox_order', 'netbox_size'].includes(name))
    if (collectionChanged && !('netbox_page' in values)) next.delete('netbox_page')
    setParams(next)
  }
  const tableOrder = tableOrdering(query.ordering)
  return <section className="content-section netbox-register" aria-labelledby="netbox-heading">
    <div className="section-heading"><div><h1 id="netbox-heading" tabIndex={-1}>{translate('netbox.heading')}</h1><p>{translate('netbox.intro')}</p></div></div>
    {error && <p role="alert">{error}</p>}
    <div className="collection-toolbar">
      <form key={query.q} className="collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ netbox_q: typeof value === 'string' ? value.trim() : '' }) }}><input name="q" type="search" defaultValue={query.q} aria-label={translate('netbox.search')} /><button className="secondary-button" type="submit">{translate('collections.searchAction')}</button></form>
      <FilterMenu groups={[{ kind: 'choices', label: translate('netbox.type'), value: query.object_type ?? '', choices: [{ value: '', label: translate('collections.all') }, ...objectTypes.map((value) => ({ value, label: typeLabel[value] ?? value }))], onChange: (value) => browse({ netbox_type: value || null }) }]} activeCount={Number(Boolean(query.object_type))} onClear={() => browse({ netbox_type: null })} />
      <ColumnChooser preferences={preferences} labels={labels} onSave={async (selected) => { try { setPreferences(await preferenceClient.save(workspace, 'network-netbox', { columns: selected, page_size: pageSize })); setError('') } catch { setError(translate('collections.preferenceFailed')) } }} onReset={async () => { try { setPreferences(await preferenceClient.reset(workspace, 'network-netbox')); setError(''); browse({ netbox_page: null, netbox_size: null }) } catch { setError(translate('collections.preferenceFailed')) } }} />
      <label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => { const size = Number(event.target.value) as 25 | 50 | 100; browse({ netbox_size: String(size) }); void preferenceClient.save(workspace, 'network-netbox', { columns: preferences.columns, page_size: size }).then(setPreferences).catch(() => setError(translate('collections.preferenceFailed'))) }}>{[25, 50, 100].map((size) => <option key={size}>{size}</option>)}</select></label>
    </div>
    {query.object_type && <div className="collection-active-filters"><button type="button" className="row-action" onClick={() => browse({ netbox_type: null })}>{translate('netbox.type')}: {typeLabel[query.object_type] ?? query.object_type} ×</button></div>}
    <label className="collection-mobile-order">{translate('collections.ordering')}<select value={tableOrder} onChange={(event) => browse({ netbox_order: apiOrdering(event.target.value) })}>{columns.flatMap((column) => [<option key={column} value={column}>{labels[column]} ↑</option>, <option key={`-${column}`} value={`-${column}`}>{labels[column]} ↓</option>])}</select></label>
    {!response || response.key !== key ? <p role="status">{translate('netbox.loading')}</p> : !result ? <p role="alert">{translate('netbox.failed')} <button type="button" onClick={() => setReload((value) => value + 1)}>{translate('collections.retry')}</button></p> : <>
      <p>{translate('netbox.count', { count: result.count })}</p>
      {result.results.length === 0 ? <p className="empty-state">{query.q || query.object_type ? translate('netbox.noMatches') : translate('netbox.empty')}</p> : <CollectionTable<NetBoxReference & { name: string }> label={translate('netbox.table')} rows={result.results.map((reference) => ({ ...reference, name: reference.entity_name }))} selectable={false} selected={new Set()} onSelection={() => {}} ordering={tableOrder} onOrder={(value) => browse({ netbox_order: apiOrdering(value) })} columns={preferences.columns.map((column) => ({ id: column, label: labels[column as keyof typeof labels], render: (reference) => column === 'name' ? <strong>{reference.entity_name}</strong> : column === 'type' ? typeLabel[reference.object_type] ?? reference.object_type : column === 'object' ? String(reference.object_id) : reference.last_observed_at ? translate('netbox.observed') : translate('netbox.notObserved') }))} />}
      <CollectionPagination label={translate('netbox.table')} page={page} pageSize={pageSize} count={result.count} hasMore={result.has_more} onPageChange={(next) => browse({ netbox_page: String(next) })} />
    </>}
  </section>
}
