import { useEffect, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { ChildRecordProps } from './NetworkChildCollection'
import { HandoffPlacementChoice } from './HandoffPlacementChoice'
import type { HandoffChoice } from './HandoffPlacementChoice'
import type { HandoffDetail, HandoffWrite, NetworksClient } from './api'
import { networkText as t } from './networkText'
const sides = ['a', 'z'] as const
const media = ['copper', 'fiber', 'coax', 'wireless', 'virtual', 'other'] as const
export function HandoffView({ record, onReturn, workspace, client, canManage, parentId, onSaved }: ChildRecordProps<HandoffDetail> & { workspace: WorkspaceContext; client: NetworksClient; parentId: string }) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [editing, setEditing] = useState<'details' | 'placement' | null>(record ? null : 'details')
  useEffect(() => { if (!editing) heading.current?.focus() }, [record?.id, editing])
  if (editing && canManage) return <HandoffEditor key={editing} record={record} workspace={workspace} client={client} parentId={parentId} mode={editing} onSaved={onSaved} onCancel={() => { if (record) setEditing(null); else onReturn() }} />
  if (!record) return <p>{t('circuitUnavailable')}</p>
  const facts = { side: t('circuitSide'), media: t('circuitMedia'), connector: t('circuitConnector'), provider_reference: t('circuitReference'), site_name: t('site'), location_name: t('location'), device_name: t('circuitDevice'), interface_name: t('circuitInterface') }
  return <section><button type="button" className="secondary-button" onClick={onReturn}>{t('circuitHandoffsBack')}</button><h2 ref={heading} tabIndex={-1}>{record.name}</h2><dl className="record-facts">{(Object.keys(facts) as (keyof typeof facts)[]).map(field => <div key={field}><dt>{facts[field]}</dt><dd>{field === 'side' ? t(`circuitValue_${record.side}`) : field === 'media' ? t(`circuitValue_${record.media}`) : record[field] || t('circuitMissing')}</dd></div>)}</dl><p className="network-notes">{record.description || t('noDescription')}</p>{canManage && <div className="form-actions"><button type="button" className="secondary-button" onClick={() => setEditing('details')}>{t('handoffEdit')}</button><button type="button" className="secondary-button" onClick={() => setEditing('placement')}>{t('handoffPlacementEdit')}</button></div>}</section>
}
function HandoffEditor({ record, workspace, client, parentId, mode, onSaved, onCancel }: {
  record: HandoffDetail | null; workspace: WorkspaceContext; client: NetworksClient; parentId: string; mode: 'details' | 'placement'; onSaved: (record: HandoffDetail) => void; onCancel: () => void
}) {
  const initial = { name: record?.name ?? '', side: record?.side ?? 'a', media: record?.media ?? 'fiber', connector: record?.connector ?? '', provider_reference: record?.provider_reference ?? '', description: record?.description ?? '' }
  const [form, setForm] = useState(initial)
  function choice(kind: 'site' | 'location' | 'device' | 'interface'): HandoffChoice | null { const id = record?.[`${kind}_id`]; return id ? { id, name: record?.[`${kind}_name`] ?? id } : null }
  const initialPlace = { site: choice('site'), location: choice('location'), device: choice('device'), interface: choice('interface') }
  const [place, setPlace] = useState(initialPlace), [busy, setBusy] = useState(false), [complete, setComplete] = useState(false), [error, setError] = useState('')
  const dirty = JSON.stringify(form) !== JSON.stringify(initial) || JSON.stringify(place) !== JSON.stringify(initialPlace)
  const attempt = useUnsavedChanges(dirty && !complete, busy, onCancel, !complete)
  async function save() {
    if (busy) return
    setBusy(true); setError('')
    const placement = { site_id: place.site?.id ?? null, location_id: place.location?.id ?? null, device_id: place.device?.id ?? null, interface_id: place.interface?.id ?? null }
    try {
      const saved = record ? await client.updateCircuitHandoff(workspace, parentId, record.id, mode === 'placement' ? placement : form)
        : await client.createCircuitHandoff(workspace, parentId, { ...form, ...placement } satisfies HandoffWrite)
      setComplete(true); onSaved(saved); if (record) onCancel()
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('handoffSaveFailed')) } finally { setBusy(false) }
  }
  return <form className="network-inline-editor" onSubmit={event => { event.preventDefault(); void save() }}><h2>{!record ? t('circuitHandoffNew') : mode === 'placement' ? t('handoffPlacementEdit') : t('handoffEdit')}</h2>{error && <p role="alert">{error}</p>}<fieldset disabled={busy}>
    {mode === 'details' ? <><div className="field-grid"><label>{t('name')}<input required maxLength={240} value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} /></label><label>{t('circuitSide')}<select value={form.side} onChange={event => setForm({ ...form, side: event.target.value as HandoffDetail['side'] })}>{sides.map(value => <option key={value} value={value}>{t(`circuitValue_${value}`)}</option>)}</select></label><label>{t('circuitMedia')}<select value={form.media} onChange={event => setForm({ ...form, media: event.target.value as HandoffDetail['media'] })}>{media.map(value => <option key={value} value={value}>{t(`circuitValue_${value}`)}</option>)}</select></label><label>{t('circuitConnector')}<input maxLength={120} value={form.connector} onChange={event => setForm({ ...form, connector: event.target.value })} /></label><label>{t('circuitReference')}<input maxLength={240} value={form.provider_reference} onChange={event => setForm({ ...form, provider_reference: event.target.value })} /></label></div><label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={event => setForm({ ...form, description: event.target.value })} /></label>{!record && <p>{t('handoffCreateHelp')}</p>}</> : <>
      <p>{t('handoffPlacementHelp')}</p>
      <HandoffPlacementChoice kind="site" selected={place.site} workspace={workspace} client={client} onChange={value => setPlace(value?.id === place.site?.id ? { ...place, site: value } : { site: value, location: null, device: null, interface: null })} />
      {place.site && <HandoffPlacementChoice key={place.site.id} kind="location" parentId={place.site.id} selected={place.location} workspace={workspace} client={client} onChange={value => setPlace({ ...place, location: value })} />}
      <HandoffPlacementChoice kind="device" selected={place.device} workspace={workspace} client={client} onChange={value => setPlace({ ...place, device: value, interface: value?.id === place.device?.id ? place.interface : null })} />
      {place.device && <HandoffPlacementChoice key={place.device.id} kind="interface" parentId={place.device.id} selected={place.interface} workspace={workspace} client={client} onChange={value => setPlace({ ...place, interface: value })} />}
    </>}
    <div className="form-actions"><button className="primary-button" disabled={Boolean(record && !dirty)}>{busy ? translate('common.saving') : t('handoffSave')}</button><button type="button" className="secondary-button" onClick={() => attempt(onCancel)}>{translate('common.cancel')}</button></div>
  </fieldset></form>
}
