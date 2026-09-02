import { ArrowLeft, Download, FileText, LogOut } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
import { useCallback, useEffect, useState } from 'react'
import type { AuthenticatedContext } from '../auth/api'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import { NotificationInbox } from '../notifications/NotificationInbox'
import { browserPortalNotificationsClient } from '../notifications/api'
import type { NotificationsClient, NotificationTarget } from '../notifications/api'
import { portalClient, type PortalDocument, type PortalDocumentDetail, type PortalDocumentationMap, type PortalInvoice } from './api'

export function ClientPortal({ context, onSignOut, signingOut, signOutError, notificationsClient = browserPortalNotificationsClient }: {
  context: AuthenticatedContext
  onSignOut: () => Promise<void>
  signingOut: boolean
  signOutError: string | null
  notificationsClient?: NotificationsClient
}) {
  const organization = context.organization
  const [documents, setDocuments] = useState<PortalDocument[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<PortalDocumentDetail | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [detailLoading, setDetailLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [invoices, setInvoices] = useState<PortalInvoice[]>([])
  const [selectedInvoice, setSelectedInvoice] = useState<PortalInvoice | null>(null)
  const [invoicePhase, setInvoicePhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [invoiceCursor, setInvoiceCursor] = useState<string | null>(null)
  const [loadingMoreInvoices, setLoadingMoreInvoices] = useState(false)
  const [maps, setMaps] = useState<PortalDocumentationMap[]>([])
  const [mapPhase, setMapPhase] = useState<'loading' | 'ready' | 'error'>('loading')

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
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Published documentation could not be loaded.')
      if (!cursor) setPhase('error')
    } finally {
      setLoadingMore(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    void portalClient.listDocuments().then((result) => {
      if (!active) return
      setDocuments(result.results)
      setNextCursor(result.next_cursor ?? null)
      setPhase('ready')
    }).catch((reason: unknown) => {
      if (!active) return
      setError(reason instanceof Error ? reason.message : 'Published documentation could not be loaded.')
      setPhase('error')
    })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    void portalClient.listDocumentationMaps().then((result) => {
      if (!active) return
      const records = Array.isArray(result.results)
        ? result.results.filter((item) => item && typeof item.baseline_id === 'string' && Array.isArray(item.contents))
        : []
      setMaps(records); setMapPhase('ready')
    }).catch(() => { if (active) setMapPhase('error') })
    return () => { active = false }
  }, [])

  const loadInvoices = useCallback(async (cursor?: string) => {
    if (cursor) setLoadingMoreInvoices(true)
    try {
      const result = await portalClient.listInvoices(cursor)
      setInvoices((current) => cursor ? [...current, ...result.results] : result.results)
      setInvoiceCursor(result.next_cursor)
      setInvoicePhase('ready')
    } catch { if (!cursor) setInvoicePhase('error') }
    finally { setLoadingMoreInvoices(false) }
  }, [])

  useEffect(() => {
    let active = true
    void portalClient.listInvoices().then((result) => {
      if (!active) return
      setInvoices(result.results)
      setInvoiceCursor(result.next_cursor)
      setInvoicePhase('ready')
    }).catch(() => { if (active) setInvoicePhase('error') })
    return () => { active = false }
  }, [])

  async function openDocument(document: PortalDocument) {
    setDetailLoading(true)
    setError(null)
    try { setSelectedInvoice(null); setSelected(await portalClient.getDocument(document.id)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Published documentation could not be loaded.') }
    finally { setDetailLoading(false) }
  }

  async function openInvoice(invoice: PortalInvoice) {
    setDetailLoading(true)
    setError(null)
    try { setSelected(null); setSelectedInvoice(await portalClient.getInvoice(invoice.id)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : translate('portal.invoiceLoadFailed')) }
    finally { setDetailLoading(false) }
  }

  async function openNotificationTarget(target: NotificationTarget) {
    if (target.kind === 'portal_documents') {
      setSelected(null)
      return
    }
    if (target.kind === 'portal_document' && target.publication_id) {
      setDetailLoading(true)
      setError(null)
      try { setSelected(await portalClient.getDocument(target.publication_id)) }
      catch (reason) { setError(reason instanceof Error ? reason.message : 'Published documentation could not be loaded.') }
      finally { setDetailLoading(false) }
    }
  }

  return (
    <div className="client-portal-shell">
      <header className="client-portal-header">
        <div className="client-portal-brand"><span className="brand-mark" aria-hidden="true">T</span><span>TekDocs</span></div>
        <div className="client-portal-account">
          <span>{context.user.display_name}</span>
          <NotificationInbox client={notificationsClient} onOpen={openNotificationTarget} />
          <button className="secondary-button" type="button" disabled={signingOut} onClick={() => { void onSignOut() }}>
            <LogOut size={16} aria-hidden="true" />{signingOut ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      </header>
      <main className="client-portal-main" aria-busy={phase === 'loading' || invoicePhase === 'loading' || mapPhase === 'loading' || detailLoading || loadingMore || loadingMoreInvoices}>
        {signOutError && <div className="form-error" role="alert">{signOutError}</div>}
        <header className="page-header"><div><h1>{organization?.name ?? 'Client portal'}</h1><p>{translate('portal.summary')}</p></div></header>
        {error && <div className="form-error" role="alert">{error}</div>}
        {selectedInvoice ? <article className="content-section portal-document-detail">
          <div className="portal-document-actions"><button className="secondary-button" type="button" onClick={() => setSelectedInvoice(null)}><ArrowLeft size={16} aria-hidden="true" />{translate('portal.allInvoices')}</button><span className="visibility-label client-visible">{translate('portal.clientVisible')}</span></div>
          <header><p className="eyebrow">{translate('portal.issuedInvoice')}</p><h2>{selectedInvoice.number}</h2><p>{selectedInvoice.reference || translate('portal.invoiceReferenceFallback')}</p></header>
          <dl className="inventory-provenance"><div><dt>{translate('accounting.invoiceDate')}</dt><dd>{new Date(`${selectedInvoice.invoice_date}T00:00:00`).toLocaleDateString()}</dd></div><div><dt>{translate('accounting.dueDate')}</dt><dd>{new Date(`${selectedInvoice.due_date}T00:00:00`).toLocaleDateString()}</dd></div><div><dt>{translate('accounting.lifecycle')}</dt><dd>{portalInvoiceState(selectedInvoice.lifecycle_state ?? 'issued')}</dd></div><div><dt>{translate('accounting.total')}</dt><dd><strong>{selectedInvoice.currency} {selectedInvoice.total}</strong></dd></div><div><dt>{translate('accounting.paid')}</dt><dd>{selectedInvoice.currency} {selectedInvoice.paid_amount ?? '0.00'}</dd></div><div><dt>{translate('accounting.balance')}</dt><dd>{selectedInvoice.currency} {selectedInvoice.balance_amount ?? selectedInvoice.total}</dd></div></dl>
          {selectedInvoice.notes && <p>{selectedInvoice.notes}</p>}
          <section aria-labelledby="portal-invoice-lines"><h3 id="portal-invoice-lines">{translate('accounting.lines')}</h3><ul className="inventory-list">{selectedInvoice.lines.map((line) => <li key={line.id}><div><strong>{line.description}</strong><span>{line.quantity} × {line.currency} {line.unit_amount}</span></div><strong>{line.currency} {line.total}</strong></li>)}</ul></section>
          <div className="form-actions"><a className="secondary-button" href={portalClient.invoicePdfUrl(selectedInvoice.id)}><Download size={15} aria-hidden="true" />{translate('accounting.downloadPdf')}</a><a className="secondary-button" href={portalClient.invoiceCsvUrl(selectedInvoice.id)}><Download size={15} aria-hidden="true" />{translate('accounting.downloadCsv')}</a></div>
        </article> : selected ? <article className="content-section portal-document-detail">
          <div className="portal-document-actions">
            <button className="secondary-button" type="button" onClick={() => setSelected(null)}><ArrowLeft size={16} aria-hidden="true" />{translate('portal.allDocuments')}</button>
            <span className="visibility-label client-visible">Client visible</span>
          </div>
          <header><p className="eyebrow">STATIC {selected.category}</p><h2>{selected.title}</h2><p>{selected.reason}</p></header>
          {selected.lifecycle_state === 'review_due' && <p className="portal-review-note">This publication is still available, but its scheduled review is due.</p>}
          <SanitizedMarkdown html={selected.sanitized_html} />
          {selected.artifacts.length > 0 && <section aria-labelledby="portal-downloads"><h3 id="portal-downloads">Downloads</h3><ul className="portal-download-list">{selected.artifacts.map((artifact) => <li key={artifact.id}><a href={portalClient.artifactUrl(selected.id, artifact.id)}><Download size={15} aria-hidden="true" />{artifact.filename}</a><span>{Math.max(1, Math.ceil(artifact.size / 1024))} KB</span></li>)}</ul></section>}
        </article> : <>
        <section className="content-section" aria-labelledby="portal-invoices-heading">
          <div className="section-heading"><div><h2 id="portal-invoices-heading">{translate('portal.invoices')}</h2><p>{translate('portal.invoicesDescription')}</p></div><span>{invoices.length}</span></div>
          {invoicePhase === 'loading' && <p role="status">{translate('portal.loadingInvoices')}</p>}
          {invoicePhase === 'error' && <p role="alert">{translate('portal.invoiceLoadFailed')}</p>}
          {invoicePhase === 'ready' && invoices.length === 0 && <div className="empty-state"><FileText size={24} aria-hidden="true" /><p>{translate('portal.noInvoices')}</p></div>}
          {invoicePhase === 'ready' && invoices.length > 0 && <ul className="portal-document-list">{invoices.map((invoice) => <li key={invoice.id}><button type="button" disabled={detailLoading} onClick={() => { void openInvoice(invoice) }}><span><strong>{invoice.number}</strong><small>{invoice.currency} {invoice.total} · {translate('accounting.dueDate')} {new Date(`${invoice.due_date}T00:00:00`).toLocaleDateString()}</small></span><span className="visibility-label client-visible">{portalInvoiceState(invoice.lifecycle_state ?? 'issued')}</span></button></li>)}</ul>}
          {invoicePhase === 'ready' && invoiceCursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMoreInvoices} onClick={() => { void loadInvoices(invoiceCursor) }}>{loadingMoreInvoices ? translate('portal.loadingInvoices') : translate('portal.loadMoreInvoices')}</button></div>}
        </section>
        <section className="content-section" aria-labelledby="portal-maps-heading">
          <div className="section-heading"><div><h2 id="portal-maps-heading">Documentation maps</h2><p>Approved runbooks and handoff packages prepared for your organization.</p></div><span>{maps.length}</span></div>
          {mapPhase === 'loading' && <p role="status">Loading documentation maps…</p>}
          {mapPhase === 'error' && <p role="alert">Documentation maps are unavailable.</p>}
          {mapPhase === 'ready' && maps.length === 0 && <div className="empty-state"><FileText size={24} aria-hidden="true" /><p>No documentation maps have been published to your organization.</p></div>}
          {mapPhase === 'ready' && maps.length > 0 && <ul className="portal-document-list">{maps.map((map) => <li key={map.id}><div className="portal-map-row"><span><strong>{map.title}</strong><small>{map.purpose || `${map.contents.length} mapped item${map.contents.length === 1 ? '' : 's'}`}</small></span><a className="secondary-button" href={portalClient.documentationMapUrl(map.baseline_id)}><Download size={15} aria-hidden="true" />Download handoff</a></div></li>)}</ul>}
        </section>
        <section className="content-section" aria-labelledby="portal-documents-heading">
          <div className="section-heading"><div><h2 id="portal-documents-heading">Published documentation</h2><p>Only approved, current client-visible STATIC publications appear here.</p></div><span>{documents.length}</span></div>
          {phase === 'loading' && <p role="status">Loading published documentation…</p>}
          {phase === 'error' && <button className="secondary-button" type="button" onClick={() => { void loadDocuments() }}>{translate('portal.tryAgain')}</button>}
          {phase === 'ready' && documents.length === 0 && <div className="empty-state"><FileText size={24} aria-hidden="true" /><p>No documentation has been published to your organization.</p></div>}
          {phase === 'ready' && documents.length > 0 && <ul className="portal-document-list">{documents.map((document) => <li key={document.id}><button type="button" disabled={detailLoading} onClick={() => { void openDocument(document) }}><span><strong>{document.title}</strong><small>{document.category} · Published {new Date(document.published_at).toLocaleDateString()}</small></span><span className="visibility-label client-visible">Client visible</span></button></li>)}</ul>}
          {phase === 'ready' && nextCursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={() => { void loadDocuments(nextCursor) }}>{loadingMore ? 'Loading…' : 'Load more documents'}</button></div>}
        </section></>}
      </main>
    </div>
  )
}

function portalInvoiceState(value: string) {
  return translate(`accounting.lifecycle.${value}` as MessageId)
}
