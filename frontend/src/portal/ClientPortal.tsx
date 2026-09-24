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
import { portalClient, type PortalDocument, type PortalDocumentDetail, type PortalInvoice } from './api'
import '../collections/collections.css'
import './portal.css'

type PortalSection = 'documents' | 'invoices'
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
  const section: PortalSection = parameters.get('section') === 'invoices' ? 'invoices' : 'documents'
  const documentId = section === 'documents' ? parameters.get('document') : null
  const invoiceId = section === 'invoices' ? parameters.get('invoice') : null
  const sections = useMemo(() => [
    { id: 'documents', label: translate('portal.documents'), href: '?section=documents' },
    { id: 'invoices', label: translate('portal.invoices'), href: '?section=invoices' },
  ], [])
  const [documents, setDocuments] = useState<PortalDocument[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<PortalDocumentDetail | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [detailLoading, setDetailLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [invoices, setInvoices] = useState<PortalInvoice[]>([])
  const [selectedInvoice, setSelectedInvoice] = useState<PortalInvoice | null>(null)
  const [invoicePhase, setInvoicePhase] = useState<Phase>('idle')
  const [invoiceCursor, setInvoiceCursor] = useState<string | null>(null)
  const [loadingMoreInvoices, setLoadingMoreInvoices] = useState(false)
  const documentsStarted = useRef(false)
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
      setError(translate(cursor ? 'portal.moreDocumentsLoadFailed' : 'portal.documentsLoadFailed'))
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
      setError(translate('portal.invoiceLoadFailed'))
      if (!cursor) setInvoicePhase('error')
    } finally {
      setLoadingMoreInvoices(false)
    }
  }, [])

  useEffect(() => {
    const shouldLoadDocuments = section === 'documents' && phase === 'idle' && !documentsStarted.current
    const shouldLoadInvoices = section === 'invoices' && invoicePhase === 'idle' && !invoicesStarted.current
    if (shouldLoadDocuments) documentsStarted.current = true
    if (shouldLoadInvoices) invoicesStarted.current = true
    void Promise.resolve().then(() => {
      if (shouldLoadDocuments) return loadDocuments()
      if (shouldLoadInvoices) return loadInvoices()
    })
  }, [invoicePhase, loadDocuments, loadInvoices, phase, section])

  useEffect(() => {
    if (!documentId) return
    let active = true
    void Promise.resolve().then(async () => {
      if (!active) return
      setDetailLoading(true)
      setError(null)
      try {
        const result = await portalClient.getDocument(documentId)
        if (active) setSelected(result)
      } catch {
        if (active) setError(translate('portal.documentUnavailable'))
      } finally {
        if (active) setDetailLoading(false)
      }
    })
    return () => { active = false }
  }, [documentId])

  useEffect(() => {
    if (!invoiceId) return
    let active = true
    void Promise.resolve().then(async () => {
      if (!active) return
      setDetailLoading(true)
      setError(null)
      try {
        const result = await portalClient.getInvoice(invoiceId)
        if (active) setSelectedInvoice(result)
      } catch {
        if (active) setError(translate('portal.invoiceUnavailable'))
      } finally {
        if (active) setDetailLoading(false)
      }
    })
    return () => { active = false }
  }, [invoiceId])

  function openNotificationTarget(target: NotificationTarget) {
    if (target.kind === 'portal_document' && target.publication_id) showDocuments(target.publication_id)
    else if (target.kind === 'portal_documents') showDocuments()
  }

  const activePhase = section === 'documents' ? phase : invoicePhase
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
      <main id="portal-main-content" className="client-portal-main" aria-busy={activePhase === 'loading' || detailLoading || loadingMore || loadingMoreInvoices}>
        {signOutError && <div className="form-error" role="alert">{signOutError}</div>}
        <header className="page-header"><div><h1>{organization?.name ?? 'Client portal'}</h1><p>{translate('portal.summary')}</p></div></header>
        <RecordSections sections={sections} current={section} />
        {error && <div className="form-error" role="alert">{error}</div>}
        {detailLoading && (documentId || invoiceId) && <section className="content-section" aria-live="polite"><p role="status">{translate(section === 'documents' ? 'portal.loadingDocument' : 'portal.loadingInvoice')}</p></section>}
        {!detailLoading && selectedInvoice?.id === invoiceId ? <InvoiceDetail invoice={selectedInvoice} onBack={() => showInvoices()} />
          : !detailLoading && selected?.id === documentId ? <DocumentDetail document={selected} onBack={() => showDocuments()} />
            : section === 'invoices' ? <InvoiceCollection phase={invoicePhase} invoices={invoices} cursor={invoiceCursor} loadingMore={loadingMoreInvoices} detailLoading={detailLoading} onOpen={(id) => showInvoices(id)} onRetry={() => { void loadInvoices() }} onMore={() => { if (invoiceCursor) void loadInvoices(invoiceCursor) }} />
              : <DocumentCollection phase={phase} documents={documents} cursor={nextCursor} loadingMore={loadingMore} detailLoading={detailLoading} onOpen={(id) => showDocuments(id)} onRetry={() => { void loadDocuments() }} onMore={() => { if (nextCursor) void loadDocuments(nextCursor) }} />}
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

function portalInvoiceState(value: string) {
  return translate(`accounting.lifecycle.${value}` as MessageId)
}
