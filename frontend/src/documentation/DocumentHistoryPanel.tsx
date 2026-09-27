import { X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { BlockRevision, BlockRevisionDetail } from './api'

type DocumentHistoryPanelProps = {
  count: number
  hasMore: boolean
  history: BlockRevision[]
  page: number
  phase: 'idle' | 'loading' | 'ready' | 'error'
  viewedRevision: BlockRevisionDetail | null
  onClose: () => void
  onInspect: (revision: BlockRevision) => void
  onPageChange: (page: number) => void
  onRetry: () => void
}

export function DocumentHistoryPanel({
  count,
  hasMore,
  history,
  page,
  phase,
  viewedRevision,
  onClose,
  onInspect,
  onPageChange,
  onRetry,
}: DocumentHistoryPanelProps) {
  return <section className="document-context-panel revision-history" aria-labelledby="revision-history-heading">
    <div className="section-heading">
      <div>
        <h2 id="revision-history-heading">{translate('documentation.historyHeading')}</h2>
        <p>{translate(count === 1 ? 'documentation.historySummaryOne' : 'documentation.historySummary', { count, page })}</p>
      </div>
      <button className="icon-button" type="button" aria-label={translate('documentation.closeHistory')} onClick={onClose}><X size={16} /></button>
    </div>
    {phase === 'loading' && <p role="status">{translate('documentation.loadingHistory')}</p>}
    {phase === 'error' && <div role="alert">
      <p>{translate('documentation.historyUnavailable')}</p>
      <button className="secondary-button" type="button" onClick={onRetry}>{translate('common.retry')}</button>
    </div>}
    {phase === 'ready' && <>
      <div className="revision-history-body">
        <ol>{history.map((item) => <li key={item.id}>
          <button type="button" onClick={() => onInspect(item)}>
            <strong>{translate('documentation.revisionNumber', { number: item.revision_number })}</strong>
            {item.is_current && <span>{translate('documentation.current')}</span>}
            <small>{item.created_by ?? translate('documentation.revisionSystemActor')} · {new Date(item.created_at).toLocaleString()}</small>
          </button>
        </li>)}</ol>
        <div className="revision-diff">
          {viewedRevision
            ? <><h3>{translate('documentation.revisionNumber', { number: viewedRevision.revision_number })}</h3><pre tabIndex={0}>{viewedRevision.diff_from_parent || translate('documentation.noRevisionChanges')}</pre></>
            : <p>{translate('documentation.selectRevision')}</p>}
        </div>
      </div>
      <nav className="history-pagination" aria-label={translate('documentation.historyPages')}>
        <button className="secondary-button" type="button" disabled={page === 1} onClick={() => onPageChange(page - 1)}>{translate('documentation.newer')}</button>
        <button className="secondary-button" type="button" disabled={!hasMore} onClick={() => onPageChange(page + 1)}>{translate('documentation.older')}</button>
      </nav>
    </>}
  </section>
}
