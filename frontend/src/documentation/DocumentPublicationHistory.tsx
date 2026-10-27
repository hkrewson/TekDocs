import { useLayoutEffect, useRef } from 'react'
import { FileCheck2, X } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { DocumentPublication } from './api'

export function DocumentPublicationHistory({ publications, onOpen, onClose }: {
  publications: DocumentPublication[]
  onOpen: (publication: DocumentPublication) => void
  onClose: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <section className="document-context-panel" aria-labelledby="document-publications-heading">
    <div className="section-heading">
      <div><h2 id="document-publications-heading" tabIndex={-1} ref={heading}>{translate('documentation.publicationHistory')}</h2><p>{translate('documentation.retainedPublicationHistoryHelp')}</p></div>
      <button type="button" className="icon-button" aria-label={translate('documentation.closePublicationHistory')} onClick={onClose}><X size={16} /></button>
    </div>
    {publications.length === 0 ? <p>{translate('documentation.noPublishedVersions')}</p> : <ul className="static-publication-list">
      {publications.map(publication => <li key={publication.id}><button type="button" onClick={() => onOpen(publication)}>
        <FileCheck2 size={15} aria-hidden="true" /><span><strong>{publication.title}</strong><small>{translate('documentation.publishedLabel', {
          state: publication.lifecycle_state.replaceAll('_', ' '),
          audience: publication.audience === 'msp_internal' ? translate('documentation.audienceMspStaff') : translate('documentation.audienceClientPortal'),
          date: new Date(publication.published_at).toLocaleString(),
        })}</small></span>
      </button></li>)}
    </ul>}
  </section>
}
