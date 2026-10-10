import { ArrowLeft, Download, FileText, LogOut } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import type { AuthenticatedContext } from '../auth/api'
import { InvoiceBillTo } from '../accounting/InvoiceBillTo'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import { translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
import { NotificationInbox } from '../notifications/NotificationInbox'
import { browserPortalNotificationsClient } from '../notifications/api'
import type { NotificationsClient, NotificationTarget } from '../notifications/api'
import { RecordSections } from '../records/RecordNavigation'
import { portalClient, type PortalDocument, type PortalDocumentDetail, type PortalInvoice, type PortalRepositoryPublication, type PortalRepositoryPublicationDetail } from './api'
import '../collections/collections.css'
import './portal.css'

type PortalSection = 'documents' | 'publications' | 'invoices'
type Phase = 'idle' | 'loading' | 'ready' | 'error'

export function ClientPortal({ context, onSignOut, signingOut, signOutError, notificationsClient = browserPortalNotificationsClient }: {
  context: AuthenticatedContext
  onSignOut: () => Promise<void>
  signingOut: boolean
  signOutError: string | null
  notificationsClient?: NotificationsClient
}) {
  const organization = context.organization
  const [parameters, setParameters] = useSearchParams()
  const requestedSection = parameters.get('section')
  const section: PortalSection = requestedSection === 'invoices' || requestedSection === 'publications' ? requestedSection : 'documents'
  const documentId = section === 'documents' ? parameters.get('document') : null
  const publicationId = section === 'publications' ? parameters.get('publication') : null
  const invoiceId = section === 'invoices' ? parameters.get('invoice') : null
  const sections = useMemo(() => [
    { id: 'documents', label: translate('portal.documents'), href: '?section=documents' },
    { id: 'publications', label: translate('portal.repositoryPublications'), href: '?section=publications' },
    { id: 'invoices', label: translate('portal.invoices'), href: '?section=invoices' },
  ], [])
  const [documents, setDocuments] = useState<PortalDocument[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<PortalDocumentDetail | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [detailLoading, setDetailLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<{ section: PortalSection; message: string } | null>(null)
  const [publications, setPublications] = useState<PortalRepositoryPublication[]>([])
  const [publicationCursor, setPublicationCursor] = useState<string | null>(null)
  const [selectedPublication, setSelectedPublication] = useState<PortalRepositoryPublicationDetail | null>(null)
  const [publicationPhase, setPublicationPhase] = useState<Phase>('idle')
  const [loadingMorePublications, setLoadingMorePublications] = useState(false)
  const [publicationListError, setPublicationListError] = useState<string | null>(null)
  const [invoices, setInvoices] = useState<PortalInvoice[]>([])
  const [selectedInvoice, setSelectedInvoice] = useState<PortalInvoice | null>(null)
  const [invoicePhase, setInvoicePhase] = useState<Phase>('idle')
  const [invoiceCursor, setInvoiceCursor] = useState<string | null>(null)
  const [loadingMoreInvoices, setLoadingMoreInvoices] = useState(false)
  const documentsStarted = useRef(false)
  const publicationsStarted = useRef(false)
  const invoicesStarted = useRef(false)

  const showDocuments = useCallback((id?: string) => {
    const next = new URLSearchParams({ section: 'documents' })
    if (id) next.set('document', id)
    setParameters(next)
  }, [setParameters])

  const showInvoices = useCallback((id?: string) => {
    const next = new URLSearchParams({ section: 'invoices' })
    if (id) next.set('invoice', id)
    setParameters(next)
  }, [setParameters])

  const showPublications = useCallback((id?: string) => {
    const next = new URLSearchParams({ section: 'publications' })
    if (id) next.set('publication', id)
    setParameters(next)
  }, [setParameters])

  const loadDocuments = useCallback(async (cursor?: string) => {
    if (cursor) setLoadingMore(true)
    else setPhase('loading')
    setError(null)
    try {
      const result = await portalClient.listDocuments(cursor)
      setDocuments((current) => cursor
        ? [...current, ...result.results.filter((item) => !current.some((existing) => existing.id === item.id))]
        : result.results)
      setNextCursor(result.next_cursor ?? null)
      setPhase('ready')
    } catch {
      setError({ section: 'documents', message: translate(cursor ? 'portal.moreDocumentsLoadFailed' : 'portal.documentsLoadFailed') })
      if (!cursor) setPhase('error')
    } finally {
      setLoadingMore(false)
    }
  }, [])

  const loadInvoices = useCallback(async (cursor?: string) => {
    if (cursor) setLoadingMoreInvoices(true)
    else setInvoicePhase('loading')
    setError(null)
    try {
      const result = await portalClient.listInvoices(cursor)
      setInvoices((current) => cursor
        ? [...current, ...result.results.filter((item) => !current.some((existing) => existing.id === item.id))]
        : result.results)
      setInvoiceCursor(result.next_cursor ?? null)
      setInvoicePhase('ready')
    } catch {
      setError({ section: 'invoices', message: translate('portal.invoiceLoadFailed') })
      if (!cursor) setInvoicePhase('error')
    } finally {
      setLoadingMoreInvoices(false)
    }
  }, [])

  const loadPublications = useCallback(async (cursor?: string) => {
    if (cursor) setLoadingMorePublications(true)
    else setPublicationPhase('loading')
    setPublicationListError(null)
    try {
      const result = await portalClient.listRepositoryPublications(cursor)
      setPublications((current) => cursor
        ? [...current, ...result.results.filter((item) => !current.some((existing) => existing.id === item.id))]
        : result.results)
      setPublicationCursor(result.next_cursor ?? null)
      setPublicationPhase('ready')
    } catch {
      setPublicationListError(translate(cursor ? 'portal.morePublicationsLoadFailed' : 'portal.publicationsLoadFailed'))
      if (!cursor) setPublicationPhase('error')
    } finally {
      setLoadingMorePublications(false)
    }
  }, [])

  useEffect(() => {
    const shouldLoadDocuments = section === 'documents' && phase === 'idle' && !documentsStarted.current
    const shouldLoadPublications = (section === 'documents' || section === 'publications') && publicationPhase === 'idle' && !publicationsStarted.current
    const shouldLoadInvoices = section === 'invoices' && invoicePhase === 'idle' && !invoicesStarted.current
    if (shouldLoadDocuments) documentsStarted.current = true
    if (shouldLoadPublications) publicationsStarted.current = true
    if (shouldLoadInvoices) invoicesStarted.current = true
    void Promise.resolve().then(() => {
      if (shouldLoadDocuments) void loadDocuments()
      if (shouldLoadPublications) void loadPublications()
      if (shouldLoadInvoices) return loadInvoices()
    })
  }, [invoicePhase, loadDocuments, loadInvoices, loadPublications, phase, publicationPhase, section])

  useEffect(() => {
    if (!documentId) return
    let active = true
    void Promise.resolve().then(async () => {
      if (!active) return
      setDetailLoading(true)
      setSelected(null)
      setError(null)
      try {
        const result = await portalClient.getDocument(documentId)
        if (active) setSelected(result)
      } catch {
        if (active) setError({ section: 'documents', message: translate('portal.documentUnavailable') })
      } finally {
        if (active) setDetailLoading(false)
      }
    })
    return () => { active = false; setDetailLoading(false) }
  }, [documentId])

  useEffect(() => {
    if (!publicationId) return
    let active = true
    void Promise.resolve().then(async () => {
      if (!active) return
      setDetailLoading(true)
      setSelectedPublication(null)
      setError(null)
      try {
        const result = await portalClient.getRepositoryPublication(publicationId)
        if (active) setSelectedPublication(result)
      } catch {
        if (active) setError({ section: 'publications', message: translate('portal.documentUnavailable') })
      } finally {
        if (active) setDetailLoading(false)
      }
    })
    return () => { active = false; setDetailLoading(false) }
  }, [publicationId])

  useEffect(() => {
    if (!invoiceId) return
    let active = true
    void Promise.resolve().then(async () => {
      if (!active) return
      setDetailLoading(true)
      setSelectedInvoice(null)
      setError(null)
      try {
        const result = await portalClient.getInvoice(invoiceId)
        if (active) setSelectedInvoice(result)
      } catch {
        if (active) setError({ section: 'invoices', message: translate('portal.invoiceUnavailable') })
      } finally {
        if (active) setDetailLoading(false)
      }
    })
    return () => { active = false; setDetailLoading(false) }
  }, [invoiceId])

  function openNotificationTarget(target: NotificationTarget) {
    if (target.kind === 'portal_document' && target.publication_id) showDocuments(target.publication_id)
    else if (target.kind === 'portal_documents') showDocuments()
    else if (target.kind === 'portal_repository_publication' && target.publication_id) showPublications(target.publication_id)
  }

  const activePhase = section === 'documents' && (phase === 'loading' || publicationPhase === 'loading')
    ? 'loading' : section === 'documents' ? phase : section === 'publications' ? publicationPhase : invoicePhase
  return (
    <div className="client-portal-shell">
      <a className="skip-link" href="#portal-main-content">{translate('shell.skip')}</a>
      <header className="client-portal-header">
        <div className="client-portal-brand"><span className="brand-mark" aria-hidden="true">T</span><span>TekDocs</span></div>
        <div className="client-portal-account">
          <span>{context.user.display_name}</span>
          <NotificationInbox client={notificationsClient} onOpen={openNotificationTarget} />
          <button className="secondary-button" type="button" disabled={signingOut} onClick={() => { void onSignOut() }}>
            <LogOut size={16} aria-hidden="true" />{signingOut ? translate('portal.signingOut') : translate('shell.signOut')}
          </button>
        </div>
      </header>
      <main id="portal-main-content" className="client-portal-main" aria-busy={activePhase === 'loading' || detailLoading || loadingMore || loadingMorePublications || loadingMoreInvoices}>
        {signOutError && <div className="form-error" role="alert">{signOutError}</div>}
        <header className="page-header"><div><h1>{organization?.name ?? 'Client portal'}</h1><p>{translate('portal.summary')}</p></div></header>
        <RecordSections sections={sections} current={section} />
        {error?.section === section && <div className="form-error" role="alert">{error.message}</div>}
        {detailLoading && (documentId || publicationId || invoiceId) && <section className="content-section" aria-live="polite"><p role="status">{translate(section === 'invoices' ? 'portal.loadingInvoice' : 'portal.loadingDocument')}</p></section>}
        {!detailLoading && section === 'invoices' && selectedInvoice?.id === invoiceId ? <InvoiceDetail invoice={selectedInvoice} onBack={() => showInvoices()} />
          : !detailLoading && section === 'documents' && selected?.id === documentId ? <DocumentDetail document={selected} onBack={() => showDocuments()} />
            : !detailLoading && section === 'publications' && selectedPublication?.id === publicationId ? <RepositoryPublicationDetail publication={selectedPublication} onBack={() => { showPublications(); void loadPublications() }} />
              : section === 'invoices' ? <InvoiceCollection phase={invoicePhase} invoices={invoices} cursor={invoiceCursor} loadingMore={loadingMoreInvoices} detailLoading={detailLoading} onOpen={(id) => showInvoices(id)} onRetry={() => { void loadInvoices() }} onMore={() => { if (invoiceCursor) void loadInvoices(invoiceCursor) }} />
                : section === 'publications' ? <RepositoryPublicationCollection phase={publicationPhase} publications={publications} cursor={publicationCursor} loadingMore={loadingMorePublications} detailLoading={detailLoading} loadError={publicationListError} onOpen={(id) => showPublications(id)} onRetry={() => { void loadPublications() }} onMore={() => { if (publicationCursor) void loadPublications(publicationCursor) }} />
                  : <><DocumentCollection phase={phase} documents={documents} cursor={nextCursor} loadingMore={loadingMore} detailLoading={detailLoading} onOpen={(id) => showDocuments(id)} onRetry={() => { void loadDocuments() }} onMore={() => { if (nextCursor) void loadDocuments(nextCursor) }} />
                    <RepositoryPublicationCollection phase={publicationPhase} publications={publications} cursor={publicationCursor} loadingMore={loadingMorePublications} detailLoading={detailLoading} loadError={publicationListError} onOpen={(id) => showPublications(id)} onRetry={() => { void loadPublications() }} onMore={() => { if (publicationCursor) void loadPublications(publicationCursor) }} /></>}
      </main>
    </div>
  )
}

function InvoiceCollection({ phase, invoices, cursor, loadingMore, detailLoading, onOpen, onRetry, onMore }: { phase: Phase; invoices: PortalInvoice[]; cursor: string | null; loadingMore: boolean; detailLoading: boolean; onOpen: (id: string) => void; onRetry: () => void; onMore: () => void }) {
  return <section className="content-section portal-workspace" aria-labelledby="portal-invoices-heading">
    <div className="section-heading"><div><h2 id="portal-invoices-heading">{translate('portal.invoices')}</h2><p>{translate('portal.invoicesDescription')}</p></div></div>
    {phase === 'loading' && <p role="status">{translate('portal.loadingInvoices')}</p>}
    {phase === 'error' && <div role="alert"><p>{translate('portal.invoiceLoadFailed')}</p><button className="secondary-button" type="button" onClick={onRetry}>{translate('portal.tryAgain')}</button></div>}
    {phase === 'ready' && invoices.length === 0 && <div className="empty-state"><FileText size={24} aria-hidden="true" /><p>{translate('portal.noInvoices')}</p></div>}
    {phase === 'ready' && invoices.length > 0 && <ul className="portal-document-list">{invoices.map((invoice) => <li key={invoice.id}><button type="button" disabled={detailLoading} onClick={() => onOpen(invoice.id)}><span><strong>{invoice.number}</strong><small>{invoice.currency} {invoice.total} · {translate('accounting.dueDate')} {new Date(`${invoice.due_date}T00:00:00`).toLocaleDateString()}</small></span><span className="visibility-label client-visible">{portalInvoiceState(invoice.lifecycle_state ?? 'issued')}</span></button></li>)}</ul>}
    {phase === 'ready' && cursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={onMore}>{loadingMore ? translate('portal.loadingInvoices') : translate('portal.loadMoreInvoices')}</button></div>}
  </section>
}

function DocumentCollection({ phase, documents, cursor, loadingMore, detailLoading, onOpen, onRetry, onMore }: { phase: Phase; documents: PortalDocument[]; cursor: string | null; loadingMore: boolean; detailLoading: boolean; onOpen: (id: string) => void; onRetry: () => void; onMore: () => void }) {
  return <section className="content-section portal-workspace" aria-labelledby="portal-documents-heading">
    <div className="section-heading"><div><h2 id="portal-documents-heading">{translate('portal.documents')}</h2><p>{translate('portal.documentsDescription')}</p></div></div>
    {phase === 'loading' && <p role="status">{translate('portal.loadingDocuments')}</p>}
    {phase === 'error' && <div role="alert"><p>{translate('portal.documentsLoadFailed')}</p><button className="secondary-button" type="button" onClick={onRetry}>{translate('portal.tryAgain')}</button></div>}
    {phase === 'ready' && documents.length === 0 && <div className="empty-state"><FileText size={24} aria-hidden="true" /><p>{translate('portal.noDocuments')}</p></div>}
    {phase === 'ready' && documents.length > 0 && <ul className="portal-document-list">{documents.map((document) => <li key={document.id}><button type="button" disabled={detailLoading} onClick={() => onOpen(document.id)}><span><strong>{document.title}</strong><small>{document.category} · {translate('portal.publishedOn', { date: new Date(document.published_at).toLocaleDateString() })}</small></span></button></li>)}</ul>}
    {phase === 'ready' && cursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={onMore}>{loadingMore ? translate('portal.loadingMoreDocuments') : translate('portal.loadMoreDocuments')}</button></div>}
  </section>
}

function RepositoryPublicationCollection({ phase, publications, cursor, loadingMore, detailLoading, loadError, onOpen, onRetry, onMore }: { phase: Phase; publications: PortalRepositoryPublication[]; cursor: string | null; loadingMore: boolean; detailLoading: boolean; loadError: string | null; onOpen: (id: string) => void; onRetry: () => void; onMore: () => void }) {
  return <section className="content-section portal-workspace" aria-labelledby="portal-publications-heading">
    <div className="section-heading"><div><h2 id="portal-publications-heading">{translate('portal.repositoryPublications')}</h2><p>{translate('portal.repositoryPublicationsDescription')}</p></div></div>
    {phase === 'loading' && <p role="status">{translate('portal.loadingPublications')}</p>}
    {phase === 'error' && <div role="alert"><p>{translate('portal.publicationsLoadFailed')}</p><button className="secondary-button" type="button" onClick={onRetry}>{translate('portal.tryAgain')}</button></div>}
    {phase === 'ready' && loadError && <p role="alert">{loadError}</p>}
    {phase === 'ready' && publications.length === 0 && <div className="empty-state"><FileText size={24} aria-hidden="true" /><p>{translate('portal.noPublications')}</p></div>}
    {phase === 'ready' && publications.length > 0 && <ul className="portal-document-list">{publications.map((publication) => <li key={publication.id}><button type="button" disabled={detailLoading} onClick={() => onOpen(publication.id)}><span><strong>{publication.title}</strong><small>{translate('portal.publishedOn', { date: new Date(publication.created_at).toLocaleDateString() })}</small></span></button></li>)}</ul>}
    {phase === 'ready' && cursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={onMore}>{loadingMore ? translate('portal.loadingMorePublications') : translate('portal.loadMorePublications')}</button></div>}
  </section>
}

function InvoiceDetail({ invoice, onBack }: { invoice: PortalInvoice; onBack: () => void }) {
  return <article className="content-section portal-document-detail">
    <div className="portal-document-actions"><button className="secondary-button" type="button" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />{translate('portal.allInvoices')}</button></div>
    <header><h2>{invoice.number}</h2><p>{invoice.reference || translate('portal.invoiceReferenceFallback')}</p></header>
    <dl className="inventory-provenance"><div><dt>{translate('accounting.invoiceDate')}</dt><dd>{new Date(`${invoice.invoice_date}T00:00:00`).toLocaleDateString()}</dd></div><div><dt>{translate('accounting.dueDate')}</dt><dd>{new Date(`${invoice.due_date}T00:00:00`).toLocaleDateString()}</dd></div><div><dt>{translate('accounting.lifecycle')}</dt><dd>{portalInvoiceState(invoice.lifecycle_state ?? 'issued')}</dd></div><div><dt>{translate('accounting.total')}</dt><dd><strong>{invoice.currency} {invoice.total}</strong></dd></div><div><dt>{translate('accounting.paid')}</dt><dd>{invoice.currency} {invoice.paid_amount ?? '0.00'}</dd></div><div><dt>{translate('accounting.balance')}</dt><dd>{invoice.currency} {invoice.balance_amount ?? invoice.total}</dd></div></dl>
    {invoice.notes && <p>{invoice.notes}</p>}
    {invoice.bill_to && <section aria-labelledby="portal-invoice-bill-to"><h3 id="portal-invoice-bill-to">{translate('accounting.billTo')}</h3><InvoiceBillTo identity={invoice.bill_to} /></section>}
    <section aria-labelledby="portal-invoice-lines"><h3 id="portal-invoice-lines">{translate('accounting.lines')}</h3><ul className="inventory-list">{invoice.lines.map((line) => <li key={line.id}><div><strong>{line.description}</strong><span>{line.quantity}{line.unit ? ` ${line.unit}` : ''} × {line.currency} {line.unit_amount}</span></div><strong>{line.currency} {line.total}</strong></li>)}</ul></section>
    <div className="form-actions"><a className="secondary-button" href={portalClient.invoicePdfUrl(invoice.id)}><Download size={15} aria-hidden="true" />{translate('accounting.downloadPdf')}</a><a className="secondary-button" href={portalClient.invoiceCsvUrl(invoice.id)}><Download size={15} aria-hidden="true" />{translate('accounting.downloadCsv')}</a></div>
  </article>
}

function DocumentDetail({ document, onBack }: { document: PortalDocumentDetail; onBack: () => void }) {
  return <article className="content-section portal-document-detail">
    <div className="portal-document-actions"><button className="secondary-button" type="button" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />{translate('portal.allDocuments')}</button></div>
    <header><h2>{document.title}</h2></header>
    {document.lifecycle_state === 'review_due' && <p className="portal-review-note">{translate('portal.reviewDue')}</p>}
    <SanitizedMarkdown html={document.sanitized_html} />
    {document.artifacts.length > 0 && <section aria-labelledby="portal-downloads"><h3 id="portal-downloads">{translate('portal.files')}</h3><ul className="portal-download-list">{document.artifacts.map((artifact) => <li key={artifact.id}><a href={portalClient.artifactUrl(document.id, artifact.id)}><Download size={15} aria-hidden="true" />{artifact.filename}</a><span>{Math.max(1, Math.ceil(artifact.size / 1024))} KB</span></li>)}</ul></section>}
  </article>
}

function RepositoryPublicationDetail({ publication, onBack }: { publication: PortalRepositoryPublicationDetail; onBack: () => void }) {
  return <article className="content-section portal-document-detail">
    <div className="portal-document-actions"><button className="secondary-button" type="button" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" />{translate('portal.allPublications')}</button></div>
    <header><h2>{publication.title}</h2></header>
    <SanitizedMarkdown html={publication.rendered_html} />
    <section aria-labelledby="portal-publication-downloads"><h3 id="portal-publication-downloads">{translate('portal.files')}</h3><ul className="portal-download-list">
      <li><a href={portalClient.repositoryPublicationPdfUrl(publication.id)}><Download size={15} aria-hidden="true" />{translate('portal.downloadPublicationPdf')}</a></li>
      {publication.attachments.map((attachment) => <li key={attachment.id}><a href={portalClient.repositoryPublicationAttachmentUrl(publication.id, attachment.id)}><Download size={15} aria-hidden="true" />{attachment.filename}</a><span>{Math.max(1, Math.ceil(attachment.size / 1024))} KB</span></li>)}
    </ul></section>
  </article>
}

function portalInvoiceState(value: string) {
  return translate(`accounting.lifecycle.${value}` as MessageId)
}
