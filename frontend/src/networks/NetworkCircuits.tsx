import { useEffect, useMemo, useState } from 'react'
import { Pencil, Plus } from 'lucide-react'
import type { FormEvent } from 'react'
import type { WorkspaceContext } from '../workspaces/api'
import type { CircuitChoices, CircuitHandoff, CircuitWrite, HandoffWrite, NetworkCircuit, NetworksClient } from './api'

const blankCircuit: CircuitWrite = { name: '', provider_id: '', contract_id: null, service_identifier: '', kind: 'internet', status: 'active', bandwidth_down_mbps: null, bandwidth_up_mbps: null, installed_on: null, service_starts_on: null, review_on: null, planned_disconnect_on: null, description: '' }
const blankHandoff: HandoffWrite = { name: '', side: 'a', media: 'fiber', connector: '', provider_reference: '', site_id: null, location_id: null, device_id: null, interface_id: null, description: '' }
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'The circuit request failed.'

export function NetworkCircuits({ workspace, client, query }: { workspace: WorkspaceContext; client: NetworksClient; query: string }) {
  const [circuits, setCircuits] = useState<NetworkCircuit[] | null>(null)
  const [choices, setChoices] = useState<CircuitChoices | null>(null)
  const [canManage, setCanManage] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [circuitForm, setCircuitForm] = useState<CircuitWrite | null>(null)
  const [circuitEditing, setCircuitEditing] = useState<string | null>(null)
  const [handoffForm, setHandoffForm] = useState<HandoffWrite | null>(null)
  const [handoffEditing, setHandoffEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.listCircuits(workspace, controller.signal), client.circuitChoices(workspace, controller.signal)])
      .then(([result, loadedChoices]) => { setCircuits(result.results); setCanManage(result.can_manage); setChoices(loadedChoices) })
      .catch((caught) => { if (!controller.signal.aborted) setError(errorMessage(caught)) })
    return () => controller.abort()
  }, [client, workspace])

  const shown = useMemo(() => (circuits ?? []).filter((item) => `${item.name} ${item.provider_name} ${item.service_identifier} ${item.kind} ${item.status}`.toLowerCase().includes(query.toLowerCase())), [circuits, query])
  const selected = circuits?.find((item) => item.id === selectedId) ?? shown[0] ?? null
  const availableContracts = choices?.contracts.filter((item) => !circuitForm?.provider_id || item.provider_id === circuitForm.provider_id) ?? []
  const availableLocations = choices?.locations.filter((item) => item.site_id === handoffForm?.site_id) ?? []
  function editCircuit(item: NetworkCircuit) {
    setCircuitEditing(item.id)
    setCircuitForm({ name: item.name, provider_id: item.provider_id, contract_id: item.contract?.id ?? null, service_identifier: item.service_identifier, kind: item.kind, status: item.status, bandwidth_down_mbps: item.bandwidth_down_mbps, bandwidth_up_mbps: item.bandwidth_up_mbps, installed_on: item.installed_on, service_starts_on: item.service_starts_on, review_on: item.review_on, planned_disconnect_on: item.planned_disconnect_on, description: item.description })
  }
  function editHandoff(item: CircuitHandoff) {
    setHandoffEditing(item.id)
    setHandoffForm({ name: item.name, side: item.side, media: item.media, connector: item.connector, provider_reference: item.provider_reference, site_id: item.site_id, location_id: item.location_id, device_id: item.device_id, interface_id: item.interface_id, description: item.description })
  }
  async function saveCircuit(event: FormEvent) {
    event.preventDefault(); if (!circuitForm) return
    setBusy(true); setError(null)
    try {
      const values: Partial<CircuitWrite> = { ...circuitForm }
      if (!choices?.can_view_contracts) values.contract_id = undefined
      const saved = circuitEditing ? await client.updateCircuit(workspace, circuitEditing, values) : await client.createCircuit(workspace, { ...circuitForm, contract_id: choices?.can_view_contracts ? circuitForm.contract_id : null })
      setCircuits((items) => circuitEditing ? (items ?? []).map((item) => item.id === saved.id ? saved : item) : [...(items ?? []), saved])
      setSelectedId(saved.id); setCircuitForm(null); setCircuitEditing(null)
    } catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }
  async function saveHandoff(event: FormEvent) {
    event.preventDefault(); if (!handoffForm || !selected) return
    setBusy(true); setError(null)
    try {
      const saved = handoffEditing ? await client.updateCircuitHandoff(workspace, selected.id, handoffEditing, handoffForm) : await client.createCircuitHandoff(workspace, selected.id, handoffForm)
      setCircuits((items) => (items ?? []).map((item) => item.id !== selected.id ? item : { ...item, handoffs: handoffEditing ? item.handoffs.map((handoff) => handoff.id === saved.id ? saved : handoff) : [...item.handoffs, saved] }))
      setHandoffForm(null); setHandoffEditing(null)
    } catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }

  if (circuits === null || choices === null) return <p role="status">Loading circuits…</p>
  return <>
    <div className="subsection-toolbar"><div><h2>Circuits</h2><p>Provider services, demarcations, and upcoming lifecycle dates.</p></div>{canManage && <button className="primary-button" type="button" onClick={() => { setCircuitEditing(null); setCircuitForm({ ...blankCircuit }) }}><Plus size={15} />Add circuit</button>}</div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {circuitForm && <form className="network-form" onSubmit={(event) => void saveCircuit(event)}><h2>{circuitEditing ? 'Edit circuit' : 'Add circuit'}</h2><div className="field-grid">
      <label><span>Name</span><input required value={circuitForm.name} onChange={(event) => setCircuitForm({ ...circuitForm, name: event.target.value })} /></label>
      <label><span>Provider</span><select required value={circuitForm.provider_id} onChange={(event) => setCircuitForm({ ...circuitForm, provider_id: event.target.value, contract_id: null })}><option value="">Choose provider…</option>{choices.providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      {choices.can_view_contracts && <label><span>Contract</span><select value={circuitForm.contract_id ?? ''} onChange={(event) => setCircuitForm({ ...circuitForm, contract_id: event.target.value || null })}><option value="">No linked contract</option>{availableContracts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <label><span>Service identifier</span><input required autoComplete="off" value={circuitForm.service_identifier} onChange={(event) => setCircuitForm({ ...circuitForm, service_identifier: event.target.value })} /></label>
      <Choice label="Kind" value={circuitForm.kind} items={['internet','wan','mpls','dark_fiber','broadband','cellular','voice','other']} onChange={(kind) => setCircuitForm({ ...circuitForm, kind: kind as CircuitWrite['kind'] })} />
      <Choice label="Status" value={circuitForm.status} items={['ordered','provisioning','active','suspended','disconnected']} onChange={(status) => setCircuitForm({ ...circuitForm, status: status as CircuitWrite['status'] })} />
      <OptionalNumber label="Download Mbps" value={circuitForm.bandwidth_down_mbps} onChange={(bandwidth_down_mbps) => setCircuitForm({ ...circuitForm, bandwidth_down_mbps })} />
      <OptionalNumber label="Upload Mbps" value={circuitForm.bandwidth_up_mbps} onChange={(bandwidth_up_mbps) => setCircuitForm({ ...circuitForm, bandwidth_up_mbps })} />
      <OptionalDate label="Installed on" value={circuitForm.installed_on} onChange={(installed_on) => setCircuitForm({ ...circuitForm, installed_on })} />
      <OptionalDate label="Service starts" value={circuitForm.service_starts_on} onChange={(service_starts_on) => setCircuitForm({ ...circuitForm, service_starts_on })} />
      <OptionalDate label="Review on" value={circuitForm.review_on} onChange={(review_on) => setCircuitForm({ ...circuitForm, review_on })} />
      <OptionalDate label="Planned disconnect" value={circuitForm.planned_disconnect_on} onChange={(planned_disconnect_on) => setCircuitForm({ ...circuitForm, planned_disconnect_on })} />
      <label className="field-span"><span>Description</span><textarea value={circuitForm.description} onChange={(event) => setCircuitForm({ ...circuitForm, description: event.target.value })} /></label>
    </div><Actions busy={busy} cancel={() => setCircuitForm(null)} label="Save circuit" /></form>}
    {handoffForm && selected && <form className="network-form" onSubmit={(event) => void saveHandoff(event)}><h2>{handoffEditing ? 'Edit handoff' : `Add handoff to ${selected.name}`}</h2><div className="field-grid">
      <label><span>Name</span><input required value={handoffForm.name} onChange={(event) => setHandoffForm({ ...handoffForm, name: event.target.value })} /></label>
      <Choice label="Side" value={handoffForm.side} items={['a','z']} onChange={(side) => setHandoffForm({ ...handoffForm, side: side as HandoffWrite['side'] })} />
      <Choice label="Media" value={handoffForm.media} items={['copper','fiber','coax','wireless','virtual','other']} onChange={(media) => setHandoffForm({ ...handoffForm, media: media as HandoffWrite['media'] })} />
      <label><span>Connector</span><input value={handoffForm.connector} placeholder="LC, RJ45, virtual…" onChange={(event) => setHandoffForm({ ...handoffForm, connector: event.target.value })} /></label>
      <label><span>Provider handoff reference</span><input value={handoffForm.provider_reference} onChange={(event) => setHandoffForm({ ...handoffForm, provider_reference: event.target.value })} /></label>
      <label><span>Site</span><select value={handoffForm.site_id ?? ''} onChange={(event) => setHandoffForm({ ...handoffForm, site_id: event.target.value || null, location_id: null })}><option value="">No site</option>{choices.sites.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>Location</span><select disabled={!handoffForm.site_id} value={handoffForm.location_id ?? ''} onChange={(event) => setHandoffForm({ ...handoffForm, location_id: event.target.value || null })}><option value="">No structured location</option>{availableLocations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>Device</span><select value={handoffForm.device_id ?? ''} onChange={(event) => setHandoffForm({ ...handoffForm, device_id: event.target.value || null, interface_id: null })}><option value="">No device</option>{choices.devices.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label className="field-span"><span>Description</span><textarea value={handoffForm.description} onChange={(event) => setHandoffForm({ ...handoffForm, description: event.target.value })} /></label>
    </div><Actions busy={busy} cancel={() => setHandoffForm(null)} label="Save handoff" /></form>}
    <div className="inventory-layout circuit-layout"><section className="network-table-wrap"><table className="network-table"><thead><tr><th>Circuit</th><th>Provider</th><th>Bandwidth</th><th>Next lifecycle date</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{shown.map((item) => <tr key={item.id} className={selected?.id === item.id ? 'selected' : undefined}><td><button className="network-record-link" type="button" onClick={() => setSelectedId(item.id)}>{item.name}</button><small>{item.service_identifier}</small></td><td>{item.provider_name}</td><td>{bandwidth(item)}</td><td>{item.lifecycle_events[0] ? `${item.lifecycle_events[0].date} · ${item.lifecycle_events[0].label}` : 'Not scheduled'}</td><td>{item.status}</td><td>{canManage && <button className="row-action" type="button" onClick={() => editCircuit(item)}><Pencil size={14} />Edit</button>}</td></tr>)}</tbody></table>{shown.length === 0 && <p className="empty-state">No circuits match this workspace and search.</p>}</section>
      <section className="content-section circuit-detail">{selected ? <><div className="section-heading"><div><h2>{selected.name}</h2><p>{selected.provider_name} · {selected.kind.replace('_', ' ')}</p></div>{canManage && <button className="secondary-button" type="button" onClick={() => { setHandoffEditing(null); setHandoffForm({ ...blankHandoff }) }}><Plus size={15} />Add handoff</button>}</div><dl className="inventory-provenance"><div><dt>Service ID</dt><dd>{selected.service_identifier}</dd></div><div><dt>Term</dt><dd>{selected.service_starts_on ?? 'Open'} – {selected.planned_disconnect_on ?? 'Open'}</dd></div>{selected.contract && <div><dt>Contract</dt><dd>{selected.contract.name}</dd></div>}<div><dt>Installed</dt><dd>{selected.installed_on ?? 'Not recorded'}</dd></div></dl>
        <h3>Lifecycle dates</h3>{selected.lifecycle_events.length ? <ul className="plain-detail-list">{selected.lifecycle_events.map((item) => <li key={`${item.kind}-${item.date}`}><strong>{item.date}</strong><span>{item.label}{item.state === 'overdue' ? ' · overdue' : item.state === 'today' ? ' · today' : ''}</span></li>)}</ul> : <p className="empty-state">No lifecycle dates are scheduled.</p>}
        <div className="section-heading"><h3>Handoffs</h3></div>{selected.handoffs.length ? <ul className="plain-detail-list">{selected.handoffs.map((item) => <li key={item.id}><div><strong>{item.name}</strong><span>{item.side.toUpperCase()} side · {item.media}{item.connector ? ` · ${item.connector}` : ''} · {item.interface_name ?? item.device_name ?? item.location_name ?? item.site_name ?? 'Unplaced'}</span></div>{canManage && <button className="text-button" type="button" onClick={() => editHandoff(item)}>Edit</button>}</li>)}</ul> : <p className="empty-state">No handoffs have been recorded.</p>}</> : <p className="empty-state">Choose a circuit to inspect its handoffs and lifecycle dates.</p>}</section></div>
  </>
}

function bandwidth(item: NetworkCircuit) { return item.bandwidth_down_mbps || item.bandwidth_up_mbps ? `${item.bandwidth_down_mbps ?? '—'} / ${item.bandwidth_up_mbps ?? '—'} Mbps` : 'Not recorded' }
function OptionalDate({ label, value, onChange }: { label: string; value: string | null; onChange: (value: string | null) => void }) { return <label><span>{label}</span><input type="date" value={value ?? ''} onChange={(event) => onChange(event.target.value || null)} /></label> }
function OptionalNumber({ label, value, onChange }: { label: string; value: string | null; onChange: (value: string | null) => void }) { return <label><span>{label}</span><input type="number" min="0.001" step="0.001" value={value ?? ''} onChange={(event) => onChange(event.target.value || null)} /></label> }
function Choice({ label, value, items, onChange }: { label: string; value: string; items: string[]; onChange: (value: string) => void }) { return <label><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}>{items.map((item) => <option key={item} value={item}>{item === 'a' || item === 'z' ? `${item.toUpperCase()} side` : item.replace('_', ' ')}</option>)}</select></label> }
function Actions({ busy, cancel, label }: { busy: boolean; cancel: () => void; label: string }) { return <div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : label}</button><button className="secondary-button" type="button" onClick={cancel}>Cancel</button></div> }
