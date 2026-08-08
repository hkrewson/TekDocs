import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link2, Search, Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { browserRelationshipsClient } from './api'
import type { EntityLinkType, EntityReference, EntityRelationship, LinkTypeDefinition, RelationshipsClient } from './api'

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

const organizationRelationshipTypes: EntityLinkType[] = [
  'related_to',
  'managed_by',
  'supplied_by',
  'manufactured_by',
  'partnered_with',
  'depends_on',
  'references',
]

export function EntityRelationships({ organizationId, organizationName, client = browserRelationshipsClient }: {
  organizationId: string
  organizationName: string
  client?: RelationshipsClient
}) {
  const scope = useMemo(() => ({ organizationId }), [organizationId])
  const [relationshipResult, setRelationshipResult] = useState<{ organizationId: string; items: EntityRelationship[] } | null>(null)
  const [types, setTypes] = useState<LinkTypeDefinition[]>([])
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState('')
  const [linkType, setLinkType] = useState<EntityLinkType>('related_to')
  const [candidateResult, setCandidateResult] = useState<{ key: string; items: EntityReference[] } | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [archivingId, setArchivingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const candidateKey = `${organizationId}:${linkType}:${query}`
  const relationships = relationshipResult?.organizationId === organizationId ? relationshipResult.items : null
  const candidates = candidateResult?.key === candidateKey ? candidateResult.items : null

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      client.list(scope, organizationId, controller.signal),
      client.linkTypes(controller.signal),
    ])
      .then(([loadedRelationships, loadedTypes]) => {
        if (controller.signal.aborted) return
        setRelationshipResult({ organizationId, items: loadedRelationships })
        setTypes(loadedTypes.filter((item) => organizationRelationshipTypes.includes(item.value)))
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(loadError, 'Relationships could not be loaded.'))
      })
    return () => controller.abort()
  }, [client, organizationId, scope])

  useEffect(() => {
    if (!adding) return
    const controller = new AbortController()
    client.search(scope, query, 'organization', controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setCandidateResult({ key: candidateKey, items: result.results.filter((candidate) => (
          candidate.id !== organizationId && candidate.eligible_link_types.includes(linkType)
        )) })
      })
      .catch((searchError: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(searchError, 'Relationship targets could not be loaded.'))
      })
    return () => controller.abort()
  }, [adding, candidateKey, client, linkType, organizationId, query, scope])

  const selectedType = types.find((item) => item.value === linkType)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedId) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const created = await client.create(scope, organizationId, selectedId, linkType)
      setRelationshipResult((current) => ({ organizationId, items: [...(current?.organizationId === organizationId ? current.items : []), created] }))
      setAdding(false)
      setQuery('')
      setSelectedId('')
      setMessage('Relationship added.')
    } catch (saveError) {
      setError(errorMessage(saveError, 'The relationship could not be added.'))
    } finally {
      setSaving(false)
    }
  }

  const archive = async (relationship: EntityRelationship) => {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await client.archive(scope, organizationId, relationship.id)
      setRelationshipResult((current) => ({ organizationId, items: current?.organizationId === organizationId ? current.items.filter((item) => item.id !== relationship.id) : [] }))
      setArchivingId(null)
      setMessage('Relationship archived.')
    } catch (archiveError) {
      setError(errorMessage(archiveError, 'The relationship could not be archived.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="content-section relationship-section" aria-labelledby="organization-relationships-heading">
      <div className="section-heading relationship-heading">
        <div><h2 id="organization-relationships-heading">Organization relationships</h2><p>Typed links and reverse references involving {organizationName}.</p></div>
        <button className="secondary-button" type="button" onClick={() => { setAdding((current) => !current); setSelectedId(''); setMessage(null) }}>{adding ? 'Cancel' : 'Add relationship'}</button>
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      {message && <div className="form-success" role="status">{message}</div>}
      {adding && (
        <form className="relationship-form" onSubmit={(event) => { void submit(event) }}>
          <label>Relationship type<select value={linkType} onChange={(event) => { setLinkType(event.target.value as EntityLinkType); setSelectedId('') }}>
            {types.map((item) => <option key={item.value} value={item.value}>{item.forward_label}</option>)}
          </select></label>
          <label className="relationship-search"><span>Related organization</span><span className="relationship-search-control"><Search size={16} aria-hidden="true" /><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setSelectedId('') }} placeholder="Search organizations" /></span></label>
          <fieldset className="relationship-candidates">
            <legend>Select an organization</legend>
            {candidates === null && <p role="status">Loading eligible organizations…</p>}
            {candidates !== null && candidates.length === 0 && <p>No eligible organizations match this search.</p>}
            {candidates?.map((candidate) => (
              <label key={candidate.id}><input type="radio" name="relationship-target" value={candidate.id} checked={selectedId === candidate.id} onChange={() => setSelectedId(candidate.id)} /><span><strong>{candidate.display_name}</strong><span>{candidate.workspace_label}</span></span></label>
            ))}
          </fieldset>
          <div className="form-actions"><button className="primary-button" type="submit" disabled={saving || !selectedId}>{saving ? 'Adding…' : `Add ${selectedType?.forward_label.toLowerCase() ?? 'relationship'}`}</button></div>
        </form>
      )}
      {relationships === null && !error && <p className="relationship-state" role="status">Loading relationships…</p>}
      {relationships !== null && relationships.length === 0 && <p className="relationship-state">No relationships have been added.</p>}
      {relationships && relationships.length > 0 && (
        <ul className="relationship-list">
          {relationships.map((relationship) => (
            <li key={relationship.id}>
              <Link2 size={16} aria-hidden="true" />
              <span className="relationship-label">{relationship.label}</span>
              {relationship.related_entity.entity_type === 'organization'
                ? <Link to={`/workspaces/organizations/${relationship.related_entity.id}/overview`}>{relationship.related_entity.display_name}</Link>
                : <span>{relationship.related_entity.display_name}</span>}
              <span className="relationship-scope">{relationship.direction === 'incoming' ? 'Backlink' : 'Outgoing'}</span>
              {archivingId === relationship.id
                ? <span className="relationship-confirm"><button className="row-action danger" type="button" disabled={saving} onClick={() => { void archive(relationship) }}>Confirm archive</button><button className="row-action" type="button" disabled={saving} onClick={() => setArchivingId(null)}>Cancel</button></span>
                : <button className="row-action danger relationship-archive" type="button" aria-label={`Archive relationship with ${relationship.related_entity.display_name}`} onClick={() => setArchivingId(relationship.id)}><Trash2 size={14} aria-hidden="true" />Archive</button>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
