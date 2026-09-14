import { useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { browserCollectionPreferences } from '../collections/preferences'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RecordActivity } from '../records/RecordActivity'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import type { WorkspaceContext } from '../workspaces/api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig, ChildRecordProps } from './NetworkChildCollection'
import type { NetworkRack, NetworksClient, RackWrite } from './api'
import { RackPlaceChoice } from './RackPlaceChoice'
import { RackDevices } from './RackDevices'
import { networkText as t } from './networkText'
const statuses = [{ value: 'planned', label: t('rackStatusPlanned') }, { value: 'active', label: t('rackStatusActive') }, { value: 'retired', label: t('rackStatusRetired') }]
const columns = ['name', 'site', 'location', 'status', 'unit_count', 'device_count'] as const
const labels = { name: t('name'), site: t('site'), location: t('location'), status: translate('collections.status'), unit_count: t('rackCapacity'), device_count: t('rackDeviceCount') }
const config: ChildCollectionConfig<NetworkRack, NetworkRack> = {
  key: 'racks', feature: 'network-racks', columns, labels, title: t('racks'), back: t('racksBack'), create: t('racksNew'), search: t('racksSearch'), order: t('racksOrder'), failed: t('racksFailed'), empty: t('racksEmpty'), count: (count) => t('racksCount', { count }), statuses, identity: (row) => row.name,
  value: (row, column) => column === 'site' ? row.site_name : column === 'location' ? row.location_name || translate('collections.missing') : column === 'status' ? statuses.find((item) => item.value === row.status)?.label ?? row.status : row[column as 'unit_count' | 'device_count'],
  load: (client, workspace, query, signal) => client.rackCollection(workspace, query, signal), read: (client, workspace, id, signal) => client.rackDetail(workspace, id, signal),
}
export function RackRegister({ workspace, client, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <div className="rack-register"><NetworkChildCollection standalone workspace={workspace} subnetId="" client={client} preferenceClient={preferenceClient} config={config} RecordComponent={RackRecord} /></div>
}
type Props = ChildRecordProps<NetworkRack> & { workspace: WorkspaceContext; client: NetworksClient }
function RackRecord({ record, workspace, client, canManage, onSaved, onReturn }: Props) {
  const [params] = useSearchParams()
  const location = useLocation()
  const requested = params.get('racks_section')
  const section = record && (requested === 'devices' || requested === 'history') ? requested : 'overview'
  const initial: RackWrite = { name: record?.name ?? '', site_id: record?.site_id ?? '', location_id: record?.location_id ?? null, unit_count: record?.unit_count ?? 42, status: record?.status ?? 'active' }
  const [form, setForm] = useState(initial)
  const [site, setSite] = useState(record ? { id: record.site_id, name: record.site_name } : null)
  const [place, setPlace] = useState(record?.location_id ? { id: record.location_id, name: record.location_name ?? t('assignmentUnavailable') } : null)
  const [editing, setEditing] = useState(!record)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const reset = () => { setForm(initial); setSite(record ? { id: record.site_id, name: record.site_name } : null); setPlace(record?.location_id ? { id: record.location_id, name: record.location_name ?? t('assignmentUnavailable') } : null) }
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); reset() }, editing)
  function href(id: string) { const next = new URLSearchParams(params); next.set('racks_section', id); return `${location.pathname}?${next}` }
  async function save() {
    if (busy) return
    if (!form.site_id) { setError(t('rackSiteRequired')); return }
    setBusy(true); setError('')
    try { const value = await (record ? client.updateRack(workspace, record.id, form) : client.createRack(workspace, form)); setEditing(false); onSaved(value) }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('racksSaveFailed')) }
    finally { setBusy(false) }
  }
  return <article className="record-page">
    {params.get('racks_full') === 'true' && <RecordHeader title={record?.name ?? t('racksNew')} recordId={record?.id ?? 'new'} section={section} />}
    {record && <RecordSections current={section} sections={['overview', 'devices', 'history'].map((id) => ({ id, label: id === 'devices' ? t('rackDevices') : translate(id === 'history' ? 'collections.history' : 'collections.overview'), href: href(id) }))} />}
    {section === 'devices' && record ? <RackDevices workspace={workspace} client={client} rackId={record.id} /> : section === 'history' && record ? <RecordActivity workspace={workspace} entityId={record.id} description={t('racksHistoryHelp')} emptyLabel={t('racksHistoryEmpty')} deniedLabel={t('racksHistoryDenied')} /> : <>
      {record && record.device_count > 0 && <p>{t('rackOccupied')}</p>}
      {error && <p role="alert">{error}</p>}
      {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
        <label>{t('name')}<input required maxLength={240} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <div className="field-grid"><label>{t('rackCapacity')}<input required type="number" min={1} max={100} value={Number.isNaN(form.unit_count) ? '' : form.unit_count} onChange={(event) => setForm({ ...form, unit_count: event.target.valueAsNumber })} /></label><label>{translate('collections.status')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as RackWrite['status'] })}>{statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
        <p>{t('rackSiteHelp')}</p>
        <RackPlaceChoice kind="site" selected={site} workspace={workspace} client={client} onChange={(value) => { if (value && value.id !== form.site_id) { setSite(value); setPlace(null); setForm({ ...form, site_id: value.id, location_id: null }) } }} />
        {form.site_id && <RackPlaceChoice key={form.site_id} kind="location" siteId={form.site_id} selected={place} workspace={workspace} client={client} onChange={(value) => { setPlace(value); setForm({ ...form, location_id: value?.id ?? null }) }} />}
        <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t('racksSave')}</button><button type="button" className="secondary-button" onClick={() => record ? attempt(() => setEditing(false)) : onReturn()}>{translate('common.cancel')}</button></div>
      </fieldset></form> : record ? <>
        <dl className="record-facts">{columns.filter((column) => column !== 'name').map((column) => <div key={column}><dt>{labels[column]}</dt><dd>{config.value(record, column)}</dd></div>)}</dl>
        {canManage && <button type="button" className="secondary-button" onClick={() => { reset(); setError(''); setEditing(true) }}>{t('racksEdit')}</button>}
      </> : <p>{t('racksDenied')}</p>}
    </>}
  </article>
}
