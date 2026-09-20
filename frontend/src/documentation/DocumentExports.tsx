import { useLayoutEffect, useRef } from 'react'
import { Download, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { DocumentRecord, DocumentScope, DocumentsClient } from './api'

export function DocumentExports({ document, scope, client, selectedIds, onToggle, onClose }: {
  document: DocumentRecord; scope: DocumentScope; client: DocumentsClient
  selectedIds: string[]; onToggle: (id: string) => void; onClose: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  const exportableFiles = [...document.primary_file_versions, ...document.attachments]
  return <section className="document-context-panel document-export-panel" aria-labelledby="document-export-heading">
    <div className="section-heading">
      <div><h2 ref={heading} tabIndex={-1} id="document-export-heading">{translate('documentation.downloadEditableCopy')}</h2><p>{translate('documentation.downloadEditableHelp')}</p></div>
      <button className="icon-button" type="button" aria-label={translate('documentation.closeExport')} onClick={onClose}><X size={16} /></button>
    </div>
    <div className="document-actions">
      {(['md', 'html', 'pdf', 'docx'] as const).map((format) => <a key={format} className="secondary-button" href={client.exportUrl(scope, document.id, format)} title={format === 'docx' ? translate('documentation.wordCompatibility') : undefined}>
        <Download size={15} aria-hidden="true" />{translate(`documentation.exportFormat.${format}`)}
      </a>)}
    </div>
    <section className="portable-export" aria-labelledby="portable-export-heading">
      <h3 id="portable-export-heading">{translate('documentation.portableZip')}</h3>
      <p>{translate('documentation.portableZipHelp')}</p>
      {exportableFiles.length === 0 && <p>{translate('documentation.noExportFiles')}</p>}
      {exportableFiles.length > 0 && <fieldset>
        <legend>{translate('documentation.includeFiles')}</legend>
        {exportableFiles.map((attachment) => <div key={attachment.id}>
          <label className="checkbox-field">
            <input type="checkbox" checked={selectedIds.includes(attachment.id)} onChange={() => onToggle(attachment.id)} />
            <span><strong>{attachment.filename}</strong><small>{'version_number' in attachment && typeof attachment.version_number === 'number'
              ? translate('documentation.exportPrimaryFile', { version: attachment.version_number, size: attachment.size.toLocaleString() })
              : translate('documentation.exportAttachedFile', { size: attachment.size.toLocaleString() })}</small></span>
          </label>
        </div>)}
      </fieldset>}
      <p role="status">{translate('documentation.exportSelectionCount', { count: selectedIds.length })}</p>
      <a className="primary-button" href={client.exportUrl(scope, document.id, 'bundle', selectedIds)}><Download size={15} aria-hidden="true" />{translate('documentation.downloadZip')}</a>
    </section>
  </section>
}
