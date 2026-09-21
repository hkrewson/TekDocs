import { useEffect, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { DocumentRecord, DocumentResult, DocumentScope, DocumentsClient } from './api'

export function DocumentLinkPicker({ scope, documentId, client, busy, onInsert }: { scope: DocumentScope; documentId: string; client: DocumentsClient; busy: boolean; onInsert: (document: DocumentRecord) => void }) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [result, setResult] = useState<DocumentResult | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.list(scope, controller.signal, {
        q: query,
        exclude_document: documentId,
        ordering: 'title',
        page,
        page_size: 20,
      }).then((value) => {
        if (!controller.signal.aborted) { setResult(value); setPhase('ready') }
      }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [client, documentId, page, query, retry, scope])

  return <div className="document-link-picker">
    <label>{translate('documentation.findDocument')}<input disabled={busy} type="search" maxLength={120} value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); setPhase('loading') }} /></label>
    {phase === 'loading' && <p role="status">{translate('common.loading')}</p>}
    {phase === 'error' && <div role="alert"><p>{translate('documentation.documentLinkLoadFailed')}</p><button className="secondary-button" type="button" onClick={() => { setPhase('loading'); setRetry((value) => value + 1) }}>{translate('common.retry')}</button></div>}
    {phase === 'ready' && result && <>
      {result.results.length === 0 && <p>{translate('documentation.noLinkDocuments')}</p>}
      <ul>{result.results.map((document) => <li key={document.id}><span><strong>{document.title}</strong><small>{[document.collection, document.category, document.health_status?.replaceAll('_', ' ')].filter(Boolean).join(' · ')}</small></span><button className="secondary-button" type="button" disabled={busy} aria-label={`${translate('documentation.insert')} ${document.title}`} onClick={() => onInsert(document)}>{translate('documentation.insert')}</button></li>)}</ul>
      <CollectionPagination label={translate('documentation.documents').toLocaleLowerCase()} page={result.page ?? page} pageSize={result.page_size ?? 20} count={result.count} hasMore={result.has_more ?? false} onPageChange={(value) => { setPage(value); setPhase('loading') }} />
    </>}
  </div>
}
