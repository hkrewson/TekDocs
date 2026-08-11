import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Pencil, Plus } from 'lucide-react'
import type { WorkspaceContext } from '../workspaces/api'
import type { DeviceListResult, InterfaceWrite, IPAddressWrite, MACAddressWrite, NetworkIPAddress, NetworkInterface, NetworkMACAddress, NetworkSubnet, NetworksClient } from './api'

type Kind = 'interfaces' | 'ip-addresses' | 'mac-addresses'
type Endpoint = NetworkInterface | NetworkIPAddress | NetworkMACAddress
const blankInterface: InterfaceWrite = { name: '', device_id: '', kind: 'physical', status: 'active', description: '' }
const blankIP: IPAddressWrite = { address: '', subnet_id: '', interface_id: null, status: 'active', dns_name: '', description: '' }
const blankMAC: MACAddressWrite = { address: '', interface_id: null, description: '' }
const title = (kind: Kind) => kind === 'ip-addresses' ? 'IP address' : kind === 'mac-addresses' ? 'MAC address' : 'interface'
const message = (error: unknown) => error instanceof Error ? error.message : 'The network request failed.'

export function NetworkEndpoints({ workspace, client, kind, query }: { workspace: WorkspaceContext; client: NetworksClient; kind: Kind; query: string }) {
  const [records, setRecords] = useState<Endpoint[] | null>(null)
  const [devices, setDevices] = useState<DeviceListResult | null>(null)
  const [subnets, setSubnets] = useState<NetworkSubnet[] | null>(null)
  const [interfaces, setInterfaces] = useState<NetworkInterface[] | null>(null)
  const [form, setForm] = useState<InterfaceWrite | IPAddressWrite | MACAddressWrite | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) { setRecords(null); setForm(null); setEditing(null); setError(null) }
    })
    const recordRequest = kind === 'interfaces' ? client.listInterfaces(workspace, controller.signal) : kind === 'ip-addresses' ? client.listIPAddresses(workspace, controller.signal) : client.listMACAddresses(workspace, controller.signal)
    Promise.all([recordRequest, client.listDevices(workspace, controller.signal), client.listSubnets(workspace, controller.signal), client.listInterfaces(workspace, controller.signal)])
      .then(([result, loadedDevices, loadedSubnets, loadedInterfaces]) => { setRecords(result.results); setDevices(loadedDevices); setSubnets(loadedSubnets.results); setInterfaces(loadedInterfaces.results) })
      .catch((caught: unknown) => { if (!controller.signal.aborted) setError(message(caught)) })
    return () => controller.abort()
  }, [client, kind, workspace])

  const filtered = useMemo(() => (records ?? []).filter((record) => Object.values(record).join(' ').toLowerCase().includes(query.toLowerCase())), [query, records])
  const canManage = devices?.can_manage ?? false

  function beginAdd() {
    setEditing(null)
    setForm(kind === 'interfaces' ? { ...blankInterface } : kind === 'ip-addresses' ? { ...blankIP } : { ...blankMAC })
  }

  function beginEdit(record: Endpoint) {
    setEditing(record.id)
    if (kind === 'interfaces') { const value = record as NetworkInterface; setForm({ name: value.name, device_id: value.device_id, kind: value.kind, status: value.status, description: value.description }) }
    else if (kind === 'ip-addresses') { const value = record as NetworkIPAddress; setForm({ address: value.address, subnet_id: value.subnet_id, interface_id: value.interface_id, status: value.status, dns_name: value.dns_name, description: value.description }) }
    else { const value = record as NetworkMACAddress; setForm({ address: value.address, interface_id: value.interface_id, description: value.description }) }
  }

  async function save(event: FormEvent) {
    event.preventDefault(); if (!form) return
    setBusy(true); setError(null)
    try {
      let saved: Endpoint
      if (kind === 'interfaces') saved = editing ? await client.updateInterface(workspace, editing, form as InterfaceWrite) : await client.createInterface(workspace, form as InterfaceWrite)
      else if (kind === 'ip-addresses') saved = editing ? await client.updateIPAddress(workspace, editing, form as IPAddressWrite) : await client.createIPAddress(workspace, form as IPAddressWrite)
      else saved = editing ? await client.updateMACAddress(workspace, editing, form as MACAddressWrite) : await client.createMACAddress(workspace, form as MACAddressWrite)
      setRecords((items) => editing ? (items ?? []).map((item) => item.id === saved.id ? saved : item) : [...(items ?? []), saved])
      if (kind === 'interfaces') setInterfaces((items) => editing ? (items ?? []).map((item) => item.id === saved.id ? saved as NetworkInterface : item) : [...(items ?? []), saved as NetworkInterface])
      setForm(null); setEditing(null)
    } catch (caught) { setError(message(caught)) } finally { setBusy(false) }
  }

  const interfaceForm = kind === 'interfaces' ? form as InterfaceWrite | null : null
  const ipForm = kind === 'ip-addresses' ? form as IPAddressWrite | null : null
  const macForm = kind === 'mac-addresses' ? form as MACAddressWrite | null : null
  const assignmentOptions = <><option value="">Unassigned</option>{interfaces?.map((item) => <option key={item.id} value={item.id}>{item.device_name} · {item.name}</option>)}</>

  return <div className="network-endpoints">
    <div className="network-subtoolbar"><p>{kind === 'interfaces' ? 'Device ports and logical adapters.' : kind === 'ip-addresses' ? 'Host addresses within a subnet and routing namespace.' : 'Workspace-unique hardware addresses.'}</p>{canManage && <button className="primary-button" type="button" onClick={beginAdd}><Plus size={15} />Add {title(kind)}</button>}</div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {form && <form className="network-form" onSubmit={(event) => void save(event)}><h2>{editing ? 'Edit' : 'Add'} {title(kind)}</h2><div className="field-grid">
      {interfaceForm && <><label><span>Name</span><input required value={interfaceForm.name} onChange={(event) => setForm({ ...interfaceForm, name: event.target.value })} /></label><label><span>Device</span><select required value={interfaceForm.device_id} onChange={(event) => setForm({ ...interfaceForm, device_id: event.target.value })}><option value="">Choose a device…</option>{devices?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Kind</span><select value={interfaceForm.kind} onChange={(event) => setForm({ ...interfaceForm, kind: event.target.value as InterfaceWrite['kind'] })}>{['physical', 'virtual', 'lag', 'loopback', 'tunnel', 'wireless', 'other'].map((value) => <option key={value} value={value}>{value === 'lag' ? 'Link aggregation' : value[0].toUpperCase() + value.slice(1)}</option>)}</select></label><label><span>Status</span><select value={interfaceForm.status} onChange={(event) => setForm({ ...interfaceForm, status: event.target.value as InterfaceWrite['status'] })}>{['planned', 'active', 'disabled', 'retired'].map((value) => <option key={value}>{value}</option>)}</select></label></>}
      {ipForm && <><label><span>IP address</span><input required spellCheck="false" placeholder="192.0.2.10" value={ipForm.address} onChange={(event) => setForm({ ...ipForm, address: event.target.value })} /></label><label><span>Subnet</span><select required value={ipForm.subnet_id} onChange={(event) => setForm({ ...ipForm, subnet_id: event.target.value })}><option value="">Choose a subnet…</option>{subnets?.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.cidr}{item.vrf_name ? ` · ${item.vrf_name}` : ''}</option>)}</select></label><label><span>Interface</span><select value={ipForm.interface_id ?? ''} onChange={(event) => setForm({ ...ipForm, interface_id: event.target.value || null })}>{assignmentOptions}</select></label><label><span>Status</span><select value={ipForm.status} onChange={(event) => setForm({ ...ipForm, status: event.target.value as IPAddressWrite['status'] })}>{['active', 'reserved', 'dhcp', 'deprecated'].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>DNS name</span><input spellCheck="false" value={ipForm.dns_name} onChange={(event) => setForm({ ...ipForm, dns_name: event.target.value })} /></label></>}
      {macForm && <><label><span>MAC address</span><input required spellCheck="false" placeholder="02:00:00:00:00:01" value={macForm.address} onChange={(event) => setForm({ ...macForm, address: event.target.value })} /></label><label><span>Interface</span><select value={macForm.interface_id ?? ''} onChange={(event) => setForm({ ...macForm, interface_id: event.target.value || null })}>{assignmentOptions}</select></label></>}
      <label className="field-wide"><span>Description</span><textarea rows={2} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
    </div><div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : `Save ${title(kind)}`}</button><button className="secondary-button" type="button" onClick={() => setForm(null)}>Cancel</button></div></form>}
    {records === null ? <p role="status">Loading {title(kind)} records…</p> : <div className="network-table-wrap"><table className="network-table"><thead><tr>{kind === 'interfaces' ? <><th>Name</th><th>Device</th><th>Kind</th><th>Status</th></> : kind === 'ip-addresses' ? <><th>Address</th><th>Subnet / VRF</th><th>Assignment</th><th>DNS / status</th></> : <><th>MAC address</th><th>Assignment</th><th>Description</th></>}<th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filtered.map((record) => <tr key={record.id}>{kind === 'interfaces' ? <><td><strong>{(record as NetworkInterface).name}</strong></td><td>{(record as NetworkInterface).device_name}</td><td>{(record as NetworkInterface).kind}</td><td>{(record as NetworkInterface).status}</td></> : kind === 'ip-addresses' ? <><td><strong>{(record as NetworkIPAddress).address}</strong></td><td>{(record as NetworkIPAddress).subnet_cidr}{(record as NetworkIPAddress).vrf_name ? ` · ${(record as NetworkIPAddress).vrf_name}` : ''}</td><td>{(record as NetworkIPAddress).device_name ? `${(record as NetworkIPAddress).device_name} · ${(record as NetworkIPAddress).interface_name}` : 'Unassigned'}</td><td>{(record as NetworkIPAddress).dns_name || '—'} · {(record as NetworkIPAddress).status}</td></> : <><td><strong>{(record as NetworkMACAddress).address}</strong></td><td>{(record as NetworkMACAddress).device_name ? `${(record as NetworkMACAddress).device_name} · ${(record as NetworkMACAddress).interface_name}` : 'Unassigned'}</td><td>{(record as NetworkMACAddress).description || '—'}</td></>}<td>{canManage && <button className="row-action" type="button" onClick={() => beginEdit(record)}><Pencil size={14} />Edit</button>}</td></tr>)}</tbody></table>{filtered.length === 0 && <p className="empty-state">No {title(kind)} records match this workspace and search.</p>}</div>}
  </div>
}
