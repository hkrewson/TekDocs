import { useEffect, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { ListResult, NetworksClient } from './api'
import { networkText as t } from './networkText'
export type HandoffChoice = { id: string; name: string }
export function HandoffPlacementChoice({ kind, parentId, selected, workspace, client, onChange }: {
  kind: 'site' | 'location' | 'device' | 'interface'; parentId?: string; selected: HandoffChoice | null;
  workspace: WorkspaceContext; client: NetworksClient; onChange: (value: HandoffChoice | null) => void
}) {
  const [draft, setDraft] = useState(''), [search, setSearch] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0)
  const [response, setResponse] = useState<{ key: string; value?: ListResult<HandoffChoice> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${kind}:${parentId}:${search}:${page}`
  const result = response?.key === key ? response : null
  const title = kind === 'site' || kind === 'location' ? t(kind) : t(kind === 'device' ? 'circuitDevice' : 'circuitInterface')
  useEffect(() => {
    const controller = new AbortController()
    const query = { q: search, page, page_size: 25, ordering: 'name' }
    const request = kind === 'site' ? client.assignmentChoices(workspace, 'site', search, page, controller.signal)
      : kind === 'location' ? client.locationChoices(workspace, parentId!, search, page, controller.signal)
      : kind === 'device' ? client.deviceCollection(workspace, query, controller.signal)
      : client.interfaceCollection(workspace, { ...query, device_id: parentId! }, controller.signal)
    request.then(value => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [client, workspace, kind, parentId, search, page, key, reload])
  function find() { setSearch(draft); setPage(1) }
  return <section aria-label={title}><p>{selected?.name ?? t('circuitMissing')}</p>
    <div className="collection-search"><input type="search" maxLength={240} aria-label={t(`handoffSearch_${kind}`)} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('circuitChoiceFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <><label>{title}<select value={result.value.results.some(row => row.id === selected?.id) ? selected!.id : ''} onChange={event => { const value = result.value?.results.find(row => row.id === event.target.value); if (value) onChange(value) }}><option value="">{t('circuitChoiceChoose')}</option>{result.value.results.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>{!result.value.count && <p>{t('circuitChoiceEmpty')}</p>}<CollectionPagination label={title} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} /></>}
    <button type="button" className="secondary-button" disabled={!selected} onClick={() => onChange(null)}>{t(`handoffClear_${kind}`)}</button>
  </section>
}
