import { useEffect, useRef, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { ListResult, NetworksClient, WirelessNetwork } from './api'
import { networkText as t } from './networkText'

export function WirelessAssociation({ record, workspace, client, onSaved, onCancel, kind }: {
  kind: 'site' | 'vlan'; record: WirelessNetwork; workspace: WorkspaceContext; client: NetworksClient
  onSaved: (record: WirelessNetwork) => void; onCancel: () => void
}) {
  const field = kind === 'site' ? 'site_id' : 'vlan_id'
  const copy = (key: 'Change' | 'Help' | 'Selected' | 'None' | 'Remove' | 'Search' | 'Failed' | 'Results' | 'Choose' | 'Empty' | 'Save') => t(`${kind}Assignment${key}`)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])
  const [selected, setSelected] = useState({ id: record[field], label: (kind === 'site' ? record.site_name : record.vlan_name) || (record[field] ? t('assignmentUnavailable') : copy('None')) })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [result, setResult] = useState<{ key: string; value?: ListResult<{ id: string; name: string; identifier: string }> } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const dirty = selected.id !== record[field] && !saved
  const attempt = useUnsavedChanges(dirty, busy, onCancel, true)
  const key = `${workspace.kind}:${workspace.id}:${kind}:${search}:${page}`
  const choices = result?.key === key ? result : null
  useEffect(() => {
    const controller = new AbortController()
    client.assignmentChoices(workspace, kind, search, page, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setResult({ key, value }) })
      .catch(() => { if (!controller.signal.aborted) setResult({ key }) })
    return () => controller.abort()
  }, [workspace, client, kind, search, page, key, reload])
  async function save() {
    if (busy || !dirty) return
    setBusy(true); setError('')
    try {
      const value = await client.updateWireless(workspace, record.id, { [field]: selected.id })
      setSaved(true); onSaved(value); onCancel()
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('wirelessSaveFailed')) }
    finally { setBusy(false) }
  }
  return <section className="network-inline-editor" aria-label={copy('Change')}>
    <h3 ref={heading} tabIndex={-1}>{copy('Change')}</h3>
    <p>{copy('Help')}</p>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}>
      <p><strong>{copy('Selected')}</strong> {selected.label}</p>
      <button type="button" className="secondary-button" onClick={() => setSelected({ id: null, label: copy('None') })}>{copy('Remove')}</button>
      <form className="collection-search" onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get('parent-search'); setSearch(typeof value === 'string' ? value : ''); setPage(1) }}>
        <input type="search" name="parent-search" aria-label={copy('Search')} maxLength={253} />
        <button type="submit" className="secondary-button">{translate('collections.searchAction')}</button>
      </form>
      {!choices ? <p role="status">{translate('collections.loading')}</p> : !choices.value ? <p role="alert">{copy('Failed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        {choices.value.results.length ? <label>{copy('Results')}<select value={choices.value.results.some((item) => item.id === selected.id) ? selected.id ?? '' : ''} onChange={(event) => { const value = choices.value?.results.find((item) => item.id === event.target.value); if (value) setSelected({ id: value.id, label: [value.name, value.identifier].filter(Boolean).join(' · ') }) }}>
          <option value="">{copy('Choose')}</option>
          {choices.value.results.map((item) => <option key={item.id} value={item.id}>{[item.name, item.identifier].filter(Boolean).join(' · ')}</option>)}
        </select></label> : <p>{copy('Empty')}</p>}
        <CollectionPagination label={copy('Results')} page={page} pageSize={25} count={choices.value.count} hasMore={choices.value.has_more} onPageChange={setPage} />
      </>}
      <div className="form-actions"><button type="button" className="primary-button" disabled={!dirty} onClick={() => { void save() }}>{busy ? translate('common.saving') : copy('Save')}</button><button type="button" className="secondary-button" onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
    </fieldset>
  </section>
}
