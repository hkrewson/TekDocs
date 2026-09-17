import { createContext, useContext, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { browserCollectionPreferences } from '../collections/preferences'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RecordActivity } from '../records/RecordActivity'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import type { WorkspaceContext } from '../workspaces/api'
import { browserRelationshipsClient } from '../relationships/api'
import type { RelationshipsClient } from '../relationships/api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig, ChildRecordProps } from './NetworkChildCollection'
import type { DeviceWrite, NetworkDevice, NetworksClient } from './api'
import { DeviceInterfaces } from './DeviceInterfaces'
import { DeviceHardware } from './DeviceHardware'
import { NetworkRelationships } from './NetworkRelationships'
import { DeviceChoice } from './DeviceChoice'
import { RackPlaceChoice } from './RackPlaceChoice'
import { networkText as t } from './networkText'
const roles: { value: NetworkDevice['role']; label: string }[] = [
  { value: 'router', label: t('deviceRoleRouter') }, { value: 'switch', label: t('deviceRoleSwitch') }, { value: 'firewall', label: t('deviceRoleFirewall') }, { value: 'wireless_controller', label: t('deviceRoleWirelessController') }, { value: 'access_point', label: t('deviceRoleAccessPoint') }, { value: 'load_balancer', label: t('deviceRoleLoadBalancer') }, { value: 'other', label: t('deviceRoleOther') },
]
const statuses = [{ value: 'planned', label: t('rackStatusPlanned') }, { value: 'active', label: t('rackStatusActive') }, { value: 'offline', label: t('rackStatusOffline') }, { value: 'retired', label: t('rackStatusRetired') }]
const columns = ['name', 'role', 'status', 'site', 'rack', 'rack_unit'] as const
const labels = { name: t('name'), role: t('rackDeviceRole'), status: translate('collections.status'), site: t('site'), rack: t('deviceRack'), rack_unit: t('rackDeviceUnit') }
const config: ChildCollectionConfig<NetworkDevice, NetworkDevice> = {
  key: 'devices', childSelectionKeys: ['interface', 'interface_view', 'interface_ip', 'interface_mac'], feature: 'network-devices', columns, labels, title: t('devices'), back: t('devicesBack'), create: t('devicesNew'), search: t('devicesSearch'), order: t('devicesOrder'), failed: t('devicesFailed'), empty: t('devicesEmpty'), count: (count) => t('devicesCount', { count }), association: { label: t('rackDeviceRole'), choices: roles }, statuses, identity: (row) => row.name,
  value: (row, column) => column === 'role' ? roles.find((item) => item.value === row.role)?.label : column === 'status' ? statuses.find((item) => item.value === row.status)?.label : column === 'site' ? row.site_name || t('unassigned') : column === 'rack' ? row.rack_name || t('deviceUnracked') : row.rack_unit ?? translate('collections.missing'),
  load: (client, workspace, query, signal) => { const { association, ...rest } = query; return client.deviceCollection(workspace, { ...rest, ...(association ? { role: association } : {}) }, signal) }, read: (client, workspace, id, signal) => client.deviceDetail(workspace, id, signal),
}
const DeviceRelationshipsClientContext = createContext<RelationshipsClient>(browserRelationshipsClient)
export function DeviceRegister({ workspace, client, relationshipsClient = browserRelationshipsClient, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; client: NetworksClient; relationshipsClient?: RelationshipsClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <DeviceRelationshipsClientContext.Provider value={relationshipsClient}><div className="device-register"><NetworkChildCollection standalone workspace={workspace} subnetId="" client={client} preferenceClient={preferenceClient} config={config} RecordComponent={DeviceRecord} /></div></DeviceRelationshipsClientContext.Provider>
}
type Props = ChildRecordProps<NetworkDevice> & { workspace: WorkspaceContext; client: NetworksClient }
function DeviceRecord({ record, workspace, client, canManage, canRebindHardware, relationshipAccess, onSaved, onReturn }: Props) {
  const [params] = useSearchParams(), location = useLocation()
  const relationshipsClient = useContext(DeviceRelationshipsClientContext)
  const requested = params.get('devices_section')
  const section = record && (requested === 'placement' || requested === 'history' || requested === 'interfaces' || (requested === 'hardware' && canRebindHardware) || (requested === 'relationships' && relationshipAccess?.view)) ? requested : 'overview'
  function href(id: string) { const next = new URLSearchParams(params); next.set('devices_section', id); return `${location.pathname}?${next}` }
  const sections = ['overview', ...(canRebindHardware ? ['hardware'] : []), 'placement', 'interfaces', ...(relationshipAccess?.view ? ['relationships'] : []), 'history']
  return <article className="record-page">
    {params.get('devices_full') === 'true' && <RecordHeader title={record?.name ?? t('devicesNew')} recordId={record?.id ?? 'new'} section={section} />}
    {record && <RecordSections current={section} sections={sections.map((id) => ({ id, label: id === 'interfaces' ? t('interfaces') : id === 'hardware' ? t('deviceHardware') : id === 'relationships' ? t('deviceRelationships') : id === 'placement' ? t('devicePlacement') : translate(id === 'history' ? 'collections.history' : 'collections.overview'), href: href(id) }))} />}
    {section === 'hardware' && record ? <DeviceHardware key={record.id} record={record} workspace={workspace} client={client} onSaved={onSaved} /> : section === 'interfaces' && record ? <DeviceInterfaces key={record.id} workspace={workspace} deviceId={record.id} client={client} /> : section === 'relationships' && record ? <NetworkRelationships key={record.id} workspace={workspace} deviceId={record.id} deviceName={record.name} canCreate={Boolean(relationshipAccess?.create)} canArchive={Boolean(relationshipAccess?.archive)} client={relationshipsClient} /> : section === 'history' && record ? <RecordActivity workspace={workspace} entityId={record.id} description={t('devicesHistoryHelp')} emptyLabel={t('devicesHistoryEmpty')} deniedLabel={t('devicesHistoryDenied')} /> : section === 'placement' && record ? <DevicePlacement key={record.id} record={record} workspace={workspace} client={client} canManage={canManage} onSaved={onSaved} /> : <DeviceOverview record={record} workspace={workspace} client={client} canManage={canManage} onSaved={onSaved} onReturn={onReturn} />}
  </article>
}
function DeviceOverview({ record, workspace, client, canManage, onSaved, onReturn }: Props) {
  const initial = { name: record?.name ?? '', role: record?.role ?? 'switch', status: record?.status ?? 'active' }
  const [form, setForm] = useState(initial), [asset, setAsset] = useState<{ id: string; name: string } | null>(null)
  const [editing, setEditing] = useState(!record), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const attempt = useUnsavedChanges(editing && (JSON.stringify(form) !== JSON.stringify(initial) || Boolean(asset)), busy, () => { setEditing(false); setForm(initial); setAsset(null) }, editing)
  async function save() {
    if (busy) return
    if (!record && !asset) { setError(t('deviceAssetRequired')); return }
    setBusy(true); setError('')
    try {
      const value = record ? await client.updateDevice(workspace, record.id, form) : await client.createDevice(workspace, { ...form, hardware_asset_id: asset!.id, site_id: null, location_id: null, rack_id: null, rack_unit: null, rack_units: 1 })
      setEditing(false); setAsset(null); onSaved(value)
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('devicesSaveFailed')) } finally { setBusy(false) }
  }
  return <>
    {error && <p role="alert">{error}</p>}
    {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{t('name')}<input required maxLength={240} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
      <div className="field-grid"><label>{t('rackDeviceRole')}<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as NetworkDevice['role'] })}>{roles.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>{translate('collections.status')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as NetworkDevice['status'] })}>{statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
      {!record && <><p>{t('deviceCreateHelp')}</p><DeviceChoice kind="asset" selected={asset} onChange={setAsset} workspace={workspace} client={client} /></>}
      <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t('devicesSave')}</button><button type="button" className="secondary-button" onClick={() => record ? attempt(() => setEditing(false)) : onReturn()}>{translate('common.cancel')}</button></div>
    </fieldset></form> : record ? <>
      <dl className="record-facts">{columns.filter((column) => column !== 'name').map((column) => <div key={column}><dt>{labels[column]}</dt><dd>{config.value(record, column)}</dd></div>)}<div><dt>{t('rackDeviceAsset')}</dt><dd>{record.hardware_asset_name || t('rackDeviceAssetUnavailable')}</dd></div></dl>
      {canManage && <button type="button" className="secondary-button" onClick={() => { setForm(initial); setEditing(true); setError('') }}>{t('devicesEdit')}</button>}
    </> : <p>{t('devicesDenied')}</p>}
  </>
}
function DevicePlacement({ record, workspace, client, canManage, onSaved }: Omit<Props, 'record' | 'onReturn'> & { record: NetworkDevice }) {
  const initial: Pick<DeviceWrite, 'site_id' | 'location_id' | 'rack_id' | 'rack_unit' | 'rack_units'> = { site_id: record.site_id, location_id: record.location_id, rack_id: record.rack_id, rack_unit: record.rack_unit, rack_units: record.rack_units }
  const [form, setForm] = useState(initial)
  const [mode, setMode] = useState(record.rack_id ? 'rack' : 'site')
  const [site, setSite] = useState(record.site_id ? { id: record.site_id, name: record.site_name ?? t('assignmentUnavailable') } : null)
  const [place, setPlace] = useState(record.location_id ? { id: record.location_id, name: record.location_name ?? t('assignmentUnavailable') } : null)
  const [rack, setRack] = useState(record.rack_id ? { id: record.rack_id, name: record.rack_name ?? t('assignmentUnavailable') } : null)
  const [editing, setEditing] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  function reset() { setForm(initial); setMode(record.rack_id ? 'rack' : 'site'); setSite(record.site_id ? { id: record.site_id, name: record.site_name ?? t('assignmentUnavailable') } : null); setPlace(record.location_id ? { id: record.location_id, name: record.location_name ?? t('assignmentUnavailable') } : null); setRack(record.rack_id ? { id: record.rack_id, name: record.rack_name ?? t('assignmentUnavailable') } : null) }
  const attempt = useUnsavedChanges(editing && (JSON.stringify(form) !== JSON.stringify(initial) || mode !== (record.rack_id ? 'rack' : 'site')), busy, () => { setEditing(false); reset() }, editing)
  async function save() {
    if (busy) return
    if (mode === 'rack' && !form.rack_id) { setError(t('deviceRackRequired')); return }
    setBusy(true); setError('')
    try { const value = await client.updateDevice(workspace, record.id, form); setEditing(false); onSaved(value) } catch (caught) { setError(caught instanceof Error ? caught.message : t('devicesSaveFailed')) } finally { setBusy(false) }
  }
  return <>
    {error && <p role="alert">{error}</p>}
    {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{t('devicePlacementType')}<select value={mode} onChange={(event) => { setMode(event.target.value); setRack(null); setForm({ ...form, rack_id: null, rack_unit: event.target.value === 'rack' ? 1 : null, rack_units: 1 }) }}><option value="site">{t('deviceUnracked')}</option><option value="rack">{t('deviceRacked')}</option></select></label>
      {mode === 'rack' ? <><p>{t('deviceRackHelp')}</p><DeviceChoice kind="rack" selected={rack} workspace={workspace} client={client} onChange={(value) => { setRack(value); setForm({ ...form, rack_id: value.id }) }} /><div className="field-grid">{(['rack_unit', 'rack_units'] as const).map((field) => <label key={field}>{t(field === 'rack_unit' ? 'rackDeviceUnit' : 'rackDeviceUnits')}<input type="number" required min={1} max={100} value={form[field] == null || Number.isNaN(form[field]) ? '' : form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.valueAsNumber })} /></label>)}</div></> : <>
        <p>{t('deviceSiteHelp')}</p><button type="button" className="secondary-button" onClick={() => { setSite(null); setPlace(null); setForm({ ...form, site_id: null, location_id: null }) }}>{t('deviceNoSite')}</button>
        <RackPlaceChoice kind="site" selected={site} workspace={workspace} client={client} onChange={(value) => { if (value && value.id !== form.site_id) { setSite(value); setPlace(null); setForm({ ...form, site_id: value.id, location_id: null }) } }} />
        {form.site_id && <RackPlaceChoice key={form.site_id} kind="location" siteId={form.site_id} selected={place} workspace={workspace} client={client} onChange={(value) => { setPlace(value); setForm({ ...form, location_id: value?.id ?? null }) }} />}
      </>}
      <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t('devicePlacementSave')}</button><button type="button" className="secondary-button" onClick={() => attempt(() => setEditing(false))}>{translate('common.cancel')}</button></div>
    </fieldset></form> : <>
      <dl className="record-facts">{[[t('site'), record.site_name], [t('location'), record.location_name], [t('deviceRack'), record.rack_name ?? t('deviceUnracked')], [t('rackDeviceUnit'), record.rack_unit], [t('rackDeviceUnits'), record.rack_units]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? translate('collections.missing')}</dd></div>)}</dl>
      {canManage && <button type="button" className="secondary-button" onClick={() => { reset(); setError(''); setEditing(true) }}>{t('devicePlacementEdit')}</button>}
    </>}
  </>
}
