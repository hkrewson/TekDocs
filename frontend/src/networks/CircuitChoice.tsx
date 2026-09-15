import { useEffect, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { CircuitChoicePage, NetworksClient } from './api'
import { networkText as t } from './networkText'
export type CircuitChoiceValue = { id: string; name: string }
export function CircuitChoice({ kind, selected, providerId, workspace, client, onChange, onPermission }: {
  kind: 'providers' | 'contracts'; selected: CircuitChoiceValue | null; providerId?: string; workspace: WorkspaceContext; client: NetworksClient;
  onChange: (value: CircuitChoiceValue) => void; onPermission?: (allowed: boolean) => void
}) {
  const [draft, setDraft] = useState(''), [search, setSearch] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [response, setResponse] = useState<{ key: string; value?: CircuitChoicePage } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${kind}:${providerId}:${selected?.id}:${search}:${page}`
  const result = response?.key === key ? response : null
  useEffect(() => {
    const controller = new AbortController()
    client.circuitChoicePage(workspace, { choice: kind, q: search, page, page_size: 25, ...(providerId ? { provider_id: providerId } : {}), ...(selected ? { selected_id: selected.id } : {}) }, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setResponse({ key, value }); onPermission?.(value.can_view_contracts) } })
      .catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [client, workspace, kind, search, page, providerId, selected, key, reload, onPermission])
  const title = kind === 'providers' ? t('circuitProvider') : t('circuitContract')
  function find() { setSearch(draft); setPage(1) }
  return <section aria-label={title}><p>{selected?.name ?? t('circuitChoiceNone')}</p>
    <div className="collection-search"><input type="search" maxLength={240} aria-label={kind === 'providers' ? t('circuitProviderSearch') : t('circuitContractSearch')} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('circuitChoiceFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      {selected && !result.value.selected && <p role="alert">{t('circuitChoiceUnavailable')}</p>}
      <label>{title}<select value={result.value.results.some(row => row.id === selected?.id) ? selected!.id : ''} onChange={event => { const value = result.value?.results.find(row => row.id === event.target.value); if (value) onChange(value) }}><option value="">{t('circuitChoiceChoose')}</option>{result.value.results.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      {!result.value.count && <p>{t('circuitChoiceEmpty')}</p>}
      <CollectionPagination label={title} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
    </>}
  </section>
}
