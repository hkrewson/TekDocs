import type { NetworkChoices, NetworkRecord, NetworkRecordWrite, NetworksClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'
import { useEffect, useState } from 'react'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import { RecordActivity } from '../records/RecordActivity'
import { networkText as t } from './networkText'
import { translate } from '../i18n/localization'

function NetworkEditor({ value, setValue, choices, busy, ready, cancel, save }: { value: NetworkRecordWrite; setValue: (value: NetworkRecordWrite) => void; choices: NetworkChoices | null; busy: boolean; ready: boolean; cancel: () => void; save: () => void }) {
  return <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); save() }}><fieldset disabled={busy}>
        <div className="field-grid">
          <label><span>{t('name')}</span><input autoFocus required maxLength={240} value={value.name} onChange={(event) => setValue({ ...value, name: event.target.value })} placeholder="Office LAN" /></label>
          <label><span>{t('location')}</span><select value={value.location_id ?? ''} onChange={(event) => setValue({ ...value, location_id: event.target.value || null })}><option value="">{t('unassigned')}</option>{choices?.locations.map((location) => {
            const site = choices.sites.find((item) => item.id === location.site_id)
            return <option key={location.id} value={location.id}>{site ? `${site.name} · ` : ''}{location.name}</option>
          })}</select></label>
          <label><span>{t('vlan')}</span><input type="number" min="1" max="4094" value={value.vlan ?? ''} onChange={(event) => setValue({ ...value, vlan: event.target.value ? Number(event.target.value) : null })} placeholder="20" /></label>
          <label><span>{t('cidr')}</span><input required value={value.cidr} onChange={(event) => setValue({ ...value, cidr: event.target.value })} placeholder="192.168.1.0/24" /><small>{t('gatewayHelp')}</small></label>
          <label><span>{t('primaryDns')}</span><input value={value.primary_dns ?? ''} onChange={(event) => setValue({ ...value, primary_dns: event.target.value || null })} placeholder="9.9.9.9" /></label>
          <label><span>{t('secondaryDns')}</span><input value={value.secondary_dns ?? ''} onChange={(event) => setValue({ ...value, secondary_dns: event.target.value || null })} placeholder="1.1.1.1" /></label>
        </div>
        <label className="network-range-toggle"><input type="checkbox" checked={value.use_full_range} onChange={(event) => setValue({ ...value, use_full_range: event.target.checked })} /><span>{t('fullRange')}</span></label>
        {!value.use_full_range && <div className="field-grid network-range-fields">
          <label><span>{t('rangeStart')}</span><input required value={value.range_start ?? ''} onChange={(event) => setValue({ ...value, range_start: event.target.value || null })} placeholder="192.168.1.100" /></label>
          <label><span>{t('rangeEnd')}</span><input required value={value.range_end ?? ''} onChange={(event) => setValue({ ...value, range_end: event.target.value || null })} placeholder="192.168.1.200" /></label>
        </div>}
        <label><span>{t('description')}</span><input maxLength={4000} value={value.description} onChange={(event) => setValue({ ...value, description: event.target.value })} placeholder="Guest Wi-Fi, voice, office LAN…" /></label>
        <label><span>{t('notes')}</span><textarea rows={5} maxLength={8000} value={value.notes} onChange={(event) => setValue({ ...value, notes: event.target.value })} /></label>
<div className="form-actions"><button className="primary-button" disabled={busy || !ready}>{busy ? translate('common.saving') : t('save')}</button><button className="secondary-button" type="button" onClick={cancel}>{translate('common.cancel')}</button></div></fieldset></form>
}

export function NetworkRecordView({ record, workspace, client, section, href, embedded, canManage, onSaved, onCancel }: { record: NetworkRecord | null; workspace: WorkspaceContext; client: NetworksClient; section: string; href: (section: string) => string; embedded: boolean; canManage: boolean; onSaved: (record: NetworkRecord) => void; onCancel: () => void }) {
  const [editing, setEditing] = useState(!record)
  const initial = record ? { name: record.name, location_id: record.location_id, description: record.description, vlan: record.vlan, cidr: record.cidr, use_full_range: record.use_full_range, range_start: record.use_full_range ? null : record.range_start, range_end: record.use_full_range ? null : record.range_end, primary_dns: record.primary_dns, secondary_dns: record.secondary_dns, notes: record.notes } : { name: '', location_id: null, description: '', vlan: null, cidr: '', use_full_range: true, range_start: null, range_end: null, primary_dns: null, secondary_dns: null, notes: '' }
  const [form, setForm] = useState<NetworkRecordWrite>(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [choices, setChoices] = useState<NetworkChoices | null>(null)
  const [choiceError, setChoiceError] = useState(false)
  const [reload, setReload] = useState(0)
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  useEffect(() => { if (!editing) return; const controller = new AbortController(); client.choices(workspace, controller.signal).then((value) => { if (!controller.signal.aborted) { setChoices(value); setChoiceError(false) } }).catch(() => { if (!controller.signal.aborted) setChoiceError(true) }); return () => controller.abort() }, [workspace, client, editing, reload])
  async function save() { if (!choices) return; setBusy(true); setError(''); try { const values = form.use_full_range ? { ...form, range_start: null, range_end: null } : form; const saved = record ? await client.updateNetwork(workspace, record.id, values) : await client.createNetwork(workspace, values); setEditing(false); onSaved(saved) } catch (caught) { setError(caught instanceof Error ? caught.message : t('saveFailed')) } finally { setBusy(false) } }
  const current = section === 'history' ? 'history' : 'overview'
  return <article className="record-page">
    {record && !embedded && <RecordHeader recordId={record.id} section={current} title={record.name} description={record.cidr} />}
    {record && <RecordSections current={current} sections={['overview', 'history'].map((id) => ({ id, label: translate(id === 'overview' ? 'collections.overview' : 'collections.history'), href: href(id) }))} />}
    {error && <p role="alert">{error}</p>}
    {current === 'history' && record ? <RecordActivity entityId={record.id} workspace={workspace} description={t('historyHelp')} emptyLabel={t('historyEmpty')} deniedLabel={t('historyDenied')} /> : editing ? <>
      <h2>{t(record ? 'edit' : 'new')}</h2><p>{t('gatewayHelp')}</p>
      {choiceError && <p role="alert">{t('choicesFailed')} <button type="button" onClick={() => setReload(reload + 1)}>{translate('collections.retry')}</button></p>}
      <NetworkEditor value={form} setValue={setForm} choices={choices} busy={busy} ready={Boolean(choices)} cancel={() => attempt(() => { if (record) setEditing(false); else onCancel() })} save={() => void save()} />
    </> : record && <>
      <p>{record.description || t('noDescription')}</p>
      <dl className="record-facts">{[[t('location'), [record.site_name, record.location_name].filter(Boolean).join(' · ') || t('unassigned')], [t('vlan'), String(record.vlan ?? '—')], [t('cidr'), record.cidr], [t('gateway'), record.gateway], [t('range'), `${record.range_start}–${record.range_end}`], [t('primaryDns'), record.primary_dns || '—'], [t('secondaryDns'), record.secondary_dns || '—']].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <h2>{t('notes')}</h2><p className="network-notes">{record.notes || t('noNotes')}</p>
      {canManage && <button className="secondary-button" type="button" onClick={() => { setForm(initial); setEditing(true) }}>{t('edit')}</button>}
    </>}
  </article>
}
