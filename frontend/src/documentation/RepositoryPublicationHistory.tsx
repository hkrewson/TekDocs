import { useEffect, useRef, useState } from 'react'
import { formatDateTime, translate } from '../i18n/localization'
import { type RepositoryClient, type RepositoryEvidence, type RepositoryStaticFormat, type RepositoryStaticPublication } from './repositoryApi'

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
  const [exporting, setExporting] = useState<RepositoryStaticFormat | null>(null)
  const [downloadError, setDownloadError] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [reviewError, setReviewError] = useState(false)
  const listRequest = useRef<AbortController | null>(null)
  const staticRequest = useRef<AbortController | null>(null)
  const exportRequest = useRef<AbortController | null>(null)
  const reviewRequest = useRef<AbortController | null>(null)

  useEffect(() => () => {
    listRequest.current?.abort()
    staticRequest.current?.abort()
    exportRequest.current?.abort()
    reviewRequest.current?.abort()
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
    exportRequest.current?.abort()
    reviewRequest.current?.abort()
    const controller = new AbortController()
    staticRequest.current = controller
    setSelected(record)
    setStaticRecord(null)
    setStaticPhase('loading')
    setDownloadError(false)
    setExporting(null)
    setReviewing(false)
    setReviewError(false)
    try {
      const result = await client.staticPublication(record.id, organizationId, controller.signal)
      if (controller.signal.aborted) return
      setStaticRecord(result)
      setStaticPhase('ready')
    } catch {
      if (!controller.signal.aborted) setStaticPhase('error')
    }
  }

  async function downloadReviewPdf() {
    if (!selected || reviewing) return
    const evidenceId = selected.id
    const controller = new AbortController()
    reviewRequest.current = controller
    setReviewing(true)
    setReviewError(false)
    try {
      const result = await client.reviewPdf(evidenceId, organizationId, controller.signal)
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a')
      link.href = url
      link.download = result.name
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      if (!controller.signal.aborted) setReviewError(true)
    } finally {
      if (!controller.signal.aborted) setReviewing(false)
    }
  }

  async function download(format: RepositoryStaticFormat) {
    if (!organizationId || !selected || !staticRecord?.verified || staticRecord.source_commit !== selected.source_commit
      || !/^[a-f0-9]{64}$/.test(staticRecord.content_digest) || exporting) return
    const controller = new AbortController()
    exportRequest.current = controller
    setExporting(format)
    setDownloadError(false)
    try {
      const result = await client.exportStatic(selected.id, format, staticRecord.content_digest, organizationId, controller.signal)
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a')
      link.href = url
      link.download = result.name
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      if (!controller.signal.aborted) setDownloadError(true)
    } finally {
      if (!controller.signal.aborted) setExporting(null)
    }
  }

  const verifiedStatic = staticPhase === 'ready' && staticRecord?.verified
    && staticRecord.source_commit === selected?.source_commit && /^[a-f0-9]{64}$/.test(staticRecord.content_digest)

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
      <p>{translate('repository.reviewPdfNotice')}</p>
      <button type="button" className="secondary-button" disabled={reviewing} onClick={() => { void downloadReviewPdf() }}>{reviewing ? translate('repository.reviewPdfPreparing') : translate('repository.reviewPdfDownload')}</button>
      {reviewError && <p role="alert" className="form-message error">{translate('repository.reviewPdfFailed')}</p>}
      {staticPhase === 'loading' && <p role="status">{translate('repository.staticChecking')}</p>}
      {staticPhase === 'error' && <p role="alert" className="form-message error">{translate('repository.staticCheckFailed')} <button type="button" className="secondary-button" onClick={() => { void inspect(selected) }}>{translate('common.retry')}</button></p>}
      {staticPhase === 'ready' && !staticRecord && <p>{translate('repository.staticNotFinalized')}</p>}
      {staticPhase === 'ready' && staticRecord && <p role="status">{translate(verifiedStatic ? 'repository.staticVerified' : 'repository.staticUnverified')}</p>}
      {verifiedStatic && organizationId && <><p>{translate('repository.staticDownloadNotice')}</p><div className="form-actions">{(['md', 'html', 'pdf'] as const).map((format) => <button key={format} type="button" className="secondary-button" disabled={exporting !== null} onClick={() => { void download(format) }}>{translate(format === 'md' ? 'repository.staticDownloadMarkdown' : format === 'html' ? 'repository.staticDownloadHtml' : 'repository.staticDownloadPdf')}</button>)}</div></>}
      {exporting && <p role="status">{translate('repository.staticDownloading')}</p>}
      {downloadError && <p role="alert" className="form-message error">{translate('repository.staticDownloadFailed')}</p>}
    </div>}
  </section>
}
