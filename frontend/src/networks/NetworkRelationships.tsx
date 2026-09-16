import { useEffect, useMemo, useState } from 'react'
import { Link2, Trash2 } from 'lucide-react'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { RelationshipsClient, EntityLinkType, EntityReference, EntityRelationship } from '../relationships/api'
import type { WorkspaceContext } from '../workspaces/api'
import { networkText as t } from './networkText'

const relationshipTypes: Array<{ value: EntityLinkType; label: string }> = [
  { value: 'connected_to', label: t('deviceRelationshipConnected') },
  { value: 'depends_on', label: t('deviceRelationshipDepends') },
  { value: 'related_to', label: t('deviceRelationshipRelated') },
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
  const attempt = useUnsavedChanges(adding && Boolean(query || targetId || linkType !== 'connected_to'), busy, () => { setAdding(false); setQuery(''); setTargetId(''); setLinkType('connected_to') }, adding || busy)

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, deviceId, controller.signal).then(setItems).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : t('deviceRelationshipsFailed'))
    })
    return () => controller.abort()
  }, [client, deviceId, scope])

  useEffect(() => {
    if (!adding) return
    const controller = new AbortController()
    client.search(scope, query, 'network_device', controller.signal).then((result) => {
      setCandidates(result.results.filter((item) => item.id !== deviceId && item.eligible_link_types.includes(linkType)))
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : t('deviceRelationshipSearchFailed'))
    })
    return () => controller.abort()
  }, [adding, client, deviceId, linkType, query, scope])

  async function create() {
    if (!targetId) return
    setBusy(true); setError(null)
    try {
      const created = await client.create(scope, deviceId, targetId, linkType)
      setItems((current) => [...(current ?? []), created]); setAdding(false); setTargetId(''); setQuery('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('deviceRelationshipAddFailed')) }
    finally { setBusy(false) }
  }

  async function archive(item: EntityRelationship) {
    setBusy(true); setError(null)
    try {
      await client.archive(scope, deviceId, item.id)
      setItems((current) => (current ?? []).filter((candidate) => candidate.id !== item.id))
    } catch (caught) { setError(caught instanceof Error ? caught.message : t('deviceRelationshipArchiveFailed')) }
    finally { setBusy(false) }
  }

  return <section className="network-relationships" aria-labelledby="network-relationships-heading">
    <div className="section-heading"><div><h3 id="network-relationships-heading">{t('deviceRelationshipsHeading')}</h3><p>{t('deviceRelationshipsHelp', { name: deviceName })}</p></div>{canCreate && <button className="secondary-button" type="button" onClick={() => attempt(() => setAdding((value) => !value))}>{t(adding ? 'deviceRelationshipCancel' : 'deviceRelationshipAdd')}</button>}</div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {adding && <div className="network-relationship-form">
      <label><span>{t('deviceRelationshipType')}</span><select value={linkType} onChange={(event) => { setLinkType(event.target.value as EntityLinkType); setTargetId('') }}>{relationshipTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label><span>{t('deviceRelationshipSearch')}</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setTargetId('') }} /></label>
      <label><span>{t('deviceRelationshipTarget')}</span><select value={targetId} onChange={(event) => setTargetId(event.target.value)}><option value="">{t('deviceRelationshipChoose')}</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
      <button className="primary-button" type="button" disabled={busy || !targetId} onClick={() => void create()}>{t(busy ? 'deviceRelationshipAdding' : 'deviceRelationshipAdd')}</button>
    </div>}
    {items === null && !error && <p role="status">{t('deviceRelationshipsLoading')}</p>}
    {items?.length === 0 && <p>{t('deviceRelationshipsEmpty')}</p>}
    {items && items.length > 0 && <ul className="network-relationship-list">{items.map((item) => <li key={item.id}><Link2 size={15} aria-hidden="true" /><span><strong>{item.label}</strong> {item.related_entity.display_name}</span><span>{t(item.direction === 'incoming' ? 'deviceRelationshipBacklink' : 'deviceRelationshipOutgoing')}</span>{canArchive && <button className="icon-button" type="button" disabled={busy} aria-label={t('deviceRelationshipArchive', { name: item.related_entity.display_name })} onClick={() => void archive(item)}><Trash2 size={14} /></button>}</li>)}</ul>}
  </section>
}
