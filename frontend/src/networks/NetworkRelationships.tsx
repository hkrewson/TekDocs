import { useEffect, useMemo, useState } from 'react'
import { Link2, Trash2 } from 'lucide-react'
import type { RelationshipsClient, EntityLinkType, EntityReference, EntityRelationship } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'

const relationshipTypes: Array<{ value: EntityLinkType; label: string }> = [
  { value: 'connected_to', label: 'Connected to' },
  { value: 'depends_on', label: 'Depends on' },
  { value: 'related_to', label: 'Related to' },
]

export function NetworkRelationships({ workspace, deviceId, deviceName, canCreate, canArchive, client }: {
  workspace: WorkspaceContext
  deviceId: string
  deviceName: string
  canCreate: boolean
  canArchive: boolean
  client: RelationshipsClient
}) {
  const scope = useMemo(() => workspace.kind === 'organization' ? { organizationId: workspace.id } : {}, [workspace])
  const [items, setItems] = useState<EntityRelationship[] | null>(null)
  const [candidates, setCandidates] = useState<EntityReference[]>([])
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState('')
  const [targetId, setTargetId] = useState('')
  const [linkType, setLinkType] = useState<EntityLinkType>('connected_to')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, deviceId, controller.signal).then(setItems).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Logical relationships could not be loaded.')
    })
    return () => controller.abort()
  }, [client, deviceId, scope])

  useEffect(() => {
    if (!adding) return
    const controller = new AbortController()
    client.search(scope, query, 'network_device', controller.signal).then((result) => {
      setCandidates(result.results.filter((item) => item.id !== deviceId && item.eligible_link_types.includes(linkType)))
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Network devices could not be searched.')
    })
    return () => controller.abort()
  }, [adding, client, deviceId, linkType, query, scope])

  async function create() {
    if (!targetId) return
    setBusy(true); setError(null)
    try {
      const created = await client.create(scope, deviceId, targetId, linkType)
      setItems((current) => [...(current ?? []), created]); setAdding(false); setTargetId(''); setQuery('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The relationship could not be added.') }
    finally { setBusy(false) }
  }

  async function archive(item: EntityRelationship) {
    setBusy(true); setError(null)
    try {
      await client.archive(scope, deviceId, item.id)
      setItems((current) => (current ?? []).filter((candidate) => candidate.id !== item.id))
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The relationship could not be archived.') }
    finally { setBusy(false) }
  }

  return <section className="network-relationships" aria-labelledby="network-relationships-heading">
    <div className="section-heading"><div><h3 id="network-relationships-heading">Logical relationships</h3><p>Typed links and backlinks for {deviceName}.</p></div>{canCreate && <button className="secondary-button" type="button" onClick={() => setAdding((value) => !value)}>{adding ? 'Cancel' : 'Add relationship'}</button>}</div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {adding && <div className="network-relationship-form">
      <label><span>Relationship</span><select value={linkType} onChange={(event) => { setLinkType(event.target.value as EntityLinkType); setTargetId('') }}>{relationshipTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label><span>Find a network device</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setTargetId('') }} /></label>
      <label><span>Related device</span><select value={targetId} onChange={(event) => setTargetId(event.target.value)}><option value="">Choose a device…</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
      <button className="primary-button" type="button" disabled={busy || !targetId} onClick={() => void create()}>{busy ? 'Adding…' : 'Add relationship'}</button>
    </div>}
    {items === null && !error && <p role="status">Loading logical relationships…</p>}
    {items?.length === 0 && <p>No logical relationships have been added.</p>}
    {items && items.length > 0 && <ul className="network-relationship-list">{items.map((item) => <li key={item.id}><Link2 size={15} aria-hidden="true" /><span><strong>{item.label}</strong> {item.related_entity.display_name}</span><span>{item.direction === 'incoming' ? 'Backlink' : 'Outgoing'}</span>{canArchive && <button className="icon-button" type="button" disabled={busy} aria-label={`Archive relationship with ${item.related_entity.display_name}`} onClick={() => void archive(item)}><Trash2 size={14} /></button>}</li>)}</ul>}
  </section>
}
