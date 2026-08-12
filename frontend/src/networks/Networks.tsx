import { useEffect, useMemo, useState } from 'react'
import { MapPin, Pencil, Plus } from 'lucide-react'

import type { RelationshipsClient } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { browserNetworksClient } from './api'
import type { NetworkChoices, NetworkRecord, NetworkRecordWrite, NetworksClient } from './api'

type Props = {
  workspace: WorkspaceContext
  client?: NetworksClient
  relationshipsClient: RelationshipsClient
}

const emptyForm: NetworkRecordWrite = {
  name: '',
  location_id: null,
  description: '',
  vlan: null,
  cidr: '',
  use_full_range: true,
  range_start: null,
  range_end: null,
  primary_dns: null,
  secondary_dns: null,
  notes: '',
}

export function Networks({ workspace, client = browserNetworksClient, relationshipsClient }: Props) {
  void relationshipsClient
  const [records, setRecords] = useState<NetworkRecord[] | null>(null)
  const [choices, setChoices] = useState<NetworkChoices | null>(null)
  const [canManage, setCanManage] = useState(false)
  const [query, setQuery] = useState('')
  const [form, setForm] = useState<NetworkRecordWrite | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.listNetworks(workspace, controller.signal), client.choices(workspace, controller.signal)])
      .then(([result, nextChoices]) => {
        setRecords(result.results)
        setCanManage(result.can_manage)
        setChoices(nextChoices)
        setError('')
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Networks could not be loaded.')
      })
    return () => controller.abort()
  }, [client, workspace])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return records ?? []
    return (records ?? []).filter((record) => [
      record.name,
      record.description,
      record.location_name,
      record.site_name,
      record.cidr,
      record.vlan?.toString(),
      record.primary_dns,
      record.secondary_dns,
    ].some((value) => value?.toLowerCase().includes(normalized)))
  }, [query, records])

  function beginEdit(record: NetworkRecord) {
    setEditingId(record.id)
    setError('')
    setForm({
      name: record.name,
      location_id: record.location_id,
      description: record.description,
      vlan: record.vlan,
      cidr: record.cidr,
      use_full_range: record.use_full_range,
      range_start: record.use_full_range ? null : record.range_start,
      range_end: record.use_full_range ? null : record.range_end,
      primary_dns: record.primary_dns,
      secondary_dns: record.secondary_dns,
      notes: record.notes,
    })
  }

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!form) return
    setBusy(true)
    setError('')
    try {
      const values = form.use_full_range ? { ...form, range_start: null, range_end: null } : form
      const saved = editingId
        ? await client.updateNetwork(workspace, editingId, values)
        : await client.createNetwork(workspace, values)
      setRecords((current) => editingId
        ? (current ?? []).map((record) => record.id === saved.id ? saved : record)
        : [...(current ?? []), saved])
      setForm(null)
      setEditingId(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The network could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return <>
    <header className="page-header">
      <div>
        <h1>Networks</h1>
        <p>Address ranges and essential network settings for {workspace.name}.</p>
      </div>
      {canManage && <button className="primary-button" type="button" onClick={() => { setEditingId(null); setForm({ ...emptyForm }); setError('') }}>
        <Plus size={16} aria-hidden="true" />New network
      </button>}
    </header>

    <section className="content-section network-records" aria-labelledby="network-list-heading">
      <div className="network-record-toolbar">
        <div>
          <h2 id="network-list-heading">Network records</h2>
          <p>One record describes the location, VLAN, address space, gateway, range, and DNS.</p>
        </div>
        <label className="network-search">
          <span className="sr-only">Search networks</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search networks" />
        </label>
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}
      {records === null && !error && <p role="status">Loading networks…</p>}
      {records !== null && filtered.length === 0 && <p className="empty-state">{query ? 'No networks match this search.' : 'No networks have been added to this workspace.'}</p>}
      {records !== null && filtered.length > 0 && <div className="network-table-wrap">
        <table className="network-table">
          <thead><tr><th>Name</th><th>Location</th><th>VLAN</th><th>CIDR</th><th>Assignable range</th><th>Gateway</th><th>DNS</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{filtered.map((record) => <tr key={record.id}>
            <td><strong>{record.name}</strong>{record.description && <small>{record.description}</small>}</td>
            <td>{record.location_name ? <span className="network-location"><MapPin size={14} aria-hidden="true" />{record.site_name ? `${record.site_name} · ` : ''}{record.location_name}</span> : 'Not assigned'}</td>
            <td>{record.vlan ?? '—'}</td>
            <td><code>{record.cidr}</code></td>
            <td><code>{record.range_start}–{record.range_end}</code></td>
            <td><code>{record.gateway}</code></td>
            <td>{[record.primary_dns, record.secondary_dns].filter(Boolean).join(', ') || '—'}</td>
            <td>{canManage && <button className="row-action" type="button" onClick={() => beginEdit(record)}><Pencil size={14} aria-hidden="true" />Edit</button>}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </section>

    {form && <section className="content-section network-editor" aria-labelledby="network-editor-heading">
      <div className="section-heading"><div><h2 id="network-editor-heading">{editingId ? 'Edit network' : 'New network'}</h2><p>The gateway and usable full range are calculated from the CIDR.</p></div></div>
      <form className="network-form" onSubmit={(event) => void save(event)}>
        <div className="field-grid">
          <label><span>Name</span><input required maxLength={240} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Office LAN" /></label>
          <label><span>Location</span><select value={form.location_id ?? ''} onChange={(event) => setForm({ ...form, location_id: event.target.value || null })}><option value="">Not assigned</option>{choices?.locations.map((location) => {
            const site = choices.sites.find((item) => item.id === location.site_id)
            return <option key={location.id} value={location.id}>{site ? `${site.name} · ` : ''}{location.name}</option>
          })}</select></label>
          <label><span>VLAN</span><input type="number" min="1" max="4094" value={form.vlan ?? ''} onChange={(event) => setForm({ ...form, vlan: event.target.value ? Number(event.target.value) : null })} placeholder="20" /></label>
          <label><span>Network (CIDR)</span><input required value={form.cidr} onChange={(event) => setForm({ ...form, cidr: event.target.value })} placeholder="192.168.1.0/24" /><small>Gateway is calculated as the first usable address.</small></label>
          <label><span>Primary DNS</span><input value={form.primary_dns ?? ''} onChange={(event) => setForm({ ...form, primary_dns: event.target.value || null })} placeholder="9.9.9.9" /></label>
          <label><span>Secondary DNS</span><input value={form.secondary_dns ?? ''} onChange={(event) => setForm({ ...form, secondary_dns: event.target.value || null })} placeholder="1.1.1.1" /></label>
        </div>
        <label className="network-range-toggle"><input type="checkbox" checked={form.use_full_range} onChange={(event) => setForm({ ...form, use_full_range: event.target.checked })} /><span>Use the full usable address range</span></label>
        {!form.use_full_range && <div className="field-grid network-range-fields">
          <label><span>Assignable range start</span><input required value={form.range_start ?? ''} onChange={(event) => setForm({ ...form, range_start: event.target.value || null })} placeholder="192.168.1.100" /></label>
          <label><span>Assignable range end</span><input required value={form.range_end ?? ''} onChange={(event) => setForm({ ...form, range_end: event.target.value || null })} placeholder="192.168.1.200" /></label>
        </div>}
        <label><span>Description</span><input maxLength={4000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Guest Wi-Fi, voice, office LAN…" /></label>
        <label><span>Notes</span><textarea rows={5} maxLength={8000} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></label>
        <div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save network'}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => { setForm(null); setEditingId(null); setError('') }}>Cancel</button></div>
      </form>
    </section>}
  </>
}
