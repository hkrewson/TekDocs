import { WirelessAssociation } from './WirelessAssociation'
import { WirelessParent } from './WirelessParent'
import { useLocation, useSearchParams } from 'react-router'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import { RecordActivity } from '../records/RecordActivity'
import { useEffect, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { browserCollectionPreferences } from '../collections/preferences'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetworksClient, WirelessNetwork } from './api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig, ChildRecordProps } from './NetworkChildCollection'
import { networkText as t } from './networkText'

const statuses = ['planned', 'active', 'disabled', 'retired'] as const
const purposes = ['corporate', 'guest', 'iot', 'voice', 'other'] as const
const securityModes = ['open', 'owe', 'wpa2_personal', 'wpa3_personal', 'wpa2_enterprise', 'wpa3_enterprise', 'mixed_personal', 'mixed_enterprise'] as const
const config: ChildCollectionConfig<Omit<WirelessNetwork, 'description'>, WirelessNetwork> = {
  key: 'wireless', feature: 'network-wireless', columns: ['name', 'status', 'purpose', 'security'],
  labels: { name: t('ssid'), status: t('addressStatus'), purpose: t('purpose'), security: t('security') },
  title: t('wireless'), back: t('backWireless'), create: t('newWireless'), search: t('searchWireless'),
  order: t('wirelessOrder'), failed: t('wirelessFailed'), empty: t('wirelessEmpty'), count: (count) => t('wirelessCount', { count }),
  statuses: statuses.map((value) => ({ value, label: t(value) })),
  identity: (row) => row.ssid, value: (row, column) => t(column === 'status' ? row.status : column === 'purpose' ? row.purpose : row.security),
  load: (client, workspace, query, signal) => client.wirelessCollection(workspace, query, signal),
  read: (client, workspace, id, signal) => client.wirelessDetail(workspace, id, signal),
}
export function NetworkWireless({ workspace, subnetId, client, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; subnetId: string; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection workspace={workspace} subnetId={subnetId} client={client} preferenceClient={preferenceClient} config={config} RecordComponent={WirelessRecord} />
}

type WirelessForm = Pick<WirelessNetwork, 'ssid' | 'status' | 'purpose' | 'security' | 'hidden' | 'client_isolation' | 'description'>
function WirelessRecord({ record, subnetId, workspace, client, canManage, onSaved, onReturn, showHeading = true }: ChildRecordProps<WirelessNetwork> & { showHeading?: boolean; subnetId: string; workspace: WorkspaceContext; client: NetworksClient }) {
  const initial: WirelessForm = record ? { ssid: record.ssid, status: record.status, purpose: record.purpose, security: record.security, hidden: record.hidden, client_isolation: record.client_isolation, description: record.description } : { ssid: '', status: 'active', purpose: 'corporate', security: 'wpa3_personal', hidden: false, client_isolation: false, description: '' }
  const [form, setForm] = useState(initial)
  const [editing, setEditing] = useState(!record)
  const [changingParent, setChangingParent] = useState(false)
  const [assignment, setAssignment] = useState<'site' | 'vlan' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  useEffect(() => { heading.current?.focus() }, [record?.id])
  async function save() {
    setBusy(true); setError('')
    try {
      // Existing associations are omitted from ordinary edits, so hidden or legacy
      // site/VLAN relationships are preserved by the partial update contract.
      const value = record ? await client.updateWireless(workspace, record.id, form) : await client.createWireless(workspace, { ...form, subnet_id: subnetId || null, site_id: null, vlan_id: null })
      setEditing(false); onSaved(value)
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('wirelessSaveFailed')) } finally { setBusy(false) }
  }
  return <>
    {showHeading && <button className="secondary-button" type="button" onClick={onReturn}>{t('backWireless')}</button>}
    {showHeading && <h2 ref={heading} tabIndex={-1}>{record?.ssid ?? t('newWireless')}</h2>}
    {error && <p role="alert">{error}</p>}
    {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{t('ssid')}<input required maxLength={128} value={form.ssid} onChange={(event) => setForm({ ...form, ssid: event.target.value })} /></label>
      <label>{t('addressStatus')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as WirelessForm['status'] })}>{statuses.map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label>
      <label>{t('purpose')}<select value={form.purpose} onChange={(event) => setForm({ ...form, purpose: event.target.value as WirelessForm['purpose'] })}>{purposes.map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label>
      <label>{t('security')}<select value={form.security} onChange={(event) => setForm({ ...form, security: event.target.value as WirelessForm['security'] })}>{securityModes.map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label>
      <label className="network-range-toggle"><input type="checkbox" checked={form.hidden} onChange={(event) => setForm({ ...form, hidden: event.target.checked })} /><span>{t('hidden')}</span></label>
      <label className="network-range-toggle"><input type="checkbox" checked={form.client_isolation} onChange={(event) => setForm({ ...form, client_isolation: event.target.checked })} /><span>{t('clientIsolation')}</span></label>
      <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('common.saving') : t('saveWireless')}</button><button type="button" className="secondary-button" onClick={() => { if (record) attempt(() => setEditing(false)); else onReturn() }}>{translate('common.cancel')}</button></div>
    </fieldset></form> : record ? <>
      <dl className="record-facts">{[[t('networkColumn'), record.subnet_cidr || t('unassignedNetwork')], [t('addressStatus'), t(record.status)], [t('purpose'), t(record.purpose)], [t('security'), t(record.security)], [t('hidden'), t(record.hidden ? 'yes' : 'no')], [t('clientIsolation'), t(record.client_isolation ? 'yes' : 'no')], [translate('collections.site'), record.site_name || translate('collections.missing')], [t('vlan'), record.vlan_number === null ? translate('collections.missing') : String(record.vlan_number)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <p className="network-notes">{record.description || t('noDescription')}</p>
      {canManage && !changingParent && !assignment && <button className="secondary-button" type="button" onClick={() => { setForm(initial); setEditing(true) }}>{t('editWireless')}</button>}
      {changingParent ? <WirelessParent record={record} workspace={workspace} client={client} onSaved={onSaved} onCancel={() => setChangingParent(false)} /> : canManage && !assignment && <button className="secondary-button" type="button" onClick={() => setChangingParent(true)}>{t('changeParent')}</button>}
      {assignment ? <WirelessAssociation key={assignment} kind={assignment} record={record} workspace={workspace} client={client} onSaved={onSaved} onCancel={() => setAssignment(null)} /> : canManage && !changingParent && (['site', 'vlan'] as const).map((kind) => <button key={kind} className="secondary-button" type="button" onClick={() => setAssignment(kind)}>{t(`${kind}AssignmentChange`)}</button>)}
    </> : <p>{t('wirelessDenied')}</p>}
  </>
}

const registerConfig: typeof config = {
  ...config, key: 'ssid', feature: 'wireless-register', columns: ['name', 'network', 'status', 'security'],
  labels: { ...config.labels, network: t('networkColumn') }, empty: t('wirelessRegisterEmpty'),
  association: { label: t('networkAssociation'), choices: [{ value: 'assigned', label: t('assignedNetwork') }, { value: 'unassigned', label: t('unassignedNetwork') }] },
  value: (row, column) => column === 'network' ? row.subnet_cidr || t('unassignedNetwork') : config.value(row, column),
}
export function WirelessWorkspace({ workspace, client, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection standalone workspace={workspace} subnetId="" client={client} config={registerConfig} RecordComponent={WorkspaceWirelessRecord} preferenceClient={preferenceClient} />
}
function WorkspaceWirelessRecord(props: ChildRecordProps<WirelessNetwork> & { subnetId: string; workspace: WorkspaceContext; client: NetworksClient }) {
  const [params] = useSearchParams()
  const location = useLocation()
  const section = params.get('ssid_section') === 'history' ? 'history' : 'overview'
  function href(value: string) { const next = new URLSearchParams(params); next.set('ssid_section', value); return `${location.pathname}?${next}` }
  return <article className="record-page">
    {params.get('ssid_full') === 'true' && <RecordHeader title={props.record?.ssid ?? t('newWireless')} recordId={props.record?.id ?? 'new'} section={section} />}
    {props.record && <RecordSections current={section} sections={['overview', 'history'].map((id) => ({ id, label: translate(id === 'overview' ? 'collections.overview' : 'collections.history'), href: href(id) }))} />}
    {section === 'history' && props.record ? <RecordActivity entityId={props.record.id} workspace={props.workspace} description={t('wirelessHistoryHelp')} emptyLabel={t('wirelessHistoryEmpty')} deniedLabel={t('wirelessHistoryDenied')} /> : <WirelessRecord {...props} showHeading={false} />}
  </article>
}
