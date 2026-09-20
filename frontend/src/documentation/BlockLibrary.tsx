import { useEffect, useRef, useState } from 'react'
import { CollectionPagination } from '../CollectionPagination'
import { translate } from '../i18n/localization'
import type { BlockLibraryItem, BlockLibraryResult, DocumentScope, DocumentsClient } from './api'

export function BlockLibrary({ scope, documentId, client, busy, onInsert }: { scope: DocumentScope; documentId: string; client: DocumentsClient; busy: boolean; onInsert: (block: BlockLibraryItem) => void }) {
  const search = useRef<HTMLInputElement>(null)
  useEffect(() => { search.current?.focus() }, [])
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [result, setResult] = useState<BlockLibraryResult | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.searchBlockLibrary(scope, query, controller.signal, page, documentId).then((value) => {
        if (!controller.signal.aborted) { setResult(value); setPhase('ready') }
      }).catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [client, scope, query, page, retry, documentId])
  return <div className="block-library">
    <label>{translate('documentation.findReusable')}<input ref={search} disabled={busy} type="search" maxLength={120} value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); setPhase('loading') }} placeholder={translate('documentation.searchReusable')} /></label>
    {phase === 'loading' && <p role="status">{translate('common.loading')}</p>}
    {phase === 'error' && <div role="alert"><p>{translate('documentation.blockLoadFailed')}</p><button className="secondary-button" type="button" onClick={() => { setPhase('loading'); setRetry((value) => value + 1) }}>{translate('common.retry')}</button></div>}
    {phase === 'ready' && result && <>
      {result.results.length === 0 && <p>{translate('documentation.noBlocks')}</p>}
      <ul className="reuse-results">{result.results.map((block) => <li key={block.id}><div><strong>{block.name.replace(/ — content$/, '')}</strong><p>{block.source_document_title} · {translate(block.owner_kind === 'msp' ? 'documentation.mspWorkspace' : 'documentation.thisClient')}</p><details><summary>{translate('documentation.previewSection')}</summary><pre className="block-preview">{block.markdown}</pre></details></div><button className="secondary-button" type="button" disabled={busy} onClick={() => onInsert(block)}>{translate('documentation.insert')}</button></li>)}</ul>
      <CollectionPagination label={translate('documentation.blocksLabel')} page={result.page ?? page} pageSize={result.page_size ?? 20} count={result.count} hasMore={result.has_more ?? false} onPageChange={(value) => { setPage(value); setPhase('loading') }} />
    </>}
  </div>
}
