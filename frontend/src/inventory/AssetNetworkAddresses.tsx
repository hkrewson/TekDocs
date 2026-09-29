import { Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { AssetIPAddress, AssetNetworkChoice, ClientAsset, InventoryClient } from './api'

const statuses: AssetIPAddress['status'][] = ['active', 'reserved', 'dhcp', 'deprecated']

export function AssetNetworkAddresses({ asset, workspace, client, canManage, onChange }: {
  asset: ClientAsset
  workspace: WorkspaceContext
  client: InventoryClient
  canManage: boolean
  onChange: (addresses: AssetIPAddress[]) => void
}) {
  const addresses = asset.ip_addresses ?? []
  const [editing, setEditing] = useState<AssetIPAddress | 'new' | null>(null)
  const [choices, setChoices] = useState<AssetNetworkChoice[]>([])
  const [form, setForm] = useState({ address: '', subnet_id: '', status: 'active' as AssetIPAddress['status'], dns_name: '', description: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = editing !== null && (editing === 'new'
    ? Object.values(form).some(Boolean)
    : JSON.stringify(form) !== JSON.stringify({ address: editing.address, subnet_id: editing.subnet_id, status: editing.status, dns_name: editing.dns_name, description: editing.description }))
  const attempt = useUnsavedChanges(dirty, busy, () => setEditing(null), editing !== null)

  useEffect(() => {
    if (!canManage || editing === null || choices.length) return
    client.listAssetNetworkChoices(workspace, asset.id).then(setChoices).catch(() => setError(translate('inventory.assetNetworksLoadFailed')))
  }, [asset.id, canManage, choices.length, client, editing, workspace])

  function begin(value: AssetIPAddress | 'new') {
    setEditing(value)
    setForm(value === 'new'
      ? { address: '', subnet_id: '', status: 'active', dns_name: '', description: '' }
      : { address: value.address, subnet_id: value.subnet_id, status: value.status, dns_name: value.dns_name, description: value.description })
    setError('')
  }

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const saved = editing === 'new'
        ? await client.createAssetIPAddress(workspace, asset.id, form)
        : await client.updateAssetIPAddress(workspace, asset.id, editing!.id, form)
      onChange(editing === 'new' ? [...addresses, saved] : addresses.map((item) => item.id === saved.id ? saved : item))
      setEditing(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : translate('inventory.assetIPAddressSaveFailed'))
    } finally {
      setBusy(false)
    }
  }

  return <section className="hardware-addresses" aria-labelledby="asset-ip-addresses-heading">
    <div className="section-heading">
      <div><h3 id="asset-ip-addresses-heading">{translate('inventory.assetIPAddresses')}</h3><p>{translate('inventory.assetIPAddressesHelp')}</p></div>
      {canManage && editing === null && <button className="secondary-button" type="button" onClick={() => attempt(() => begin('new'))}><Plus size={15} aria-hidden="true" />{translate('inventory.addIPAddress')}</button>}
    </div>
    {addresses.length === 0 && editing === null ? <p className="empty-state">{translate('inventory.noAssetIPAddresses')}</p> : <ul className="hardware-address-list">{addresses.map((item) => <li key={item.id}><span><code>{item.address}</code><small>{item.subnet_cidr}{item.dns_name ? ` · ${item.dns_name}` : ''} · {item.status}</small></span>{canManage && <button className="row-action" type="button" onClick={() => attempt(() => begin(item))}><Pencil size={14} aria-hidden="true" />{translate('common.edit')}</button>}</li>)}</ul>}
    {editing !== null && <form className="hardware-form hardware-address-form" onSubmit={(event) => void save(event)}>
      <label><span>{translate('inventory.network')}</span><select required value={form.subnet_id} onChange={(event) => setForm({ ...form, subnet_id: event.target.value })}><option value="">{translate('inventory.chooseNetwork')}</option>{choices.map((choice) => <option key={choice.id} value={choice.id}>{choice.cidr}{choice.name !== choice.cidr ? ` · ${choice.name}` : ''}</option>)}</select></label>
      <label><span>{translate('inventory.ipAddress')}</span><input required maxLength={45} value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} placeholder="192.0.2.10" /></label>
      <label><span>{translate('collections.status')}</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as AssetIPAddress['status'] })}>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
      <label><span>{translate('inventory.dnsName')}</span><input maxLength={253} value={form.dns_name} onChange={(event) => setForm({ ...form, dns_name: event.target.value })} /></label>
      <label><span>{translate('inventory.description')}</span><input maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? translate('common.saving') : translate('inventory.saveAddress')}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => attempt(() => setEditing(null))}>{translate('common.cancel')}</button></div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>}
  </section>
}
