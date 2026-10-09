import { useEffect, useRef, useState } from 'react'
import { formatDateTime, translate } from '../i18n/localization'
import { type RepositoryClient, type RepositoryEvidence, type RepositoryStaticPublication } from './repositoryApi'

export function RepositoryPublicationHistory({ contentId, organizationId, client }: {
  contentId: string
  organizationId?: string
  client: RepositoryClient
}) {
  const [records, setRecords] = useState<RepositoryEvidence[]>([])
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [failedPage, setFailedPage] = useState(1)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [selected, setSelected] = useState<RepositoryEvidence | null>(null)
  const [staticRecord, setStaticRecord] = useState<RepositoryStaticPublication | null>(null)
  const [staticPhase, setStaticPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const listRequest = useRef<AbortController | null>(null)
  const staticRequest = useRef<AbortController | null>(null)

  useEffect(() => () => {
    listRequest.current?.abort()
    staticRequest.current?.abort()
  }, [])

  async function load(nextPage: number) {
    if (phase === 'loading') return
    listRequest.current?.abort()
    const controller = new AbortController()
    listRequest.current = controller
    setPhase('loading')
    try {
      const result = await client.listEvidence(contentId, organizationId, nextPage, controller.signal)
      if (controller.signal.aborted) return
      setRecords((current) => nextPage === 1 ? result.results : [...current, ...result.results])
      setPage(result.page)
      setHasMore(result.has_more)
      setPhase('ready')
    } catch {
      if (!controller.signal.aborted) { setFailedPage(nextPage); setPhase('error') }
    }
  }

  async function inspect(record: RepositoryEvidence) {
    staticRequest.current?.abort()
    const controller = new AbortController()
    staticRequest.current = controller
    setSelected(record)
    setStaticRecord(null)
    setStaticPhase('loading')
    try {
      const result = await client.staticPublication(record.id, organizationId, controller.signal)
      if (controller.signal.aborted) return
      setStaticRecord(result)
      setStaticPhase('ready')
    } catch {
      if (!controller.signal.aborted) setStaticPhase('error')
    }
  }

  return <section className="repository-publication-history" aria-label={translate('repository.publicationHistory')}>
    <h2>{translate('repository.publicationHistory')}</h2>
    <p>{translate('repository.publicationHistoryNotice')}</p>
    {phase === 'idle' && <button type="button" className="secondary-button" onClick={() => { void load(1) }}>{translate('repository.loadPublicationHistory')}</button>}
    {phase === 'loading' && <p role="status">{translate('repository.publicationHistoryLoading')}</p>}
    {phase === 'error' && <p role="alert" className="form-message error">{translate('repository.publicationHistoryFailed')} <button type="button" className="secondary-button" onClick={() => { void load(failedPage) }}>{translate('common.retry')}</button></p>}
    {phase === 'ready' && records.length === 0 && <p className="empty-state">{translate('repository.publicationHistoryEmpty')}</p>}
    {records.length > 0 && <ul className="document-title-list">{records.map((record) => <li key={record.id}><button type="button" aria-current={selected?.id === record.id ? 'true' : undefined} onClick={() => { void inspect(record) }}><span><strong>{record.title}</strong><small>{translate('repository.publicationEvidenceSummary', { audience: translate(record.audience === 'client_visible' ? 'repository.audienceClient' : 'repository.audienceInternal'), commit: record.source_commit.slice(0, 12) })} · <time dateTime={record.signed_at}>{formatDateTime(record.signed_at)}</time></small></span></button></li>)}</ul>}
    {phase === 'ready' && hasMore && <button type="button" className="secondary-button" onClick={() => { void load(page + 1) }}>{translate('repository.publicationHistoryMore')}</button>}
    {selected && <div className="repository-publication-detail">
      <h3>{translate('repository.publicationEvidenceSelected')}</h3>
      {staticPhase === 'loading' && <p role="status">{translate('repository.staticChecking')}</p>}
      {staticPhase === 'error' && <p role="alert" className="form-message error">{translate('repository.staticCheckFailed')} <button type="button" className="secondary-button" onClick={() => { void inspect(selected) }}>{translate('common.retry')}</button></p>}
      {staticPhase === 'ready' && !staticRecord && <p>{translate('repository.staticNotFinalized')}</p>}
      {staticPhase === 'ready' && staticRecord && <p role="status">{translate(staticRecord.verified ? 'repository.staticVerified' : 'repository.staticUnverified')}</p>}
    </div>}
  </section>
}
