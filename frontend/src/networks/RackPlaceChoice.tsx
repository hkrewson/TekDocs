import { useEffect, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { ListResult, NetworksClient } from './api'
import { networkText as t } from './networkText'

type Choice = { id: string; name: string; identifier?: string }
export function RackPlaceChoice({ kind, siteId, selected, onChange, workspace, client }: {
  kind: 'site' | 'location'; siteId?: string; selected: Choice | null; onChange: (value: Choice | null) => void
  workspace: WorkspaceContext; client: NetworksClient
}) {
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState('')
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [response, setResponse] = useState<{ key: string; value?: ListResult<Choice> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${kind}:${siteId}:${search}:${page}`
  const result = response?.key === key ? response : null
  const label = t(kind === 'site' ? 'rackSiteResults' : 'rackLocationResults')
  useEffect(() => {
    const controller = new AbortController()
    const request = kind === 'site' ? client.assignmentChoices(workspace, 'site', search, page, controller.signal) : client.locationChoices(workspace, siteId!, search, page, controller.signal)
    request.then((value) => { if (!controller.signal.aborted) setResponse({ key, value }) }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, kind, siteId, search, page, key, reload])
  function find() { setSearch(draft); setPage(1) }
  return <section aria-label={label}>
    <p>{t(kind === 'site' ? 'rackSelectedSite' : 'rackSelectedLocation')}: <strong>{selected?.name ?? t(kind === 'site' ? 'rackChooseSite' : 'rackNoLocation')}</strong></p>
    <div className="collection-search"><input type="search" aria-label={t(kind === 'site' ? 'rackSearchSites' : 'rackSearchLocations')} maxLength={240} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
    {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('rackChoicesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
      {result.value.results.length ? <label>{label}<select value={result.value.results.some((row) => row.id === selected?.id) ? selected!.id : ''} onChange={(event) => { const row = result.value?.results.find((item) => item.id === event.target.value); if (row) onChange(row) }}>
        <option value="">{t(kind === 'site' ? 'rackChooseSite' : 'rackChooseLocation')}</option>
        {result.value.results.map((row) => <option key={row.id} value={row.id}>{[row.name, row.identifier].filter(Boolean).join(' · ')}</option>)}
      </select></label> : <p>{t('rackChoicesEmpty')}</p>}
      <CollectionPagination label={label} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
    </>}
    {kind === 'location' && <button type="button" className="secondary-button" onClick={() => onChange(null)}>{t('rackClearLocation')}</button>}
  </section>
}
