import { useEffect, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { ListResult, NetworksClient } from './api'
import { networkText as t } from './networkText'
export function DeviceChoice({ kind, selected, onChange, workspace, client }: {
  kind: 'asset' | 'rack'; selected: { id: string; name: string } | null; onChange: (value: { id: string; name: string }) => void; workspace: WorkspaceContext; client: NetworksClient
}) {
  const [search, setSearch] = useState(''), [draft, setDraft] = useState('')
  const [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [response, setResponse] = useState<{ key: string; value?: ListResult<{ id: string; name: string }> } | null>(null)
  const prefix = kind === 'asset' ? 'deviceAsset' : 'deviceRack'
  const key = `${workspace.kind}:${workspace.id}:${kind}:${search}:${page}`
  const result = response?.key === key ? response : null
  useEffect(() => {
    const controller = new AbortController()
    const request = kind === 'asset' ? client.hardwareAssetChoices(workspace, search, page, controller.signal) : client.rackCollection(workspace, { q: search, page, page_size: 25, ordering: 'name' }, controller.signal)
    request.then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, kind, search, page, reload, key])
  function find() { setSearch(draft); setPage(1) }
  return <section aria-label={t(`${prefix}Results`)}>
    <p>{t(`${prefix}Selected`)}: <strong>{selected?.name ?? t(`${prefix}Choose`)}</strong></p>
    <div className="collection-search"><input type="search" maxLength={240} aria-label={t(`${prefix}Search`)} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('rackChoicesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      {result.value.results.length ? <label>{t(`${prefix}Results`)}<select value={result.value.results.some((row) => row.id === selected?.id) ? selected!.id : ''} onChange={(event) => { const row = result.value?.results.find((item) => item.id === event.target.value); if (row) onChange(row) }}><option value="">{t(`${prefix}Choose`)}</option>{result.value.results.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label> : <p>{t('rackChoicesEmpty')}</p>}
      <CollectionPagination label={t(`${prefix}Results`)} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
    </>}
  </section>
}
