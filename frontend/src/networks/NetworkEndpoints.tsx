import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Pencil, Plus } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { IPAddressWrite, MACAddressWrite, NetworkIPAddress, NetworkMACAddress, NetworkSubnet, NetworksClient } from './api'

type Kind = 'ip-addresses' | 'mac-addresses'
type Endpoint = NetworkIPAddress | NetworkMACAddress
type AssetChoice = { id: string; name: string }
const blankIP: IPAddressWrite = { address: '', subnet_id: '', hardware_asset_id: null, status: 'active', dns_name: '', description: '' }
const blankMAC: MACAddressWrite = { address: '', hardware_asset_id: null, description: '' }
const title = (kind: Kind) => kind === 'ip-addresses' ? 'IP address' : 'MAC address'
const message = (error: unknown) => error instanceof Error ? error.message : 'The network request failed.'

export function NetworkEndpoints({ workspace, client, kind, query, hardwareAssets }: {
  workspace: WorkspaceContext
  client: NetworksClient
  kind: Kind
  query: string
  hardwareAssets: AssetChoice[]
}) {
  const [records, setRecords] = useState<Endpoint[] | null>(null)
  const [subnets, setSubnets] = useState<NetworkSubnet[] | null>(null)
  const [canManage, setCanManage] = useState(false)
  const [form, setForm] = useState<IPAddressWrite | MACAddressWrite | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) { setRecords(null); setForm(null); setEditing(null); setError(null) }
    })
    const recordRequest = kind === 'ip-addresses'
      ? client.listIPAddresses(workspace, controller.signal)
      : client.listMACAddresses(workspace, controller.signal)
    Promise.all([recordRequest, client.listSubnets(workspace, controller.signal)])
      .then(([result, loadedSubnets]) => {
        setRecords(result.results)
        setCanManage(result.can_manage)
        setSubnets(loadedSubnets.results)
      })
      .catch((caught: unknown) => { if (!controller.signal.aborted) setError(message(caught)) })
    return () => controller.abort()
  }, [client, kind, workspace])

  const filtered = useMemo(
    () => (records ?? []).filter((record) => Object.values(record).join(' ').toLowerCase().includes(query.toLowerCase())),
    [query, records],
  )

  function beginEdit(record: Endpoint) {
    setEditing(record.id)
    if ('subnet_id' in record) {
      const value = record
      setForm({ address: value.address, subnet_id: value.subnet_id, hardware_asset_id: value.hardware_asset_id, status: value.status, dns_name: value.dns_name, description: value.description })
    } else {
      const value = record
      setForm({ address: value.address, hardware_asset_id: value.hardware_asset_id, description: value.description })
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!form) return
    setBusy(true); setError(null)
    try {
      const saved = 'subnet_id' in form
        ? (editing ? await client.updateIPAddress(workspace, editing, form) : await client.createIPAddress(workspace, form))
        : (editing ? await client.updateMACAddress(workspace, editing, form) : await client.createMACAddress(workspace, form))
      setRecords((items) => editing ? (items ?? []).map((item) => item.id === saved.id ? saved : item) : [...(items ?? []), saved])
      setForm(null); setEditing(null)
    } catch (caught) { setError(message(caught)) } finally { setBusy(false) }
  }

  const ipForm = kind === 'ip-addresses' ? form as IPAddressWrite | null : null
  const macForm = kind === 'mac-addresses' ? form : null
  const assetOptions = <><option value="">Unassigned</option>{hardwareAssets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</>

  return <div className="network-endpoints">
    <div className="network-subtoolbar"><p>{kind === 'ip-addresses' ? 'Host addresses assigned directly to hardware assets.' : 'Workspace-unique hardware addresses assigned directly to assets.'}</p>{canManage && <button className="primary-button" type="button" onClick={() => { setEditing(null); setForm(kind === 'ip-addresses' ? { ...blankIP } : { ...blankMAC }) }}><Plus size={15} />Add {title(kind)}</button>}</div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {form && <form className="network-form" onSubmit={(event) => void save(event)}><h2>{editing ? 'Edit' : 'Add'} {title(kind)}</h2><div className="field-grid">
      {ipForm && <><label><span>IP address</span><input required spellCheck="false" placeholder="192.0.2.10" value={ipForm.address} onChange={(event) => setForm({ ...ipForm, address: event.target.value })} /></label><label><span>Subnet</span><select required value={ipForm.subnet_id} onChange={(event) => setForm({ ...ipForm, subnet_id: event.target.value })}><option value="">Choose a subnet…</option>{subnets?.map((item) => <option key={item.id} value={item.id}>{item.cidr} · {item.name}</option>)}</select></label><label><span>Hardware asset</span><select value={ipForm.hardware_asset_id ?? ''} onChange={(event) => setForm({ ...ipForm, hardware_asset_id: event.target.value || null })}>{assetOptions}</select></label><label><span>Status</span><select value={ipForm.status} onChange={(event) => setForm({ ...ipForm, status: event.target.value as IPAddressWrite['status'] })}>{['active', 'reserved', 'dhcp', 'deprecated'].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>DNS name</span><input spellCheck="false" value={ipForm.dns_name} onChange={(event) => setForm({ ...ipForm, dns_name: event.target.value })} /></label></>}
      {macForm && <><label><span>MAC address</span><input required spellCheck="false" placeholder="02:00:00:00:00:01" value={macForm.address} onChange={(event) => setForm({ ...macForm, address: event.target.value })} /></label><label><span>Hardware asset</span><select value={macForm.hardware_asset_id ?? ''} onChange={(event) => setForm({ ...macForm, hardware_asset_id: event.target.value || null })}>{assetOptions}</select></label></>}
      <label className="field-wide"><span>Description</span><textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
    </div><div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : `Save ${title(kind)}`}</button><button className="secondary-button" type="button" onClick={() => setForm(null)}>{translate('common.cancel')}</button></div></form>}
    {records === null ? <p role="status">Loading {title(kind)} records…</p> : <div className="network-table-wrap"><table className="network-table"><thead><tr>{kind === 'ip-addresses' ? <><th>Address</th><th>Subnet</th><th>Hardware asset</th><th>DNS / status</th></> : <><th>MAC address</th><th>Hardware asset</th><th>Description</th></>}<th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filtered.map((record) => <tr key={record.id}>{'subnet_id' in record ? <><td><strong>{record.address}</strong></td><td>{record.subnet_cidr}{record.vrf_name ? ' · legacy VRF' : ''}</td><td>{record.hardware_asset_name ?? (record.interface_name ? `Legacy interface: ${record.interface_name}` : 'Unassigned')}</td><td>{record.dns_name || '—'} · {record.status}</td></> : <><td><strong>{record.address}</strong></td><td>{record.hardware_asset_name ?? (record.interface_name ? `Legacy interface: ${record.interface_name}` : 'Unassigned')}</td><td>{record.description || '—'}</td></>}<td>{canManage && <button className="row-action" type="button" onClick={() => beginEdit(record)}><Pencil size={14} />{translate('common.edit')}</button>}</td></tr>)}</tbody></table>{filtered.length === 0 && <p className="empty-state">No {title(kind)} records match this workspace and search.</p>}</div>}
  </div>
}
