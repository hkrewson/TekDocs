import { useLayoutEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Download, ShieldCheck, X } from 'lucide-react'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import { translate } from '../i18n/localization'
import type { DocumentPublicationDetail, DocumentScope, DocumentsClient } from './api'

export type PublicationView = { sourceId: string; publicationId: string; phase: 'loading' | 'ready' | 'error'; record?: DocumentPublicationDetail }
export type PublicationSection = 'content' | 'downloads' | 'history'

export function PublicationViewer({ view, scope, client, section, onSectionChange, onClose, onRetry, children }: {
  view: PublicationView; scope: DocumentScope; client: DocumentsClient; section: PublicationSection; onSectionChange: (section: PublicationSection) => void; onClose: () => void; onRetry: () => void; children: ReactNode
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [view.phase])
  const record = view.record
  return <section className="document-workspace static-publication" aria-label={translate('documentation.publication')}>
    <div className="document-edit-heading"><div><h2 ref={heading} tabIndex={-1}>{record?.title ?? translate('documentation.publication')}</h2><p>{translate('documentation.publicationHelp')}</p></div><button className="icon-button" type="button" aria-label={translate('documentation.closePublication')} onClick={onClose}><X size={19} /></button></div>
    {view.phase === 'loading' && <p className="empty-state" role="status">{translate('documentation.loadingPublication')}</p>}
    {view.phase === 'error' && <div><p role="alert">{translate('documentation.publicationUnavailable')}</p><button className="secondary-button" type="button" onClick={onRetry}>{translate('common.tryAgain')}</button></div>}
    {view.phase === 'ready' && record && <>
        <dl className="publication-lifecycle">
          <div><dt>{translate('documentation.status')}</dt><dd>{record.lifecycle_state.replace('_', ' ')}</dd></div>
          <div><dt>{translate('documentation.audienceLabel')}</dt><dd>{record.audience === 'msp_internal' ? translate('documentation.audienceMspStaff') : translate('documentation.audienceClientPortal')}</dd></div>
        </dl>

      <p className="publication-verification" role={record.verification.valid ? undefined : 'alert'}><ShieldCheck size={18} aria-hidden="true" />{record.verification.valid ? translate('documentation.signatureVerified') : translate('documentation.verificationFailed')}</p>
      {children}
      <div className="publication-section-nav" role="group" aria-label={translate('documentation.publicationSections')}>
        {(['content', 'downloads', 'history'] as const).map((value) => <button key={value} className="secondary-button" type="button" aria-pressed={section === value} onClick={() => onSectionChange(value)}>{translate(`documentation.publicationSection.${value}`)}</button>)}
      </div>
      {section === 'content' && <section className="publication-content" aria-label={translate('documentation.publicationSection.content')}><SanitizedMarkdown html={record.sanitized_html} /></section>}
      {section === 'downloads' && <section aria-labelledby="publication-downloads-heading">
        <h3 id="publication-downloads-heading">{translate('documentation.publicationSection.downloads')}</h3>
        <p>{translate('documentation.retainedDownloadHelp')}</p>
        <div className="document-actions">
          <a className="secondary-button" href={client.publicationExportUrl(scope, view.sourceId, record.id, 'md')}><Download size={15} />{translate('documentation.downloadMarkdown')}</a>
          <a className="secondary-button" href={client.publicationExportUrl(scope, view.sourceId, record.id, 'html')}><Download size={15} />{translate('documentation.downloadHtml')}</a>
          <a className="secondary-button" href={client.publicationExportUrl(scope, view.sourceId, record.id, 'pdf')}><Download size={15} />{translate('documentation.downloadPdf')}</a>
          <a className="secondary-button" href={client.publicationExportUrl(scope, view.sourceId, record.id, 'docx')} title={translate('documentation.wordCompatibility')}><Download size={15} />{translate('documentation.downloadDocx')}</a>
          <a className="secondary-button" href={client.publicationManifestUrl(scope, view.sourceId, record.id)}><Download size={15} />{translate('documentation.downloadManifest')}</a>
        </div>
        <section className="publication-artifacts" aria-labelledby="retained-artifacts-heading"><h3 id="retained-artifacts-heading">{translate('documentation.publishedFiles')}</h3>{!record.artifacts.some((artifact) => artifact.kind === 'attachment') && <p>{translate('documentation.noRetainedFiles')}</p>}<ul>{record.artifacts.filter((artifact) => artifact.kind === 'attachment').map((artifact) => <li key={artifact.id}><a href={client.publicationArtifactUrl(scope, view.sourceId, record.id, artifact.id)}><strong>{artifact.filename}</strong><small>{translate('documentation.retainedFileDetails', { type: artifact.media_type, size: artifact.size.toLocaleString(), checksum: artifact.checksum.slice(0, 12) })}</small></a></li>)}</ul></section>
        <div className="publication-integrity"><ShieldCheck size={18} /><div><strong>{translate('documentation.verificationDetails')}</strong><span>{record.signature_algorithm} · {translate('documentation.publishedBy', { date: new Date(record.published_at).toLocaleString(), name: record.published_by ?? translate('documentation.systemActor') })}</span><code>{translate('documentation.publicationDigest', { digest: record.content_digest })}</code><code>{translate('documentation.publicationKey', { fingerprint: record.key_fingerprint })}</code></div></div>
      </section>}
      {section === 'history' && <>
        <dl className="publication-lifecycle">
          <div><dt>{translate('documentation.reason')}</dt><dd>{record.reason}</dd></div>
          <div><dt>{translate('documentation.keepUntil')}</dt><dd>{record.retention === 'permanent' ? translate('documentation.permanent') : translate('documentation.reviewOn', { date: record.retention_review_on ?? '' })}</dd></div>
        </dl>
        <section className="publication-audiences" aria-labelledby="publication-audiences-heading"><h3 id="publication-audiences-heading">{translate('documentation.availability')}</h3><dl>{record.audience_projections.map((projection) => <div key={projection.audience}><dt>{projection.audience === 'msp_staff' ? translate('documentation.mspStaff') : translate('documentation.clientPortal')}</dt><dd>{projection.available ? translate('documentation.available') : projection.state.replaceAll('_', ' ')}</dd></div>)}</dl></section>
        <section className="publication-history" aria-labelledby="publication-history-heading"><h3 id="publication-history-heading">{translate('documentation.publicationHistory')}</h3>{record.control_events.length === 0 && <p>{translate('documentation.noPublicationHistory')}</p>}<ol>{record.control_events.map((event) => <li key={event.id}><strong>{event.action.replace('_', ' ')}</strong><span>{event.reason}</span><small>{event.actor ?? translate('documentation.systemActor')} · {new Date(event.occurred_at).toLocaleString()}</small></li>)}</ol></section>
      </>}
    </>}
  </section>
}
