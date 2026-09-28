import { NetworkWireless } from './NetworkWireless'
import { NetworkAddresses } from './NetworkAddresses'
import type { NetworkRecord, NetworkRecordWrite, NetworksClient } from './api'
import type { WorkspaceContext } from '../workspaces/api'
import { useState } from 'react'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RecordHeader, RecordSections } from '../records/RecordNavigation'
import { RecordActivity } from '../records/RecordActivity'
import { networkText as t } from './networkText'
import { translate } from '../i18n/localization'

function NetworkEditor({ value, setValue, busy, cancel, save }: { value: NetworkRecordWrite; setValue: (value: NetworkRecordWrite) => void; busy: boolean; cancel: () => void; save: () => void }) {
  return <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); save() }}><fieldset disabled={busy}>
        <div className="field-grid">
          <label><span>{t('vlan')}</span><input type="number" min="1" max="4094" value={value.vlan ?? ''} onChange={(event) => setValue({ ...value, vlan: event.target.value ? Number(event.target.value) : null })} placeholder="20" /></label>
          <label><span>{t('cidr')}</span><input autoFocus required value={value.cidr} onChange={(event) => setValue({ ...value, cidr: event.target.value, name: event.target.value })} placeholder="192.168.1.0/24" /></label>
          <label><span>{t('dhcpServer')}</span><input value={value.dhcp_server ?? ''} onChange={(event) => setValue({ ...value, dhcp_server: event.target.value || null })} placeholder="192.168.1.2" /></label>
          <label><span>{t('dnsServerOne')}</span><input value={value.primary_dns ?? ''} onChange={(event) => setValue({ ...value, primary_dns: event.target.value || null })} placeholder="9.9.9.9" /></label>
          <label><span>{t('dnsServerTwo')}</span><input value={value.secondary_dns ?? ''} onChange={(event) => setValue({ ...value, secondary_dns: event.target.value || null })} placeholder="1.1.1.1" /></label>
        </div>
<div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? translate('common.saving') : t('save')}</button><button className="secondary-button" type="button" onClick={cancel}>{translate('common.cancel')}</button></div></fieldset></form>
}

export function NetworkRecordView({ record, workspace, client, section, href, embedded, canManage, onSaved, onCancel }: { record: NetworkRecord | null; workspace: WorkspaceContext; client: NetworksClient; section: string; href: (section: string) => string; embedded: boolean; canManage: boolean; onSaved: (record: NetworkRecord) => void; onCancel: () => void }) {
  const [editing, setEditing] = useState(!record)
  const initial = record ? { name: record.cidr, location_id: null, description: '', vlan: record.vlan, cidr: record.cidr, use_full_range: true, range_start: null, range_end: null, primary_dns: record.primary_dns, secondary_dns: record.secondary_dns, dhcp_server: record.dhcp_server, notes: '' } : { name: '', location_id: null, description: '', vlan: null, cidr: '', use_full_range: true, range_start: null, range_end: null, primary_dns: null, secondary_dns: null, dhcp_server: null, notes: '' }
  const [form, setForm] = useState<NetworkRecordWrite>(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  async function save() { setBusy(true); setError(''); try { const values = { ...form, name: form.cidr, location_id: null, description: '', use_full_range: true, range_start: null, range_end: null, notes: '' }; const saved = record ? await client.updateNetwork(workspace, record.id, values) : await client.createNetwork(workspace, values); setEditing(false); onSaved(saved) } catch (caught) { setError(caught instanceof Error ? caught.message : t('saveFailed')) } finally { setBusy(false) } }
  const current = ['history', 'addresses', 'wireless'].includes(section) ? section : 'overview'
  return <article className="record-page">
    {record && !embedded && <RecordHeader recordId={record.id} section={current} title={record.cidr} description={t('cidrRecord')} />}
    {record && <RecordSections current={current} sections={['overview', 'addresses', 'wireless', 'history'].map((id) => ({ id, label: id === 'wireless' ? t('wireless') : id === 'addresses' ? t('addresses') : translate(id === 'overview' ? 'collections.overview' : 'collections.history'), href: href(id) }))} />}
    {error && <p role="alert">{error}</p>}
    {current === 'wireless' && record ? <NetworkWireless workspace={workspace} subnetId={record.id} client={client} /> : current === 'addresses' && record ? <NetworkAddresses workspace={workspace} subnetId={record.id} client={client} /> : current === 'history' && record ? <RecordActivity entityId={record.id} workspace={workspace} description={t('historyHelp')} emptyLabel={t('historyEmpty')} deniedLabel={t('historyDenied')} /> : editing ? <>
      <h2>{t(record ? 'edit' : 'new')}</h2><p>{t('derivedHelp')}</p>
      <NetworkEditor value={form} setValue={setForm} busy={busy} cancel={() => attempt(() => { if (record) setEditing(false); else onCancel() })} save={() => void save()} />
    </> : record && <>
      <dl className="record-facts">{[[t('cidr'), record.cidr], [t('vlan'), String(record.vlan ?? '—')], [t('subnetMask'), record.subnet_mask], [t('broadcastIp'), record.broadcast_ip || t('notApplicable')], [t('dhcpServer'), record.dhcp_server || '—'], [t('dnsServerOne'), record.primary_dns || '—'], [t('dnsServerTwo'), record.secondary_dns || '—']].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {canManage && <button className="secondary-button" type="button" onClick={() => { setForm(initial); setEditing(true) }}>{t('edit')}</button>}
    </>}
  </article>
}
