import { useEffect, useRef, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { ListResult, NetworksClient, NetworkSummary, WirelessNetwork } from './api'
import { networkText as t } from './networkText'

export function WirelessParent({ record, workspace, client, onSaved, onCancel }: {
  record: WirelessNetwork; workspace: WorkspaceContext; client: NetworksClient
  onSaved: (record: WirelessNetwork) => void; onCancel: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])
  const [selected, setSelected] = useState({ id: record.subnet_id, label: record.subnet_cidr || t('unassignedNetwork') })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [result, setResult] = useState<{ key: string; value?: ListResult<NetworkSummary> } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const dirty = selected.id !== record.subnet_id && !saved
  const attempt = useUnsavedChanges(dirty, busy, onCancel, true)
  const key = `${workspace.kind}:${workspace.id}:${search}:${page}`
  const choices = result?.key === key ? result : null
  useEffect(() => {
    const controller = new AbortController()
    client.collection(workspace, { q: search, page, page_size: 25, ordering: 'name' }, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setResult({ key, value }) })
      .catch(() => { if (!controller.signal.aborted) setResult({ key }) })
    return () => controller.abort()
  }, [workspace, client, search, page, key, reload])
  async function save() {
    if (busy || !dirty) return
    setBusy(true); setError('')
    try {
      const value = await client.updateWireless(workspace, record.id, { subnet_id: selected.id })
      setSaved(true); onSaved(value); onCancel()
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('wirelessSaveFailed')) }
    finally { setBusy(false) }
  }
  return <section className="network-inline-editor" aria-label={t('changeParent')}>
    <h3 ref={heading} tabIndex={-1}>{t('changeParent')}</h3>
    <p>{t('parentHelp')}</p>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}>
      <p><strong>{t('selectedParent')}</strong> {selected.label}</p>
      <button type="button" className="secondary-button" onClick={() => setSelected({ id: null, label: t('unassignedNetwork') })}>{t('removeParent')}</button>
      <form className="collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('parent-search'); setSearch(typeof value === 'string' ? value : ''); setPage(1) }}>
        <input type="search" name="parent-search" aria-label={t('searchParent')} maxLength={253} />
        <button type="submit" className="secondary-button">{translate('collections.searchAction')}</button>
      </form>
      {!choices ? <p role="status">{translate('collections.loading')}</p> : !choices.value ? <p role="alert">{t('parentChoicesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        {choices.value.results.length ? <label>{t('parentResults')}<select value={choices.value.results.some((item) => item.id === selected.id) ? selected.id ?? '' : ''} onChange={(event) => { const value = choices.value?.results.find((item) => item.id === event.target.value); if (value) setSelected({ id: value.id, label: `${value.name} · ${value.cidr}` }) }}>
          <option value="">{t('chooseParent')}</option>
          {choices.value.results.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.cidr}</option>)}
        </select></label> : <p>{t('parentChoicesEmpty')}</p>}
        <CollectionPagination label={t('parentResults')} page={page} pageSize={25} count={choices.value.count} hasMore={choices.value.has_more} onPageChange={setPage} />
      </>}
      <div className="form-actions"><button type="button" className="primary-button" disabled={!dirty} onClick={() => { void save() }}>{busy ? translate('common.saving') : t('saveParent')}</button><button type="button" className="secondary-button" onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
    </fieldset>
  </section>
}
