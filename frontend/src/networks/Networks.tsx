import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Cable, Download, Pencil, Plus, Search } from 'lucide-react'
import type { RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { NetworkRelationships } from './NetworkRelationships'
import { NetworkAddressing } from './NetworkAddressing'
import { NetworkEndpoints } from './NetworkEndpoints'
import { NetworkServices } from './NetworkServices'
import { NetworkCircuits } from './NetworkCircuits'
import { NetworkNetBox } from './NetworkNetBox'
import { NetworkSearch } from './NetworkSearch'
import { browserNetworksClient } from './api'
import type { DeviceListResult, DeviceWrite, NetworkChoices, NetworkDevice, NetworkRack, NetworkSearchItem, NetworksClient, RackWrite } from './api'

const blankRack: RackWrite = { name: '', site_id: '', location_id: null, unit_count: 42, status: 'active' }
const blankDevice: DeviceWrite = { name: '', role: 'switch', status: 'active', hardware_asset_id: null, site_id: null, location_id: null, rack_id: null, rack_unit: null, rack_units: 1 }
const roleLabel = (value: NetworkDevice['role']) => value.split('_').map((part) => part[0]?.toUpperCase() + part.slice(1)).join(' ')
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'The network request failed.'

export function Networks({ workspace, client = browserNetworksClient, relationshipsClient }: { workspace: WorkspaceContext; client?: NetworksClient; relationshipsClient: RelationshipsClient }) {
  const [racks, setRacks] = useState<NetworkRack[] | null>(null)
  const [deviceResult, setDeviceResult] = useState<DeviceListResult | null>(null)
  const [choices, setChoices] = useState<NetworkChoices | null>(null)
  const [view, setView] = useState<'all' | 'devices' | 'racks' | 'interfaces' | 'ip-addresses' | 'mac-addresses' | 'subnets' | 'vlans' | 'vrfs' | 'circuits' | 'wireless' | 'dns' | 'netbox'>('devices')
  const [query, setQuery] = useState('')
  const [rackForm, setRackForm] = useState<RackWrite | null>(null)
  const [rackEditing, setRackEditing] = useState<string | null>(null)
  const [deviceForm, setDeviceForm] = useState<DeviceWrite | null>(null)
  const [deviceEditing, setDeviceEditing] = useState<string | null>(null)
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) { setRacks(null); setDeviceResult(null); setChoices(null); setError(null) }
    })
    Promise.all([client.listRacks(workspace, controller.signal), client.listDevices(workspace, controller.signal), client.choices(workspace, controller.signal)])
      .then(([rackResult, devices, loadedChoices]) => { setRacks(rackResult.results); setDeviceResult(devices); setChoices(loadedChoices) })
      .catch((caught: unknown) => { if (!controller.signal.aborted) setError(errorMessage(caught)) })
    return () => controller.abort()
  }, [client, workspace])

  const filteredRacks = useMemo(() => (racks ?? []).filter((item) => `${item.name} ${item.site_name} ${item.location_name ?? ''}`.toLowerCase().includes(query.toLowerCase())), [query, racks])
  const filteredDevices = useMemo(() => (deviceResult?.results ?? []).filter((item) => `${item.name} ${item.role} ${item.site_name ?? ''} ${item.rack_name ?? ''}`.toLowerCase().includes(query.toLowerCase())), [deviceResult, query])
  const selected = deviceResult?.results.find((item) => item.id === selectedDevice) ?? null
  const locationsForSite = (siteId: string | null) => choices?.locations.filter((item) => item.site_id === siteId) ?? []

  async function saveRack(event: FormEvent) {
    event.preventDefault(); if (!rackForm) return
    setBusy(true); setError(null)
    try {
      const saved = rackEditing ? await client.updateRack(workspace, rackEditing, rackForm) : await client.createRack(workspace, rackForm)
      setRacks((items) => rackEditing ? (items ?? []).map((item) => item.id === saved.id ? saved : item) : [...(items ?? []), saved])
      setChoices((items) => items ? { ...items, racks: [...items.racks.filter((item) => item.id !== saved.id), { id: saved.id, name: saved.name, site_id: saved.site_id }] } : items)
      setRackForm(null); setRackEditing(null)
    } catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }

  async function saveDevice(event: FormEvent) {
    event.preventDefault(); if (!deviceForm) return
    setBusy(true); setError(null)
    try {
      const saved = deviceEditing ? await client.updateDevice(workspace, deviceEditing, deviceForm) : await client.createDevice(workspace, deviceForm)
      setDeviceResult((items) => items ? { ...items, results: deviceEditing ? items.results.map((item) => item.id === saved.id ? saved : item) : [...items.results, saved], count: deviceEditing ? items.count : items.count + 1 } : items)
      setDeviceForm(null); setDeviceEditing(null); setSelectedDevice(saved.id)
      const rackResult = await client.listRacks(workspace); setRacks(rackResult.results)
    } catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }

  function editRack(item: NetworkRack) { setRackEditing(item.id); setRackForm({ name: item.name, site_id: item.site_id, location_id: item.location_id, unit_count: item.unit_count, status: item.status }) }
  function editDevice(item: NetworkDevice) { setDeviceEditing(item.id); setDeviceForm({ name: item.name, role: item.role, status: item.status, hardware_asset_id: item.hardware_asset_id, site_id: item.site_id, location_id: item.location_id, rack_id: item.rack_id, rack_unit: item.rack_unit, rack_units: item.rack_units }) }
  function openSearchResult(item: NetworkSearchItem) {
    setView(item.section)
    setQuery(item.name)
    if (item.record_type === 'network_device') setSelectedDevice(item.id)
  }

  return <>
    <header className="page-header"><div><h1>Networks</h1><p>Physical inventory, routing, and endpoint assignments for {workspace.name}.</p></div></header>
    <section className="content-section network-inventory">
      <div className="network-toolbar"><div className="segmented-control" aria-label="Network record type">{(['all', 'devices', 'racks', 'interfaces', 'ip-addresses', 'mac-addresses', 'subnets', 'vlans', 'vrfs', 'circuits', 'wireless', 'dns', 'netbox'] as const).map((item) => <button key={item} type="button" aria-pressed={view === item} onClick={() => setView(item)}>{item === 'all' ? 'All records' : item === 'vrfs' ? 'VRFs' : item === 'dns' ? 'DNS' : item === 'netbox' ? 'NetBox' : item === 'ip-addresses' ? 'IP addresses' : item === 'mac-addresses' ? 'MAC addresses' : item[0].toUpperCase() + item.slice(1)}</button>)}</div><label className="network-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search network inventory</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this workspace" /></label><a className="secondary-button" href={client.networkExportUrl(workspace)}><Download size={15} aria-hidden="true" />Export CSV</a>{deviceResult?.can_manage && (view === 'devices' || view === 'racks') && <button className="primary-button" type="button" onClick={() => view === 'racks' ? (setRackEditing(null), setRackForm({ ...blankRack })) : (setDeviceEditing(null), setDeviceForm({ ...blankDevice }))}><Plus size={15} />Add {view === 'racks' ? 'rack' : 'device'}</button>}</div>
      {error && <div className="form-error" role="alert">{error}</div>}

      {rackForm && choices && <form className="network-form" onSubmit={(event) => void saveRack(event)}><h2>{rackEditing ? 'Edit rack' : 'Add rack'}</h2><div className="field-grid"><label><span>Name</span><input required value={rackForm.name} onChange={(event) => setRackForm({ ...rackForm, name: event.target.value })} /></label><label><span>Site</span><select required value={rackForm.site_id} onChange={(event) => setRackForm({ ...rackForm, site_id: event.target.value, location_id: null })}><option value="">Choose a site…</option>{choices.sites.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Location</span><select value={rackForm.location_id ?? ''} onChange={(event) => setRackForm({ ...rackForm, location_id: event.target.value || null })}><option value="">No structured location</option>{locationsForSite(rackForm.site_id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Rack units</span><input type="number" min="1" max="100" value={rackForm.unit_count} onChange={(event) => setRackForm({ ...rackForm, unit_count: Number(event.target.value) })} /></label><label><span>Status</span><select value={rackForm.status} onChange={(event) => setRackForm({ ...rackForm, status: event.target.value as RackWrite['status'] })}><option value="planned">Planned</option><option value="active">Active</option><option value="retired">Retired</option></select></label></div><div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save rack'}</button><button className="secondary-button" type="button" onClick={() => setRackForm(null)}>Cancel</button></div></form>}

      {deviceForm && choices && <form className="network-form" onSubmit={(event) => void saveDevice(event)}><h2>{deviceEditing ? 'Edit device' : 'Add device'}</h2><div className="field-grid"><label><span>Name</span><input required value={deviceForm.name} onChange={(event) => setDeviceForm({ ...deviceForm, name: event.target.value })} /></label><label><span>Role</span><select value={deviceForm.role} onChange={(event) => setDeviceForm({ ...deviceForm, role: event.target.value as DeviceWrite['role'] })}>{(['router', 'switch', 'firewall', 'wireless_controller', 'access_point', 'load_balancer', 'other'] as const).map((value) => <option key={value} value={value}>{roleLabel(value)}</option>)}</select></label><label><span>Status</span><select value={deviceForm.status} onChange={(event) => setDeviceForm({ ...deviceForm, status: event.target.value as DeviceWrite['status'] })}><option value="planned">Planned</option><option value="active">Active</option><option value="offline">Offline</option><option value="retired">Retired</option></select></label><label><span>Hardware asset</span><select value={deviceForm.hardware_asset_id ?? ''} onChange={(event) => setDeviceForm({ ...deviceForm, hardware_asset_id: event.target.value || null })}><option value="">No linked asset</option>{choices.hardware_assets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Rack</span><select value={deviceForm.rack_id ?? ''} onChange={(event) => { const rack = racks?.find((item) => item.id === event.target.value); setDeviceForm({ ...deviceForm, rack_id: event.target.value || null, site_id: rack?.site_id ?? deviceForm.site_id, location_id: rack?.location_id ?? deviceForm.location_id, rack_unit: event.target.value ? (deviceForm.rack_unit ?? 1) : null, rack_units: event.target.value ? deviceForm.rack_units : 1 }) }}><option value="">No rack placement</option>{choices.racks.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{deviceForm.rack_id ? <><label><span>Starting unit</span><input type="number" min="1" max="100" required value={deviceForm.rack_unit ?? 1} onChange={(event) => setDeviceForm({ ...deviceForm, rack_unit: Number(event.target.value) })} /></label><label><span>Height (U)</span><input type="number" min="1" max="100" required value={deviceForm.rack_units} onChange={(event) => setDeviceForm({ ...deviceForm, rack_units: Number(event.target.value) })} /></label></> : <><label><span>Site</span><select value={deviceForm.site_id ?? ''} onChange={(event) => setDeviceForm({ ...deviceForm, site_id: event.target.value || null, location_id: null })}><option value="">Unplaced</option>{choices.sites.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Location</span><select value={deviceForm.location_id ?? ''} disabled={!deviceForm.site_id} onChange={(event) => setDeviceForm({ ...deviceForm, location_id: event.target.value || null })}><option value="">No structured location</option>{locationsForSite(deviceForm.site_id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></>}</div><div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save device'}</button><button className="secondary-button" type="button" onClick={() => setDeviceForm(null)}>Cancel</button></div></form>}

      {view === 'all' && <NetworkSearch key={`${workspace.kind}:${workspace.id}:${query}`} workspace={workspace} client={client} query={query} onOpen={openSearchResult} />}
      {(view === 'subnets' || view === 'vlans' || view === 'vrfs') && <NetworkAddressing workspace={workspace} client={client} kind={view} query={query} />}
      {(view === 'interfaces' || view === 'ip-addresses' || view === 'mac-addresses') && <NetworkEndpoints workspace={workspace} client={client} kind={view} query={query} />}
      {(view === 'wireless' || view === 'dns') && <NetworkServices workspace={workspace} client={client} kind={view} query={query} />}
      {view === 'circuits' && <NetworkCircuits workspace={workspace} client={client} query={query} />}
      {view === 'netbox' && <NetworkNetBox workspace={workspace} client={client} query={query} />}
      {view === 'all' || view === 'subnets' || view === 'vlans' || view === 'vrfs' || view === 'interfaces' || view === 'ip-addresses' || view === 'mac-addresses' || view === 'circuits' || view === 'wireless' || view === 'dns' || view === 'netbox' ? null : racks === null || deviceResult === null ? <p role="status">Loading network inventory…</p> : view === 'racks' ? <div className="network-table-wrap"><table className="network-table"><thead><tr><th>Name</th><th>Site / location</th><th>Capacity</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filteredRacks.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td><td>{item.site_name}{item.location_name ? ` · ${item.location_name}` : ''}</td><td>{item.unit_count}U · {item.device_count} devices</td><td>{item.status}</td><td>{deviceResult.can_manage && <button className="row-action" type="button" onClick={() => editRack(item)}><Pencil size={14} />Edit</button>}</td></tr>)}</tbody></table>{filteredRacks.length === 0 && <p className="empty-state">No racks match this workspace and search.</p>}</div> : <div className="network-table-wrap"><table className="network-table"><thead><tr><th>Name</th><th>Role</th><th>Physical placement</th><th>Asset</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filteredDevices.map((item) => <tr key={item.id} className={selectedDevice === item.id ? 'selected' : undefined}><td><button className="network-record-link" type="button" onClick={() => setSelectedDevice(item.id)}>{item.name}</button></td><td>{roleLabel(item.role)}</td><td>{item.rack_name ? `${item.rack_name} · U${item.rack_unit}${item.rack_units > 1 ? `–${(item.rack_unit ?? 0) + item.rack_units - 1}` : ''}` : item.location_name ?? item.site_name ?? 'Unplaced'}</td><td>{item.hardware_asset_name ?? '—'}</td><td>{item.status}</td><td>{deviceResult.can_manage && <button className="row-action" type="button" onClick={() => editDevice(item)}><Pencil size={14} />Edit</button>}</td></tr>)}</tbody></table>{filteredDevices.length === 0 && <p className="empty-state">No network devices match this workspace and search.</p>}</div>}
    </section>
    {selected && deviceResult?.can_view_relationships && <section className="content-section network-device-detail"><div className="section-heading"><div><h2><Cable size={18} aria-hidden="true" />{selected.name}</h2><p>{roleLabel(selected.role)} · {selected.rack_name ?? selected.location_name ?? selected.site_name ?? 'Unplaced'}</p></div></div><NetworkRelationships key={selected.id} workspace={workspace} deviceId={selected.id} deviceName={selected.name} canCreate={deviceResult.can_create_relationships} canArchive={deviceResult.can_archive_relationships} client={relationshipsClient} /></section>}
  </>
}
