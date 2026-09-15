import { useEffect, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { AddressSummary, ListResult, NetworksClient } from './api'
import { networkText as t } from './networkText'
export function DNSIPChoice({ selectedId, family, onChange, workspace, client }: {
  selectedId: string | null; family: 4 | 6; onChange: (value: AddressSummary | null) => void; workspace: WorkspaceContext; client: NetworksClient
}) {
  const [search, setSearch] = useState(''), [draft, setDraft] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [response, setResponse] = useState<{ key: string; value?: ListResult<AddressSummary> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${search}:${page}`
  const result = response?.key === key ? response : null
  useEffect(() => {
    const controller = new AbortController()
    client.addressCollection(workspace, { q: search, page, page_size: 25, ordering: 'name' }, controller.signal).then(value => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, search, page, reload, key])
  function find() { setSearch(draft); setPage(1) }
  return <section aria-label={t('dnsIP')}>
    <p>{selectedId ? t('dnsIPLinked') : t('dnsIPNone')}</p>
    {selectedId && <button type="button" className="secondary-button" onClick={() => onChange(null)}>{t('dnsIPClear')}</button>}
    <div className="collection-search"><input type="search" maxLength={253} aria-label={t('dnsIPSearch')} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('dnsIPFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      <label>{t('dnsIP')}<select value={result.value.results.some(row => row.id === selectedId) ? selectedId! : ''} onChange={event => { const row = result.value?.results.find(item => item.id === event.target.value); if (row) onChange(row) }}><option value="">{t('dnsIPChoose')}</option>{result.value.results.map(row => <option key={row.id} value={row.id} disabled={row.address_family !== family}>{row.address}</option>)}</select></label>
      <CollectionPagination label={t('dnsIP')} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
    </>}
  </section>
}
