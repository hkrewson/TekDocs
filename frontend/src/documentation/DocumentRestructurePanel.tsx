import { X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { BlockKind, DocumentRestructurePreview } from './api'

type DocumentRestructurePanelProps = {
  blockKindLabel: (kind: BlockKind) => string
  busy: boolean
  documentTitle: string
  phase: 'idle' | 'loading' | 'ready' | 'error'
  preview: DocumentRestructurePreview | null
  onApply: () => void
  onClose: () => void
}

export function DocumentRestructurePanel({
  blockKindLabel,
  busy,
  documentTitle,
  phase,
  preview,
  onApply,
  onClose,
}: DocumentRestructurePanelProps) {
  return <section className="document-context-panel document-restructure" aria-labelledby="document-restructure-heading">
    <div className="section-heading">
      <div>
        <h2 id="document-restructure-heading">{translate('documentation.splitSections')}</h2>
        <p>{translate('documentation.splitSectionsHelp')}</p>
      </div>
      <button className="icon-button" type="button" aria-label={translate('documentation.closeSectionConversion')} onClick={onClose}><X size={16} /></button>
    </div>
    {phase === 'loading' && <p role="status">{translate('documentation.reviewingSections')}</p>}
    {phase === 'error' && <p role="alert">{translate('documentation.sectionPreviewUnavailable')}</p>}
    {phase === 'ready' && preview && <>
      {preview.blockers.length > 0 && <div className="document-restructure-notices" role="alert">
        <strong>{translate('documentation.documentNotChanged')}</strong>
        <ul>{preview.blockers.map((item) => <li key={item.code}>{item.detail}</li>)}</ul>
      </div>}
      {preview.warnings.length > 0 && <div className="document-restructure-notices">
        <strong>{translate('documentation.sectionWarnings')}</strong>
        <ul>{preview.warnings.map((item) => <li key={item.code}>{item.detail}</li>)}</ul>
      </div>}
      {preview.eligible && <>
        <p>{translate('documentation.sectionChangeSummary', { count: preview.section_count })}</p>
        <ol className="document-restructure-sections">{preview.sections.map((section) => <li key={`${section.position}-${section.checksum}`}>
          <details>
            <summary><strong>{section.name.replace(`${documentTitle} — `, '')}</strong><span>{blockKindLabel(section.kind)}</span></summary>
            <pre>{section.markdown}</pre>
          </details>
        </li>)}</ol>
        <div className="document-actions">
          <button className="primary-button" type="button" disabled={busy} onClick={onApply}>{busy ? translate('documentation.splitting') : translate('documentation.createSections', { count: preview.section_count })}</button>
          <button className="secondary-button" type="button" disabled={busy} onClick={onClose}>{translate('common.cancel')}</button>
        </div>
      </>}
    </>}
  </section>
}
