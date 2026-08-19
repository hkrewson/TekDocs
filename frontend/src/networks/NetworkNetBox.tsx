import { useEffect, useMemo, useState } from 'react'
import { translate } from '../i18n/localization'
import type { FormEvent } from 'react'
import type { WorkspaceContext } from '../workspaces/api'
import type { NetBoxChoice, NetBoxReference, NetworksClient } from './api'

const typeLabel: Record<string, string> = {
  'dcim.rack': 'Rack',
  'dcim.device': 'Hardware asset / device',
  'dcim.macaddress': 'MAC address',
  'ipam.vlan': 'VLAN',
  'ipam.prefix': 'Prefix',
  'ipam.ipaddress': 'IP address',
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'The NetBox reference request failed.'
}

export function NetworkNetBox({ workspace, client, query }: { workspace: WorkspaceContext; client: NetworksClient; query: string }) {
  const [references, setReferences] = useState<NetBoxReference[] | null>(null)
  const [choices, setChoices] = useState<NetBoxChoice[]>([])
  const [canManage, setCanManage] = useState(false)
  const [selectedId, setSelectedId] = useState('')
  const [objectId, setObjectId] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load(signal?: AbortSignal) {
    const [loadedReferences, loadedChoices] = await Promise.all([
      client.listNetBoxReferences(workspace, signal),
      client.netBoxChoices(workspace, signal),
    ])
    setReferences(loadedReferences)
    setChoices(loadedChoices.results)
    setCanManage(loadedChoices.can_manage)
  }

  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => { if (!controller.signal.aborted) { setReferences(null); setError(null); setFormOpen(false) } })
    Promise.all([
      client.listNetBoxReferences(workspace, controller.signal),
      client.netBoxChoices(workspace, controller.signal),
    ]).then(([loadedReferences, loadedChoices]) => {
      setReferences(loadedReferences); setChoices(loadedChoices.results); setCanManage(loadedChoices.can_manage)
    }).catch((caught: unknown) => { if (!controller.signal.aborted) setError(errorMessage(caught)) })
    return () => controller.abort()
  }, [client, workspace])

  const selected = choices.find((item) => item.id === selectedId)
  const availableChoices = choices.filter((item) => !item.linked)
  const filtered = useMemo(() => (references ?? []).filter((item) => `${item.entity_name} ${item.entity_type} ${item.object_type} ${item.object_id}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())), [query, references])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    setBusy(true); setError(null)
    try {
      await client.setNetBoxReference(workspace, {
        entity_id: selected.id,
        object_type: selected.object_type,
        object_id: Number(objectId),
      })
      await load()
      setSelectedId(''); setObjectId(''); setFormOpen(false)
    } catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }

  async function unlink(reference: NetBoxReference) {
    if (!window.confirm(`Remove the NetBox identity from ${reference.entity_name}? This does not change NetBox.`)) return
    setBusy(true); setError(null)
    try { await client.removeNetBoxReference(workspace, reference.id); await load() }
    catch (caught) { setError(errorMessage(caught)) } finally { setBusy(false) }
  }

  return <div className="network-netbox">
    <div className="section-heading"><div><h2>NetBox identities</h2><p>Stable object mappings for later read-only reconciliation. TekDocs stores no NetBox URL or API token in this slice.</p></div>{canManage && !formOpen && <button className="primary-button" type="button" onClick={() => setFormOpen(true)}>{translate('networks.linkRecord')}</button>}</div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {formOpen && <form className="network-form" onSubmit={(event) => void submit(event)}><h2>Link a NetBox object</h2><div className="field-grid"><label><span>TekDocs record</span><select required value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option value="">Choose an unlinked record…</option>{availableChoices.map((item) => <option key={item.id} value={item.id}>{item.name} · {typeLabel[item.object_type]}</option>)}</select></label><label><span>NetBox object type</span><input readOnly value={selected ? typeLabel[selected.object_type] : 'Select a TekDocs record'} /></label><label><span>NetBox numeric ID</span><input required type="number" min="1" step="1" value={objectId} onChange={(event) => setObjectId(event.target.value)} /></label></div><p className="field-help">Use the numeric ID from the NetBox REST object. A later connector will observe changes and produce a reviewable preview before modifying TekDocs.</p><div className="form-actions"><button className="primary-button" disabled={busy}>{busy ? 'Linking…' : 'Link identity'}</button><button className="secondary-button" type="button" onClick={() => setFormOpen(false)}>{translate('common.cancel')}</button></div></form>}
    {references === null ? <p role="status">Loading NetBox identities…</p> : <div className="network-table-wrap" role="group" aria-label={translate('networks.netboxTable')} tabIndex={0}><table className="network-table"><caption className="sr-only">NetBox object identities for this workspace</caption><thead><tr><th>TekDocs record</th><th>NetBox type</th><th>NetBox ID</th><th>Observation</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><strong>{item.entity_name}</strong></td><td>{typeLabel[item.object_type]}</td><td>{item.object_id}</td><td>{item.last_observed_at ? 'Fingerprint retained' : 'Not observed by a connector'}</td><td>{canManage && <button className="row-action" type="button" disabled={busy} onClick={() => void unlink(item)}>{translate('networks.unlink')}</button>}</td></tr>)}</tbody></table>{filtered.length === 0 && <p className="empty-state">No NetBox identities match this workspace and search.</p>}</div>}
  </div>
}
