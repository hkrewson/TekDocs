import { useEffect, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { browserCollectionPreferences } from '../collections/preferences'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { AddressSummary, NetworkIPAddress, NetworksClient } from './api'
import { NetworkChildCollection } from './NetworkChildCollection'
import type { ChildCollectionConfig } from './NetworkChildCollection'
import { networkText as t } from './networkText'

const statuses = ['active', 'reserved', 'dhcp', 'deprecated'] as const
const config: ChildCollectionConfig<AddressSummary, NetworkIPAddress> = {
  key: 'address', feature: 'network-addresses', columns: ['name', 'status', 'dns_name'],
  labels: { name: t('address'), status: t('addressStatus'), dns_name: t('dnsName') },
  title: t('addresses'), back: t('backAddresses'), create: t('newAddress'), search: t('searchAddresses'),
  order: t('addressOrder'), failed: t('addressesFailed'), empty: t('addressesEmpty'), count: (count) => t('addressCount', { count }),
  statuses: statuses.map((value) => ({ value, label: t(value) })),
  identity: (row) => row.address, value: (row, column) => column === 'status' ? t(row.status) : row.dns_name || translate('collections.missing'),
  load: (client, workspace, query, signal) => client.addressCollection(workspace, query, signal),
  read: (client, workspace, id, signal) => client.addressDetail(workspace, id, signal),
}
export function NetworkAddresses({ workspace, subnetId, client, preferenceClient = browserCollectionPreferences }: { workspace: WorkspaceContext; subnetId: string; client: NetworksClient; preferenceClient?: typeof browserCollectionPreferences }) {
  return <NetworkChildCollection workspace={workspace} subnetId={subnetId} client={client} preferenceClient={preferenceClient} config={config} RecordComponent={AddressRecord} />
}

type AddressForm = Pick<NetworkIPAddress, 'address' | 'status' | 'dns_name' | 'description'>
function AddressRecord({ record, subnetId, workspace, client, canManage, onSaved, onReturn }: { record: NetworkIPAddress | null; subnetId: string; workspace: WorkspaceContext; client: NetworksClient; canManage: boolean; onSaved: (record: NetworkIPAddress) => void; onReturn: () => void }) {
  const initial: AddressForm = record ? { address: record.address, status: record.status, dns_name: record.dns_name, description: record.description } : { address: '', status: 'active', dns_name: '', description: '' }
  const [form, setForm] = useState(initial)
  const [editing, setEditing] = useState(!record)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const attempt = useUnsavedChanges(editing && JSON.stringify(form) !== JSON.stringify(initial), busy, () => { setEditing(false); setForm(initial) }, editing)
  useEffect(() => { heading.current?.focus() }, [record?.id])
  async function save() { setBusy(true); setError(''); try { const value = record ? await client.updateIPAddress(workspace, record.id, form) : await client.createIPAddress(workspace, { ...form, subnet_id: subnetId, hardware_asset_id: null }); setEditing(false); onSaved(value) } catch (caught) { setError(caught instanceof Error ? caught.message : t('addressSaveFailed')) } finally { setBusy(false) } }
  return <>
    <button className="secondary-button" type="button" onClick={onReturn}>{t('backAddresses')}</button>
    <h2 ref={heading} tabIndex={-1}>{record?.address ?? t('newAddress')}</h2>
    {error && <p role="alert">{error}</p>}
    {editing && canManage ? <form className="network-inline-editor" onSubmit={(event) => { event.preventDefault(); void save() }}><fieldset disabled={busy}>
      <label>{t('address')}<input required maxLength={45} value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>
      <label>{t('addressStatus')}<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as AddressForm['status'] })}>{statuses.map((status) => <option key={status} value={status}>{t(status)}</option>)}</select></label>
      <label>{t('dnsName')}<input maxLength={253} value={form.dns_name} onChange={(event) => setForm({ ...form, dns_name: event.target.value })} /></label>
      <label>{t('description')}<textarea rows={4} maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button type="submit" className="primary-button" disabled={busy}>{busy ? translate('common.saving') : t('saveAddress')}</button><button type="button" className="secondary-button" onClick={() => { if (record) attempt(() => setEditing(false)); else onReturn() }}>{translate('common.cancel')}</button></div>
    </fieldset></form> : record ? <>
      <dl className="record-facts">{[[t('addressStatus'), t(record.status)], [t('dnsName'), record.dns_name || translate('collections.missing')], [t('addressAssignment'), record.hardware_asset_name || record.device_name || translate('collections.missing')], [t('addressInterface'), record.interface_name || translate('collections.missing')]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <p className="network-notes">{record.description || t('noDescription')}</p>
      {canManage && <button className="secondary-button" type="button" onClick={() => { setForm(initial); setEditing(true) }}>{t('editAddress')}</button>}
    </> : <p>{t('addressDenied')}</p>}
  </>
}
