import { ArrowLeft, Download, FileText, LogOut } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import type { AuthenticatedContext } from '../auth/api'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import { NotificationInbox } from '../notifications/NotificationInbox'
import { browserPortalNotificationsClient } from '../notifications/api'
import type { NotificationsClient, NotificationTarget } from '../notifications/api'
import { portalClient, type PortalDocument, type PortalDocumentDetail } from './api'

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

  async function openDocument(document: PortalDocument) {
    setDetailLoading(true)
    setError(null)
    try { setSelected(await portalClient.getDocument(document.id)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Published documentation could not be loaded.') }
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
      <main className="client-portal-main" aria-busy={phase === 'loading' || detailLoading || loadingMore}>
        {signOutError && <div className="form-error" role="alert">{signOutError}</div>}
        <header className="page-header"><div><h1>{organization?.name ?? 'Client portal'}</h1><p>Documentation explicitly approved for your organization.</p></div></header>
        {error && <div className="form-error" role="alert">{error}</div>}
        {selected ? <article className="content-section portal-document-detail">
          <div className="portal-document-actions">
            <button className="secondary-button" type="button" onClick={() => setSelected(null)}><ArrowLeft size={16} aria-hidden="true" />All documents</button>
            <span className="visibility-label client-visible">Client visible</span>
          </div>
          <header><p className="eyebrow">STATIC {selected.category}</p><h2>{selected.title}</h2><p>{selected.reason}</p></header>
          {selected.lifecycle_state === 'review_due' && <p className="portal-review-note">This publication is still available, but its scheduled review is due.</p>}
          <SanitizedMarkdown html={selected.sanitized_html} />
          {selected.artifacts.length > 0 && <section aria-labelledby="portal-downloads"><h3 id="portal-downloads">Downloads</h3><ul className="portal-download-list">{selected.artifacts.map((artifact) => <li key={artifact.id}><a href={portalClient.artifactUrl(selected.id, artifact.id)}><Download size={15} aria-hidden="true" />{artifact.filename}</a><span>{Math.max(1, Math.ceil(artifact.size / 1024))} KB</span></li>)}</ul></section>}
        </article> : <section className="content-section" aria-labelledby="portal-documents-heading">
          <div className="section-heading"><div><h2 id="portal-documents-heading">Published documentation</h2><p>Only approved, current client-visible STATIC publications appear here.</p></div><span>{documents.length}</span></div>
          {phase === 'loading' && <p role="status">Loading published documentation…</p>}
          {phase === 'error' && <button className="secondary-button" type="button" onClick={() => { void loadDocuments() }}>Try again</button>}
          {phase === 'ready' && documents.length === 0 && <div className="empty-state"><FileText size={24} aria-hidden="true" /><p>No documentation has been published to your organization.</p></div>}
          {phase === 'ready' && documents.length > 0 && <ul className="portal-document-list">{documents.map((document) => <li key={document.id}><button type="button" disabled={detailLoading} onClick={() => { void openDocument(document) }}><span><strong>{document.title}</strong><small>{document.category} · Published {new Date(document.published_at).toLocaleDateString()}</small></span><span className="visibility-label client-visible">Client visible</span></button></li>)}</ul>}
          {phase === 'ready' && nextCursor && <div className="portal-history-action"><button className="secondary-button" type="button" disabled={loadingMore} onClick={() => { void loadDocuments(nextCursor) }}>{loadingMore ? 'Loading…' : 'Load more documents'}</button></div>}
        </section>}
      </main>
    </div>
  )
}
