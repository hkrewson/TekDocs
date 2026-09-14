import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient, NetworkQuery } from './api'
import { networkText as t } from './networkText'

export function RelatedNetworks({ kind, recordId, workspace, client }: { kind: 'vlans' | 'vrfs'; recordId: string; workspace: WorkspaceContext; client: NetworksClient }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const prefix = `${kind}_networks_`
  const requested = Number(params.get(`${prefix}page`))
  const page = Number.isSafeInteger(requested) && requested > 0 ? requested : 1
  const size = Number(params.get(`${prefix}size`))
  const pageSize = [25, 50, 100].includes(size) ? size : 25
  const queryText = JSON.stringify({ q: params.get(`${prefix}q`) ?? '', page, page_size: pageSize, ordering: 'name', [kind === 'vlans' ? 'vlan_id' : 'vrf_id']: recordId })
  const query = useMemo(() => JSON.parse(queryText) as NetworkQuery, [queryText])
  const key = `${workspace.kind}:${workspace.id}:${queryText}`
  const [response, setResponse] = useState<{ key: string; value?: Awaited<ReturnType<NetworksClient['collection']>> } | null>(null)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    client.collection(workspace, query, controller.signal).then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, query, key, reload])
  function browse(values: Record<string, string>) {
    const next = new URLSearchParams(params)
    next.delete(`${prefix}page`)
    for (const [name, value] of Object.entries(values)) { if (value) next.set(`${prefix}${name}`, value); else next.delete(`${prefix}${name}`) }
    setParams(next)
  }
  function href(id: string) {
    const next = new URLSearchParams(params)
    for (const name of ['view', 'preview', 'create', 'section', 'address', 'wireless', 'history_page']) next.delete(name)
    next.set('record', id)
    return `${location.pathname}?${next}`
  }
  const result = response?.key === key ? response : null
  return <section aria-label={t('heading')}>
    <p>{t('relatedHelp')}</p>
    <form className="collection-search" key={query.q} onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('q'); browse({ q: typeof value === 'string' ? value : '' }) }}>
      <input type="search" name="q" maxLength={240} defaultValue={query.q} aria-label={t('relatedSearch')} />
      <button type="submit" className="secondary-button">{translate('collections.searchAction')}</button>
    </form>
    <label>{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => browse({ size: event.target.value })}>{[25, 50, 100].map((value) => <option key={value}>{value}</option>)}</select></label>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('relatedFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      {result.value.results.length ? <dl className="record-facts">{result.value.results.map((row) => <div key={row.id}><dt><Link to={href(row.id)}>{row.name}</Link></dt><dd>{t('cidr')}: {row.cidr}</dd></div>)}</dl> : <p>{t('relatedEmpty')}</p>}
      <CollectionPagination label={t('heading')} page={page} pageSize={pageSize} count={result.value.count} hasMore={result.value.has_more} onPageChange={(value) => browse({ page: String(value) })} />
    </>}
  </section>
}
