import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Pencil, Plus } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type { DNSRecord, DNSRecordWrite, DNSZone, DNSZoneWrite, NetworksClient, WirelessNetwork, WirelessWrite } from './api'

const wirelessBlank: WirelessWrite = { ssid: '', purpose: 'corporate', security: 'wpa3_enterprise', status: 'active', hidden: false, client_isolation: false, site_id: null, vlan_id: null, subnet_id: null, description: '' }
const zoneBlank: DNSZoneWrite = { name: '', description: '' }
const recordBlank: DNSRecordWrite = { zone_id: '', owner_name: '', record_type: 'A', value: '', ttl: 3600, priority: null, weight: null, port: null, ip_address_id: null, description: '' }
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'The network service request failed.'

export function NetworkServices({ workspace, client, kind, query }: { workspace: WorkspaceContext; client: NetworksClient; kind: 'wireless' | 'dns'; query: string }) {
  const [wireless, setWireless] = useState<WirelessNetwork[] | null>(null)
  const [zones, setZones] = useState<DNSZone[] | null>(null)
  const [records, setRecords] = useState<DNSRecord[] | null>(null)
  const [choices, setChoices] = useState<Awaited<ReturnType<NetworksClient['choices']>> | null>(null)
  const [vlans, setVLANs] = useState<Awaited<ReturnType<NetworksClient['listVLANs']>>['results']>([])
  const [subnets, setSubnets] = useState<Awaited<ReturnType<NetworksClient['listSubnets']>>['results']>([])
  const [ips, setIPs] = useState<Awaited<ReturnType<NetworksClient['listIPAddresses']>>['results']>([])
  const [canManage, setCanManage] = useState(false)
  const [wirelessForm, setWirelessForm] = useState<WirelessWrite | null>(null)
  const [zoneForm, setZoneForm] = useState<DNSZoneWrite | null>(null)
  const [recordForm, setRecordForm] = useState<DNSRecordWrite | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.listWireless(workspace, controller.signal), client.listDNSZones(workspace, controller.signal), client.listDNSRecords(workspace, controller.signal), client.choices(workspace, controller.signal), client.listVLANs(workspace, controller.signal), client.listSubnets(workspace, controller.signal), client.listIPAddresses(workspace, controller.signal)])
      .then(([wirelessResult, zoneResult, recordResult, choiceResult, vlanResult, subnetResult, ipResult]) => {
        setWireless(wirelessResult.results); setZones(zoneResult.results); setRecords(recordResult.results); setChoices(choiceResult)
        setVLANs(vlanResult.results); setSubnets(subnetResult.results); setIPs(ipResult.results); setCanManage(wirelessResult.can_manage)
      }).catch((caught: unknown) => { if (!controller.signal.aborted) setError(errorMessage(caught)) })
    return () => controller.abort()
  }, [client, workspace])

  const normalized = query.toLowerCase()
  const shownWireless = useMemo(() => (wireless ?? []).filter((item) => `${item.ssid} ${item.purpose} ${item.security} ${item.site_name ?? ''} ${item.vlan_number ?? ''} ${item.subnet_cidr ?? ''}`.toLowerCase().includes(normalized)), [normalized, wireless])
  const shownZones = useMemo(() => (zones ?? []).filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(normalized)), [normalized, zones])
  const shownRecords = useMemo(() => (records ?? []).filter((item) => `${item.owner_name} ${item.record_type} ${item.value} ${item.zone_name}`.toLowerCase().includes(normalized)), [normalized, records])

  async function saveWireless(event: FormEvent) {
    event.preventDefault(); if (!wirelessForm) return; setBusy(true); setError(null)
    try { const saved = editing ? await client.updateWireless(workspace, editing, wirelessForm) : await client.createWireless(workspace, wirelessForm); setWireless((items) => editing ? (items ?? []).map((item) => item.id === saved.id ? saved : item) : [...(items ?? []), saved]); setWirelessForm(null); setEditing(null) }
    catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }
  async function saveZone(event: FormEvent) {
    event.preventDefault(); if (!zoneForm) return; setBusy(true); setError(null)
    try { const saved = editing ? await client.updateDNSZone(workspace, editing, zoneForm) : await client.createDNSZone(workspace, zoneForm); setZones((items) => editing ? (items ?? []).map((item) => item.id === saved.id ? saved : item) : [...(items ?? []), saved]); setZoneForm(null); setEditing(null) }
    catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }
  async function saveRecord(event: FormEvent) {
    event.preventDefault(); if (!recordForm) return; setBusy(true); setError(null)
    try { const saved = editing ? await client.updateDNSRecord(workspace, editing, recordForm) : await client.createDNSRecord(workspace, recordForm); setRecords((items) => editing ? (items ?? []).map((item) => item.id === saved.id ? saved : item) : [...(items ?? []), saved]); setRecordForm(null); setEditing(null) }
    catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }

  function editWireless(item: WirelessNetwork) { setEditing(item.id); setWirelessForm({ ssid: item.ssid, purpose: item.purpose, security: item.security, status: item.status, hidden: item.hidden, client_isolation: item.client_isolation, site_id: item.site_id, vlan_id: item.vlan_id, subnet_id: item.subnet_id, description: item.description }) }
  function editZone(item: DNSZone) { setEditing(item.id); setZoneForm({ name: item.name, description: item.description }) }
  function editRecord(item: DNSRecord) { setEditing(item.id); setRecordForm({ zone_id: item.zone_id, owner_name: item.owner_name, record_type: item.record_type, value: item.value, ttl: item.ttl, priority: item.priority, weight: item.weight, port: item.port, ip_address_id: item.ip_address_id, description: item.description }) }
  function cancel() { setWirelessForm(null); setZoneForm(null); setRecordForm(null); setEditing(null) }

  const selectedVLAN = wirelessForm?.vlan_id
  const eligibleSubnets = subnets.filter((item) => !selectedVLAN || item.vlan_id === selectedVLAN)
  if (wireless === null || zones === null || records === null || choices === null) return <p role="status">Loading network services…</p>
  return <>
    <div className="network-addressing-actions">
      {canManage && kind === 'wireless' && <button className="primary-button" type="button" onClick={() => { setEditing(null); setWirelessForm({ ...wirelessBlank }) }}><Plus size={15} />{translate('networks.addWirelessNetwork')}</button>}
      {canManage && kind === 'dns' && <><button className="secondary-button" type="button" onClick={() => { setEditing(null); setZoneForm({ ...zoneBlank }) }}><Plus size={15} />{translate('networks.addZone')}</button><button className="primary-button" type="button" disabled={zones.length === 0} onClick={() => { setEditing(null); setRecordForm({ ...recordBlank, zone_id: zones[0]?.id ?? '' }) }}><Plus size={15} />{translate('networks.addRecord')}</button></>}
    </div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {wirelessForm && <form className="network-form" onSubmit={(event) => void saveWireless(event)}><h2>{editing ? 'Edit' : 'Add'} wireless network</h2><p className="form-hint">Store security posture here, never a Wi-Fi password or RADIUS secret. Use an external credential reference for access material.</p><div className="field-grid">
      <label><span>SSID</span><input required value={wirelessForm.ssid} onChange={(event) => setWirelessForm({ ...wirelessForm, ssid: event.target.value })} /></label>
      <label><span>Purpose</span><select value={wirelessForm.purpose} onChange={(event) => setWirelessForm({ ...wirelessForm, purpose: event.target.value as WirelessWrite['purpose'] })}><option value="corporate">Corporate</option><option value="guest">Guest</option><option value="iot">IoT</option><option value="voice">Voice</option><option value="other">Other</option></select></label>
      <label><span>Security</span><select value={wirelessForm.security} onChange={(event) => setWirelessForm({ ...wirelessForm, security: event.target.value as WirelessWrite['security'] })}>{[['open','Open'],['owe','Enhanced open (OWE)'],['wpa2_personal','WPA2 Personal'],['wpa3_personal','WPA3 Personal'],['wpa2_enterprise','WPA2 Enterprise'],['wpa3_enterprise','WPA3 Enterprise'],['mixed_personal','WPA2/WPA3 Personal'],['mixed_enterprise','WPA2/WPA3 Enterprise']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label><span>Status</span><select value={wirelessForm.status} onChange={(event) => setWirelessForm({ ...wirelessForm, status: event.target.value as WirelessWrite['status'] })}><option value="planned">Planned</option><option value="active">Active</option><option value="disabled">Disabled</option><option value="retired">Retired</option></select></label>
      <label><span>Site</span><select value={wirelessForm.site_id ?? ''} onChange={(event) => setWirelessForm({ ...wirelessForm, site_id: event.target.value || null })}><option value="">All / unspecified sites</option>{choices.sites.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>VLAN</span><select value={wirelessForm.vlan_id ?? ''} onChange={(event) => setWirelessForm({ ...wirelessForm, vlan_id: event.target.value || null, subnet_id: null })}><option value="">No VLAN mapping</option>{vlans.map((item) => <option key={item.id} value={item.id}>{item.vlan_id} · {item.name}</option>)}</select></label>
      <label><span>Subnet</span><select value={wirelessForm.subnet_id ?? ''} onChange={(event) => setWirelessForm({ ...wirelessForm, subnet_id: event.target.value || null })}><option value="">No subnet mapping</option>{eligibleSubnets.map((item) => <option key={item.id} value={item.id}>{item.cidr}</option>)}</select></label>
      <label className="checkbox-field"><input type="checkbox" checked={wirelessForm.hidden} onChange={(event) => setWirelessForm({ ...wirelessForm, hidden: event.target.checked })} /><span>Hidden SSID</span></label><label className="checkbox-field"><input type="checkbox" checked={wirelessForm.client_isolation} onChange={(event) => setWirelessForm({ ...wirelessForm, client_isolation: event.target.checked })} /><span>Client isolation</span></label>
      <label className="field-span"><span>Notes (no secrets)</span><textarea value={wirelessForm.description} onChange={(event) => setWirelessForm({ ...wirelessForm, description: event.target.value })} /></label>
    </div><div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save wireless network'}</button><button className="secondary-button" type="button" onClick={cancel}>{translate('common.cancel')}</button></div></form>}
    {zoneForm && <form className="network-form" onSubmit={(event) => void saveZone(event)}><h2>{editing ? 'Edit' : 'Add'} DNS zone</h2><div className="field-grid"><label><span>Canonical zone name</span><input required placeholder="example.com" value={zoneForm.name} onChange={(event) => setZoneForm({ ...zoneForm, name: event.target.value })} /></label><label className="field-span"><span>Description</span><textarea value={zoneForm.description} onChange={(event) => setZoneForm({ ...zoneForm, description: event.target.value })} /></label></div><div className="form-actions"><button className="primary-button" disabled={busy}>{translate('networks.saveZone')}</button><button className="secondary-button" type="button" onClick={cancel}>{translate('common.cancel')}</button></div></form>}
    {recordForm && <form className="network-form" onSubmit={(event) => void saveRecord(event)}><h2>{editing ? 'Edit' : 'Add'} DNS record</h2><p className="form-hint">This is permission-scoped inventory. TekDocs does not publish, resolve, or validate live DNS in this milestone.</p><div className="field-grid">
      <label><span>Zone</span><select required value={recordForm.zone_id} onChange={(event) => setRecordForm({ ...recordForm, zone_id: event.target.value })}>{zones.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Owner name</span><input required placeholder="host.example.com" value={recordForm.owner_name} onChange={(event) => setRecordForm({ ...recordForm, owner_name: event.target.value })} /></label>
      <label><span>Type</span><select value={recordForm.record_type} onChange={(event) => setRecordForm({ ...recordForm, record_type: event.target.value as DNSRecordWrite['record_type'], priority: null, weight: null, port: null, ip_address_id: null })}>{['A','AAAA','CNAME','MX','TXT','SRV','CAA','NS','PTR'].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Value</span><input required value={recordForm.value} onChange={(event) => setRecordForm({ ...recordForm, value: event.target.value })} /></label><label><span>TTL</span><input type="number" min="0" max="2147483647" value={recordForm.ttl} onChange={(event) => setRecordForm({ ...recordForm, ttl: Number(event.target.value) })} /></label>
      {(recordForm.record_type === 'MX' || recordForm.record_type === 'SRV') && <label><span>Priority</span><input required type="number" min="0" max="65535" value={recordForm.priority ?? ''} onChange={(event) => setRecordForm({ ...recordForm, priority: event.target.value ? Number(event.target.value) : null })} /></label>}{recordForm.record_type === 'SRV' && <><label><span>Weight</span><input required type="number" min="0" max="65535" value={recordForm.weight ?? ''} onChange={(event) => setRecordForm({ ...recordForm, weight: event.target.value ? Number(event.target.value) : null })} /></label><label><span>Port</span><input required type="number" min="0" max="65535" value={recordForm.port ?? ''} onChange={(event) => setRecordForm({ ...recordForm, port: event.target.value ? Number(event.target.value) : null })} /></label></>}
      {(recordForm.record_type === 'A' || recordForm.record_type === 'AAAA') && <label><span>Linked IP inventory</span><select value={recordForm.ip_address_id ?? ''} onChange={(event) => { const ip = ips.find((item) => item.id === event.target.value); setRecordForm({ ...recordForm, ip_address_id: event.target.value || null, value: ip?.address ?? recordForm.value }) }}><option value="">No stable IP link</option>{ips.filter((item) => item.address_family === (recordForm.record_type === 'A' ? 4 : 6)).map((item) => <option key={item.id} value={item.id}>{item.address}</option>)}</select></label>}
      <label className="field-span"><span>Description</span><textarea value={recordForm.description} onChange={(event) => setRecordForm({ ...recordForm, description: event.target.value })} /></label>
    </div><div className="form-actions"><button className="primary-button" disabled={busy}>{translate('networks.saveDnsRecord')}</button><button className="secondary-button" type="button" onClick={cancel}>{translate('common.cancel')}</button></div></form>}
    {kind === 'wireless' ? <div className="network-table-wrap" role="group" aria-label={translate('networks.wirelessTable')} tabIndex={0}><table className="network-table"><thead><tr><th>SSID</th><th>Purpose / security</th><th>Network mapping</th><th>Controls</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{shownWireless.map((item) => <tr key={item.id}><td><strong>{item.ssid}</strong>{item.hidden ? ' · hidden' : ''}</td><td>{item.purpose} · {item.security.replaceAll('_', ' ')}</td><td>{item.site_name ?? 'All sites'} · {item.vlan_number ? `VLAN ${item.vlan_number}` : 'No VLAN'}{item.subnet_cidr ? ` · ${item.subnet_cidr}` : ''}</td><td>{item.client_isolation ? 'Client isolation' : 'Standard client access'}</td><td>{item.status}</td><td>{canManage && <button className="row-action" type="button" onClick={() => editWireless(item)}><Pencil size={14} />{translate('common.edit')}</button>}</td></tr>)}</tbody></table>{shownWireless.length === 0 && <p className="empty-state">No wireless networks match this workspace and search.</p>}</div> : <div className="dns-inventory"><section><div className="section-heading"><div><h2>Zones</h2><p>Inventoried DNS ownership boundaries.</p></div></div><div className="network-table-wrap" role="group" aria-label={translate('networks.dnsZoneTable')} tabIndex={0}><table className="network-table"><thead><tr><th>Zone</th><th>Records</th><th>Description</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{shownZones.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td><td>{item.record_count}</td><td>{item.description || '—'}</td><td>{canManage && <button className="row-action" type="button" onClick={() => editZone(item)}><Pencil size={14} />{translate('common.edit')}</button>}</td></tr>)}</tbody></table>{shownZones.length === 0 && <p className="empty-state">No DNS zones match this workspace and search.</p>}</div></section><section><div className="section-heading"><div><h2>Records</h2><p>Values are visible only to members authorized for this exact workspace.</p></div></div><div className="network-table-wrap" role="group" aria-label={translate('networks.dnsRecordTable')} tabIndex={0}><table className="network-table"><thead><tr><th>Owner</th><th>Type</th><th>Value</th><th>TTL</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{shownRecords.map((item) => <tr key={item.id}><td><strong>{item.owner_name}</strong><small>{item.zone_name}</small></td><td>{item.record_type}</td><td><code>{item.value}</code>{item.priority !== null ? ` · priority ${item.priority}` : ''}{item.port !== null ? ` · port ${item.port}` : ''}</td><td>{item.ttl}</td><td>{canManage && <button className="row-action" type="button" onClick={() => editRecord(item)}><Pencil size={14} />{translate('common.edit')}</button>}</td></tr>)}</tbody></table>{shownRecords.length === 0 && <p className="empty-state">No DNS records match this workspace and search.</p>}</div></section></div>}
  </>
}
