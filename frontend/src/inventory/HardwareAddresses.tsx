import { useState } from 'react'
import { Pencil, Plus } from 'lucide-react'

import type { WorkspaceContext } from '../workspaces/api'
import type { AssetMACAddress, ClientAsset, InventoryClient } from './api'

export function HardwareAddresses({ asset, workspace, client, canManage, onChange }: {
  asset: ClientAsset
  workspace: WorkspaceContext
  client: InventoryClient
  canManage: boolean
  onChange: (addresses: AssetMACAddress[]) => void
}) {
  const [editing, setEditing] = useState<AssetMACAddress | null | 'new'>(null)
  const [address, setAddress] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function begin(value: AssetMACAddress | 'new') {
    setEditing(value)
    setAddress(value === 'new' ? '' : value.address)
    setDescription(value === 'new' ? '' : value.description)
    setError('')
  }

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const saved = editing === 'new'
        ? await client.createAssetMACAddress(workspace, asset.id, { address, description })
        : await client.updateAssetMACAddress(workspace, asset.id, editing!.id, { address, description })
      onChange(editing === 'new'
        ? [...asset.mac_addresses, saved]
        : asset.mac_addresses.map((item) => item.id === saved.id ? saved : item))
      setEditing(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The MAC address could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return <section className="hardware-addresses" aria-labelledby="hardware-addresses-heading">
    <div className="section-heading">
      <div><h3 id="hardware-addresses-heading">MAC addresses</h3><p>Physical interface addresses belonging to this asset.</p></div>
      {canManage && editing === null && <button className="secondary-button" type="button" onClick={() => begin('new')}><Plus size={15} aria-hidden="true" />Add address</button>}
    </div>
    {asset.mac_addresses.length === 0 && editing === null ? <p className="empty-state">No MAC addresses are recorded for this asset.</p> : <ul className="hardware-address-list">{asset.mac_addresses.map((item) => <li key={item.id}><span><code>{item.address}</code>{item.description && <small>{item.description}</small>}</span>{canManage && <button className="row-action" type="button" onClick={() => begin(item)}><Pencil size={14} aria-hidden="true" />Edit</button>}</li>)}</ul>}
    {editing !== null && <form className="hardware-form hardware-address-form" onSubmit={(event) => void save(event)}>
      <label><span>MAC address</span><input required maxLength={17} value={address} onChange={(event) => setAddress(event.target.value)} placeholder="00:11:22:33:44:55" /></label>
      <label><span>Description</span><input maxLength={4000} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Ethernet or Wi-Fi" /></label>
      <div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save address'}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button></div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>}
  </section>
}
