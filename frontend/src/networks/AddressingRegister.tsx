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
import type { AddressingRecord, AddressingSummary, NetworksClient } from './api'
import { networkText as t } from './networkText'

type Kind = 'vlans' | 'vrfs'
function configuration(kind: Kind): ChildCollectionConfig<AddressingSummary, AddressingRecord> {
  const field = kind === 'vlans' ? 'vlan_id' : 'route_distinguisher'
  return {
    key: kind, feature: `network-${kind}`, columns: ['name', field],
    labels: { name: t('name'), [field]: t(field) }, title: t(kind), back: t(`${kind}Back`),
    create: t(`${kind}New`), search: t(`${kind}Search`), order: t(`${kind}Order`),
    failed: t(`${kind}Failed`), empty: t(`${kind}Empty`), count: (count) => t(`${kind}Count`, { count }),
    statuses: [], identity: (row) => row.name,
    value: (row) => row[field] || translate('collections.missing'),
    load: (client, workspace, query, signal) => client.addressingCollection(workspace, kind, query, signal),
    read: (client, workspace, id, signal) => client.addressingDetail(workspace, kind, id, signal),
  }
}
const configs = { vlans: configuration('vlans'), vrfs: configuration('vrfs') }
type Props = ChildRecordProps<AddressingRecord> & { workspace: WorkspaceContext; client: NetworksClient; subnetId: string }
function VLANRecord(props: Props) { return <AddressingRecordView {...props} kind="vlans" /> }
function VRFRecord(props: Props) { return <AddressingRecordView {...props} kind="vrfs" /> }
export function AddressingRegister({ kind, workspace, client, preferenceClient = browserCollectionPreferences }: { kind: Kind; workspace: WorkspaceContext; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection key={kind} standalone workspace={workspace} subnetId="" client={client} preferenceClient={preferenceClient} config={configs[kind]} RecordComponent={kind === 'vlans' ? VLANRecord : VRFRecord} />
}
function AddressingRecordView({ record, kind, workspace, client, canManage, onSaved, onReturn }: Props & { kind: Kind }) {
  const [params] = useSearchParams()
  const location = useLocation()
  const section = params.get(`${kind}_section`) === 'history' ? 'history' : 'overview'
  const initial = { name: record?.name ?? '', vlan_id: String(record?.vlan_id ?? 1), route_distinguisher: record?.route_distinguisher ?? '', description: record?.description ?? '' }
  const [form, setForm] = useState(initial)
  const [editing, setEditing] = useState(!record)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  function href(value: string) { const next = new URLSearchParams(params); next.set(`${kind}_section`, value); return `${location.pathname}?${next}` }
  async function save() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const common = { name: form.name, description: form.description }
      const value = kind === 'vlans'
        ? await (record ? client.updateVLAN(workspace, record.id, { ...common, vlan_id: Number(form.vlan_id) }) : client.createVLAN(workspace, { ...common, vlan_id: Number(form.vlan_id) }))
        : await (record ? client.updateVRF(workspace, record.id, { ...common, route_distinguisher: form.route_distinguisher }) : client.createVRF(workspace, { ...common, route_distinguisher: form.route_distinguisher }))
      setEditing(false); onSaved(value)
    } catch (caught) { setError(caught instanceof Error ? caught.message : t(`${kind}SaveFailed`)) }
    finally { setBusy(false) }
  }
  return <article className="record-page">
    {params.get(`${kind}_full`) === 'true' && <RecordHeader title={record?.name ?? t(`${kind}New`)} recordId={record?.id ?? 'new'} section={section} />}
    {record && <RecordSections current={section} sections={['overview', 'history'].map((id) => ({ id, label: translate(id === 'overview' ? 'collections.overview' : 'collections.history'), href: href(id) }))} />}
    {section === 'history' && record ? <RecordActivity workspace={workspace} entityId={record.id} description={t(`${kind}HistoryHelp`)} emptyLabel={t(`${kind}HistoryEmpty`)} deniedLabel={t(`${kind}HistoryDenied`)} /> : <>
      {error && <p role="alert">{error}</p>}
      {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
        <label>{t('name')}<input required maxLength={240} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        {kind === 'vlans' ? <label>{t('vlan_id')}<input type="number" required min={1} max={4094} value={form.vlan_id} onChange={(event) => setForm({ ...form, vlan_id: event.target.value })} /></label> : <label>{t('route_distinguisher')}<input maxLength={64} value={form.route_distinguisher} onChange={(event) => setForm({ ...form, route_distinguisher: event.target.value })} /></label>}
        <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
        <div className="form-actions"><button type="submit" className="primary-button">{busy ? translate('common.saving') : t(`${kind}Save`)}</button><button type="button" className="secondary-button" onClick={() => record ? attempt(() => setEditing(false)) : onReturn()}>{translate('common.cancel')}</button></div>
      </fieldset></form> : record ? <>
        <dl className="record-facts"><div><dt>{t(kind === 'vlans' ? 'vlan_id' : 'route_distinguisher')}</dt><dd>{kind === 'vlans' ? record.vlan_id : record.route_distinguisher || translate('collections.missing')}</dd></div></dl>
        <p className="network-notes">{record.description || t('noDescription')}</p>
        {canManage && <button type="button" className="secondary-button" onClick={() => { setForm(initial); setEditing(true) }}>{t(`${kind}Edit`)}</button>}
      </> : <p>{t(`${kind}Denied`)}</p>}
    </>}
  </article>
}
