import { useEffect, useMemo, useState } from 'react'
import { Link2, Search, Trash2 } from 'lucide-react'
import type { WorkspaceContext } from '../workspaces/api'
import { browserRelationshipsClient } from '../relationships/api'
import type { EntityLinkType, EntityReference, EntityRelationship, RelationshipsClient } from '../relationships/api'

const assetLinkTypes: Array<{ value: EntityLinkType; label: string }> = [
  { value: 'related_to', label: 'Related to' },
  { value: 'depends_on', label: 'Depends on' },
  { value: 'references', label: 'References' },
]

export function AssetRelationships({
  workspace,
  assetId,
  assetName,
  canCreate,
  canArchive,
  client = browserRelationshipsClient,
}: {
  workspace: WorkspaceContext
  assetId: string
  assetName: string
  canCreate: boolean
  canArchive: boolean
  client?: RelationshipsClient
}) {
  const scope = useMemo(
    () => workspace.kind === 'organization' ? { organizationId: workspace.id } : {},
    [workspace],
  )
  const [relationships, setRelationships] = useState<EntityRelationship[] | null>(null)
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState('')
  const [linkType, setLinkType] = useState<EntityLinkType>('related_to')
  const [candidates, setCandidates] = useState<EntityReference[] | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, assetId, controller.signal)
      .then(setRelationships)
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Asset relationships could not be loaded.') })
    return () => controller.abort()
  }, [assetId, client, scope])

  useEffect(() => {
    if (!adding) return
    const controller = new AbortController()
    client.search(scope, query, 'client_asset', controller.signal)
      .then((result) => setCandidates(result.results.filter((item) => item.id !== assetId)))
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Related assets could not be loaded.') })
    return () => controller.abort()
  }, [adding, assetId, client, query, scope])

  async function addRelationship() {
    if (!selectedId) return
    setSaving(true); setError(null)
    try {
      const created = await client.create(scope, assetId, selectedId, linkType)
      setRelationships((current) => [...(current ?? []), created])
      setAdding(false); setSelectedId(''); setQuery('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The relationship could not be added.') }
    finally { setSaving(false) }
  }

  async function archiveRelationship(item: EntityRelationship) {
    setSaving(true); setError(null)
    try {
      await client.archive(scope, assetId, item.id)
      setRelationships((current) => (current ?? []).filter((relationship) => relationship.id !== item.id))
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The relationship could not be archived.') }
    finally { setSaving(false) }
  }

  return <section className="asset-relationships" aria-labelledby="asset-relationships-heading">
    <div className="section-heading"><div><h3 id="asset-relationships-heading">Asset relationships</h3><p>Typed links and backlinks for {assetName} within this workspace.</p></div>{canCreate && <button className="secondary-button" type="button" onClick={() => { setAdding((current) => !current); setCandidates(null) }}>{adding ? 'Cancel' : 'Add relationship'}</button>}</div>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {adding && <div className="asset-relationship-form">
      <label><span>Relationship</span><select value={linkType} onChange={(event) => setLinkType(event.target.value as EntityLinkType)}>{assetLinkTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label><span>Find an asset</span><span className="relationship-search-control"><Search size={16} aria-hidden="true" /><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setSelectedId('') }} /></span></label>
      <label><span>Related asset</span><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option value="">Choose an asset…</option>{candidates?.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
      <button className="primary-button" type="button" disabled={saving || !selectedId} onClick={() => { void addRelationship() }}>{saving ? 'Adding…' : 'Add relationship'}</button>
    </div>}
    {relationships === null && !error && <p className="relationship-state" role="status">Loading asset relationships…</p>}
    {relationships?.length === 0 && <p className="relationship-state">No asset relationships have been added.</p>}
    {relationships && relationships.length > 0 && <ul className="asset-relationship-list">{relationships.map((item) => <li key={item.id}><Link2 size={15} aria-hidden="true" /><span><strong>{item.label}</strong> {item.related_entity.display_name}</span><span>{item.direction === 'incoming' ? 'Backlink' : 'Outgoing'}</span>{canArchive && <button className="icon-button" type="button" aria-label={`Archive relationship with ${item.related_entity.display_name}`} disabled={saving} onClick={() => { void archiveRelationship(item) }}><Trash2 size={14} /></button>}</li>)}</ul>}
  </section>
}
