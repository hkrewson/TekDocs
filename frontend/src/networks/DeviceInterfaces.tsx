import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { InterfaceEndpoints } from './InterfaceEndpoints'
import { translate } from '../i18n/localization'
import { browserCollectionPreferences } from '../collections/preferences'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworkInterface, NetworksClient } from './api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig } from './NetworkChildCollection'
import { networkText as t } from './networkText'

const kinds = [
  { value: 'physical', label: t('interfacePhysical') }, { value: 'virtual', label: t('interfaceVirtual') },
  { value: 'lag', label: t('interfaceLag') }, { value: 'loopback', label: t('interfaceLoopback') },
  { value: 'tunnel', label: t('interfaceTunnel') }, { value: 'wireless', label: t('interfaceWireless') },
  { value: 'other', label: t('interfaceOther') },
]
const statuses = [{ value: 'planned', label: t('rackStatusPlanned') }, { value: 'active', label: t('rackStatusActive') }, { value: 'disabled', label: t('interfaceDisabled') }, { value: 'retired', label: t('rackStatusRetired') }]
const config: ChildCollectionConfig<Omit<NetworkInterface, 'description'>, NetworkInterface> = {
  key: 'interface', childSelectionKeys: ['interface_view', 'interface_ip', 'interface_mac'], feature: 'network-interfaces', parentField: 'device_id', columns: ['name', 'kind', 'status'],
  labels: { name: t('name'), kind: t('interfaceKind'), status: translate('collections.status') },
  title: t('interfaces'), back: t('interfacesBack'), create: t('interfacesNew'), search: t('interfacesSearch'),
  order: t('interfacesOrder'), failed: t('interfacesFailed'), empty: t('interfacesEmpty'), count: (count) => t('interfacesCount', { count }),
  association: { label: t('interfaceKind'), choices: kinds }, statuses,
  identity: (row) => row.name,
  value: (row, column) => column === 'kind' ? kinds.find((item) => item.value === row.kind)?.label : statuses.find((item) => item.value === row.status)?.label,
  load: (client, workspace, query, signal) => { const { association, ...rest } = query; return client.interfaceCollection(workspace, { ...rest, ...(association ? { kind: association } : {}) }, signal) },
  read: (client, workspace, id, signal) => client.interfaceDetail(workspace, id, signal),
}
export function DeviceInterfaces({ workspace, deviceId, client, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; deviceId: string; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection workspace={workspace} parentId={deviceId} client={client} preferenceClient={preferenceClient} config={config} RecordComponent={InterfaceRecord} />
}

type InterfaceForm = Pick<NetworkInterface, 'name' | 'kind' | 'status' | 'description'>
function InterfaceRecord({ record, parentId, workspace, client, canManage, onSaved, onReturn }: { record: NetworkInterface | null; parentId: string; workspace: WorkspaceContext; client: NetworksClient; canManage: boolean; onSaved: (record: NetworkInterface) => void; onReturn: () => void }) {
  const [params] = useSearchParams(), location = useLocation()
  const view = record && ['ip', 'mac'].includes(params.get('interface_view') ?? '') ? params.get('interface_view') as 'ip' | 'mac' : 'details'
  function href(value: string) { const next = new URLSearchParams(params); next.set('interface_view', value); return `${location.pathname}?${next}` }
  const initial: InterfaceForm = record ? { name: record.name, kind: record.kind, status: record.status, description: record.description } : { name: '', kind: 'physical', status: 'active', description: '' }
  const [form, setForm] = useState(initial), [editing, setEditing] = useState(!record)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  useEffect(() => { heading.current?.focus() }, [record?.id])
  async function save() {
    if (busy) return
    setBusy(true); setError('')
    try { const value = record ? await client.updateInterface(workspace, record.id, form) : await client.createInterface(workspace, { ...form, device_id: parentId }); setEditing(false); onSaved(value) }
    catch (caught) { setError(caught instanceof Error ? caught.message : t('interfaceSaveFailed')) }
    finally { setBusy(false) }
  }
  return <>
    <button className="secondary-button" type="button" onClick={onReturn}>{t('interfacesBack')}</button>
    <h2 ref={heading} tabIndex={-1}>{record?.name ?? t('interfacesNew')}</h2>
    {record && <nav className="collection-toolbar" aria-label={t('endpointNavigation')}>{(['details', 'ip', 'mac'] as const).map((value) => <Link key={value} to={href(value)} aria-current={view === value ? 'page' : undefined}>{t(value === 'details' ? 'interfaceDetails' : value === 'ip' ? 'endpointIPs' : 'endpointMACs')}</Link>)}</nav>}
    {view !== 'details' && record ? <InterfaceEndpoints key={`${record.id}:${view}`} kind={view} workspace={workspace} interfaceId={record.id} client={client} /> : <>
    {error && <p role="alert">{error}</p>}
    {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{t('name')}<input required maxLength={240} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
      <div className="field-grid"><label>{t('interfaceKind')}<select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as NetworkInterface['kind'] })}>{kinds.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label>{translate('collections.status')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as NetworkInterface['status'] })}>{statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
      <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t('interfaceSave')}</button><button type="button" className="secondary-button" onClick={() => record ? attempt(() => setEditing(false)) : onReturn()}>{translate('common.cancel')}</button></div>
    </fieldset></form> : record ? <>
      <dl className="record-facts">{(['kind', 'status'] as const).map((column) => <div key={column}><dt>{config.labels[column]}</dt><dd>{config.value(record, column)}</dd></div>)}</dl>
      <p className="network-notes">{record.description || t('noDescription')}</p>
      {canManage && <button className="secondary-button" type="button" onClick={() => { setForm(initial); setError(''); setEditing(true) }}>{t('interfaceEdit')}</button>}
    </> : <p>{t('interfaceDenied')}</p>}
    </>}
  </>
}
