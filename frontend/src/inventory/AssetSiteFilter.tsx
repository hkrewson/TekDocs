import { useEffect, useState } from 'react'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import { browserAssetSiteChoices } from './api'
import type { AssetSiteResult } from './api'

export function AssetSiteFilter({ workspace, value, onChange, client = browserAssetSiteChoices }: {
  workspace: WorkspaceContext; value: string; onChange: (id: string) => void; client?: typeof browserAssetSiteChoices
}) {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const key = JSON.stringify([workspace.id, search, page, reload])
  const [response, setResponse] = useState<{ key: string; value: string; result: AssetSiteResult } | null>(null)
  const [failed, setFailed] = useState('')
  const result = response?.key === key ? response.result : null
  useEffect(() => {
    const controller = new AbortController()
    client(workspace, search, page, value, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setResponse({ key, value, result }); setFailed('') }
    }).catch(() => { if (!controller.signal.aborted) setFailed(key) })
    return () => controller.abort()
  }, [workspace, search, page, value, client, key])
  return <div className="asset-site-filter">
    <p>{translate('collections.siteChoicesHelp')}</p>
    <form onSubmit={(event) => { event.preventDefault(); const term = new FormData(event.currentTarget).get('site-search'); setSearch(typeof term === 'string' ? term : ''); setPage(1) }}>
      <label>{translate('collections.searchSites')}<input name="site-search" type="search" aria-label={translate('collections.searchSites')} /></label>
      <button type="submit" className="secondary-button">{translate('collections.searchAction')}</button>
    </form>
    <label><input type="radio" name="asset-site" checked={!value} onChange={() => onChange('')} />{translate('collections.all')}</label>
    {failed === key ? <p role="alert">{translate('collections.siteChoicesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : !result ? <p role="status">{translate('collections.loading')}</p> : <>
      {value && response?.value === value && !result.selected && <p role="status">{translate('collections.siteUnavailable')}</p>}
      <div className="asset-site-choices" role="radiogroup" aria-label={translate('collections.site')}>
        {result.results.map((site) => <label key={site.id}><input type="radio" name="asset-site" checked={value === site.id} onChange={() => onChange(site.id)} /><span>{site.name}</span></label>)}
      </div>
      {!result.count && <p>{translate('collections.noSites')}</p>}
      <div className="form-actions"><button type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>{translate('pagination.previous')}</button><span>{page}</span><button type="button" disabled={!result.has_more} onClick={() => setPage(page + 1)}>{translate('pagination.next')}</button></div>
    </>}
  </div>
}
