import { useEffect, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworkDevice, NetworksClient } from './api'
import { networkText as t } from './networkText'

type Choice = { id: string; name: string }

export function DeviceHardware({ record, workspace, client, onSaved }: {
  record: NetworkDevice
  workspace: WorkspaceContext
  client: NetworksClient
  onSaved: (record: NetworkDevice) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(''), [search, setSearch] = useState(''), [page, setPage] = useState(1)
  const [reload, setReload] = useState(0), [selected, setSelected] = useState<Choice | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [response, setResponse] = useState<{ key: string; value?: Awaited<ReturnType<NetworksClient['hardwareAssetChoices']>> } | null>(null)
  const key = `${workspace.kind}:${workspace.id}:${search}:${page}`
  const result = response?.key === key ? response : null
  function reset() { setEditing(false); setDraft(''); setSearch(''); setPage(1); setSelected(null); setError('') }
  const attempt = useUnsavedChanges(editing && Boolean(draft || search || selected), busy, reset, editing || busy)

  useEffect(() => {
    if (!editing) return
    const controller = new AbortController()
    client.hardwareAssetChoices(workspace, search, page, controller.signal).then((value) => {
      if (!controller.signal.aborted) setResponse({ key, value })
    }).catch(() => { if (!controller.signal.aborted) setResponse({ key }) })
    return () => controller.abort()
  }, [workspace, client, editing, search, page, reload, key])

  function find() { setSearch(draft); setPage(1) }
  async function save() {
    if (busy) return
    if (!selected) { setError(t('deviceHardwareRequired')); return }
    setBusy(true); setError('')
    try {
      const value = await client.rebindDeviceHardware(
        workspace, record.id, selected.id, record.hardware_asset_id,
      )
      reset(); onSaved(value)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t('deviceHardwareSaveFailed'))
    } finally { setBusy(false) }
  }

  const choices = result?.value?.results ?? []
  return <section aria-labelledby="device-hardware-heading">
    <h3 id="device-hardware-heading">{t('deviceHardwareHeading')}</h3>
    <dl className="record-facts"><div><dt>{t('deviceHardwareCurrent')}</dt><dd>{record.hardware_asset_name ?? t('rackDeviceAssetUnavailable')}</dd></div></dl>
    {!editing ? <button type="button" className="secondary-button" onClick={() => setEditing(true)}>{t('deviceHardwareReplace')}</button> : <>
      <p>{t('deviceHardwareHelp')}</p>
      {error && <p role="alert">{error}</p>}
      <p>{t('deviceHardwareSelected')}: <strong>{selected?.name ?? t('deviceHardwareChoose')}</strong></p>
      <div className="collection-search"><input type="search" maxLength={240} aria-label={t('deviceHardwareSearch')} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); find() } }} /><button type="button" className="secondary-button" onClick={find}>{translate('collections.searchAction')}</button></div>
      {!result ? <p role="status">{translate('collections.loading')}</p> : !result.value ? <p role="alert">{t('deviceHardwareChoicesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p> : <>
        {choices.length || selected ? <label>{t('deviceHardwareResults')}<select value={selected?.id ?? ''} onChange={(event) => { const row = choices.find((item) => item.id === event.target.value); if (row) setSelected(row); else setSelected(null) }}><option value="">{t('deviceHardwareChoose')}</option>{selected && !choices.some((row) => row.id === selected.id) && <option value={selected.id}>{selected.name}</option>}{choices.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label> : <p>{t('deviceHardwareEmpty')}</p>}
        <CollectionPagination label={t('deviceHardwareResults')} page={page} pageSize={25} count={result.value.count} hasMore={result.value.has_more} onPageChange={setPage} />
      </>}
      <div className="form-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? translate('common.saving') : t('deviceHardwareConfirm')}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => attempt(reset)}>{translate('common.cancel')}</button></div>
    </>}
  </section>
}
