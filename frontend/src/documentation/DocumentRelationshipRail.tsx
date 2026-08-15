import { useEffect, useMemo, useState } from 'react'
import { Link2, Search, Trash2 } from 'lucide-react'
import type { EntityReference, EntityRelationship, RelationshipScope, RelationshipsClient } from '../relationships/api'

function message(error: unknown) {
  return error instanceof Error ? error.message : 'Document relationships are unavailable.'
}

export function DocumentRelationshipRail({ scope, documentId, client }: {
  scope: RelationshipScope
  documentId: string
  client: RelationshipsClient
}) {
  const stableScope = useMemo(() => scope.organizationId ? { organizationId: scope.organizationId } : {}, [scope.organizationId])
  const [relationships, setRelationships] = useState<EntityRelationship[] | null>(null)
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<EntityReference[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(stableScope, documentId, controller.signal)
      .then((records) => { if (!controller.signal.aborted) setRelationships(records) })
      .catch((loadError) => { if (!controller.signal.aborted) setError(message(loadError)) })
    return () => controller.abort()
  }, [client, documentId, stableScope])

  useEffect(() => {
    if (!query.trim()) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.search(stableScope, query, undefined, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setCandidates(result.results.filter((item) => item.id !== documentId && item.eligible_link_types.includes('references'))) })
        .catch((searchError) => { if (!controller.signal.aborted) setError(message(searchError)) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, documentId, query, stableScope])

  const add = async (target: EntityReference) => {
    setSaving(true); setError(null)
    try {
      const created = await client.create(stableScope, documentId, target.id, 'references')
      setRelationships((current) => [...(current ?? []), created])
      setQuery(''); setCandidates([])
    } catch (saveError) { setError(message(saveError)) } finally { setSaving(false) }
  }

  const archive = async (relationship: EntityRelationship) => {
    setSaving(true); setError(null)
    try {
      await client.archive(stableScope, documentId, relationship.id)
      setRelationships((current) => (current ?? []).filter((item) => item.id !== relationship.id))
    } catch (saveError) { setError(message(saveError)) } finally { setSaving(false) }
  }

  return <aside className="document-relationship-rail" aria-labelledby="document-relationships-heading">
    <div><h2 id="document-relationships-heading">Related records</h2><p>Assets, people, sites, networks, services, vendors, and other addressable records.</p></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <label><span>Find a record</span><span className="relationship-search-control"><Search size={15} /><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); if (!event.target.value.trim()) setCandidates([]) }} placeholder="Search this workspace" /></span></label>
    {candidates.length > 0 && <ul className="document-relationship-candidates">{candidates.map((candidate) => <li key={candidate.id}><button type="button" disabled={saving} onClick={() => { void add(candidate) }}><strong>{candidate.display_name}</strong><small>{candidate.entity_type.replaceAll('_', ' ')} · {candidate.workspace_label}</small></button></li>)}</ul>}
    {relationships === null && !error && <p role="status">Loading related records…</p>}
    {relationships?.length === 0 && <p>No related records.</p>}
    {relationships && relationships.length > 0 && <ul className="document-relationship-list">{relationships.map((relationship) => <li key={relationship.id}><Link2 size={15} /><span><strong>{relationship.related_entity.display_name}</strong><small>{relationship.label} · {relationship.related_entity.entity_type.replaceAll('_', ' ')}</small></span><button className="icon-button" type="button" disabled={saving} aria-label={`Remove relationship with ${relationship.related_entity.display_name}`} onClick={() => { void archive(relationship) }}><Trash2 size={14} /></button></li>)}</ul>}
  </aside>
}
