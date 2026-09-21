import { lazy, Suspense, useLayoutEffect, useRef } from 'react'
import { Paperclip, RefreshCw, Trash2, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { DocumentRecord, DocumentScope, DocumentsClient } from './api'

const PdfViewer = lazy(async () => ({ default: (await import('./PdfViewer')).PdfViewer }))
export type ViewedPdf = { filename: string; url: string }

export function DocumentFiles({ document, scope, client, busy, viewedPdf, onViewPdf, onUpload, onReplace, onRemove, onInsert, onClose }: {
  document: DocumentRecord; scope: DocumentScope; client: DocumentsClient; busy: boolean
  viewedPdf: ViewedPdf | null; onViewPdf: (file: ViewedPdf | null) => void
  onUpload: (file: File) => Promise<void>; onReplace: (file: File) => Promise<void>
  onRemove: (id: string) => Promise<void>; onInsert: (id: string, name: string) => void; onClose: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  const upload = useRef<HTMLInputElement>(null)
  const replacement = useRef<HTMLInputElement>(null)
  const pdfTrigger = useRef<HTMLButtonElement | null>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <section className="document-context-panel document-attachments document-files" aria-labelledby="document-attachments-heading">
    <div className="section-heading">
      <div><h2 ref={heading} tabIndex={-1} id="document-attachments-heading">{translate('files.heading')}</h2><p>{translate('documentation.filesHelp')}</p></div>
      <button className="icon-button" type="button" disabled={busy} aria-label={translate('documentation.closeFiles')} onClick={onClose}><X size={16} /></button>
    </div>
    <div className="document-actions">
      <input ref={upload} disabled={busy} aria-label={translate('files.kind.attachment')} className="sr-only" type="file" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void onUpload(file) }} />
      <button className="secondary-button" type="button" disabled={busy} onClick={() => upload.current?.click()}><Paperclip size={15} aria-hidden="true" />{translate('documentation.addFile')}</button>
      {document.primary_file && <>
        <input ref={replacement} disabled={busy} aria-label={translate('documentation.replacementPrimaryFile')} className="sr-only" type="file" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void onReplace(file) }} />
        <button className="secondary-button" type="button" disabled={busy} onClick={() => replacement.current?.click()}><RefreshCw size={15} aria-hidden="true" />{translate('documentation.replaceFile')}</button>
      </>}
    </div>
    {busy && <p role="status">{translate('documentation.fileOperationPending')}</p>}
    {document.primary_file_versions.length > 0 && <section className="primary-file-history" aria-labelledby="primary-file-history-heading">
      <h3 id="primary-file-history-heading">{translate('documentation.fileVersions')}</h3>
      <p>{translate('documentation.retainedVersionsHelp')}</p>
      <ul>{document.primary_file_versions.map((version) => {
        const url = client.attachmentDownloadUrl(scope, document.id, version.id)
        return <li key={version.id}>
          <span><strong>{version.filename}</strong><small>{translate(version.is_current ? 'documentation.currentFileVersion' : 'documentation.retainedFileVersion', { version: version.version_number, size: version.size.toLocaleString() })}</small></span>
          <div>{version.media_type === 'application/pdf' && <button className="secondary-button" type="button" disabled={busy} onClick={(event) => { pdfTrigger.current = event.currentTarget; onViewPdf({ filename: version.filename, url }) }}>{translate('documentation.viewPdf')}</button>}<a className="secondary-button" href={url}>{translate('files.download')}</a></div>
        </li>
      })}</ul>
    </section>}
    <section aria-labelledby="attached-files-heading">
      <h3 id="attached-files-heading">{translate('documentation.attachedFiles')}</h3>
      {document.attachments.length === 0 ? <p className="empty-state">{translate('documentation.noAttachments')}</p> : <ul>{document.attachments.map((attachment) => {
        const url = client.attachmentDownloadUrl(scope, document.id, attachment.id)
        return <li key={attachment.id}>
          <a href={url}><strong>{attachment.filename}</strong><small>{translate('documentation.attachmentDetails', { type: attachment.media_type, size: attachment.size.toLocaleString() })}</small></a>
          <div>
            {attachment.media_type === 'application/pdf' && <button className="secondary-button" type="button" disabled={busy} onClick={(event) => { pdfTrigger.current = event.currentTarget; onViewPdf({ filename: attachment.filename, url }) }}>{translate('documentation.viewPdf')}</button>}
            <button className="secondary-button" type="button" disabled={busy} onClick={() => onInsert(attachment.id, attachment.filename)}>{translate('documentation.insertHere')}</button>
            <button className="icon-button" type="button" disabled={busy} aria-label={translate('documentation.removeFile', { filename: attachment.filename })} onClick={() => { void onRemove(attachment.id) }}><Trash2 size={15} /></button>
          </div>
        </li>
      })}</ul>}
    </section>
    {viewedPdf && <Suspense fallback={<p role="status">{translate('documentation.loadingPdfViewer')}</p>}><PdfViewer filename={viewedPdf.filename} url={viewedPdf.url} onClose={() => { onViewPdf(null); window.requestAnimationFrame(() => { if (pdfTrigger.current?.isConnected) pdfTrigger.current.focus(); else heading.current?.focus() }) }} /></Suspense>}
  </section>
}
