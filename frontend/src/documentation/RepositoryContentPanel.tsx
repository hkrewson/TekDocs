import { useEffect, useMemo, useRef, useState } from 'react'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import { RepositoryPublicationHistory } from './RepositoryPublicationHistory'
import {
  browserRepositoryClient, RepositoryConflictError,
  type RepositoryAttachmentStatus, type RepositoryClient, type RepositoryConflict, type RepositoryListing, type RepositorySource,
} from './repositoryApi'

type Draft = {
  id: string
  kind: 'document' | 'fragment'
  title: string
  markdown: string
  path: string
  metadataText: string
}

function draftFromSource(source: RepositorySource): Draft {
  return { id: source.content_id, kind: source.kind, title: source.title, markdown: source.markdown, path: source.path, metadataText: '{}' }
}

export function RepositoryContentPanel({ organizationId, onClose, client = browserRepositoryClient }: {
  organizationId?: string
  onClose: () => void
  client?: RepositoryClient
}) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [listing, setListing] = useState<RepositoryListing | null>(null)
  const [query, setQuery] = useState('')
  const [reload, setReload] = useState(0)
  const [source, setSource] = useState<RepositorySource | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [attachments, setAttachments] = useState<RepositoryAttachmentStatus[]>([])
  const [attachmentPage, setAttachmentPage] = useState(1)
  const [attachmentMore, setAttachmentMore] = useState(false)
  const [attachmentReload, setAttachmentReload] = useState(0)
  const [attachmentError, setAttachmentError] = useState('')
  const [exporting, setExporting] = useState(false)
  const [bundleExporting, setBundleExporting] = useState(false)
  const [htmlExporting, setHtmlExporting] = useState(false)
  const [pdfExporting, setPdfExporting] = useState(false)
  const [docxExporting, setDocxExporting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [conflict, setConflict] = useState<RepositoryConflict | null>(null)
  const sourceRef = useRef(source)
  const dirty = useMemo(() => draft !== null && (
    source === null || draft.title !== source.title || draft.markdown !== source.markdown
    || draft.path !== source.path || draft.metadataText !== '{}'
  ), [draft, source])
  const canDownloadSaved = source?.kind === 'document' && !!source.accepted_commit
    && source.accepted_commit === source.indexed_commit
  const attempt = useUnsavedChanges(dirty, busy, () => { setDraft(null); setSource(null); setConflict(null) }, draft !== null)

  useEffect(() => { headingRef.current?.focus() }, [])
  useEffect(() => { sourceRef.current = source }, [source])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void client.list(organizationId, query, controller.signal)
        .then((result) => { if (!controller.signal.aborted) { setListing(result); setLoading(false) } })
        .catch(() => { if (!controller.signal.aborted) { setError(translate('repository.loadFailed')); setLoading(false) } })
    }, 150)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, organizationId, query, reload])

  useEffect(() => {
    if (source?.kind !== 'document' || !source.accepted_commit || !canDownloadSaved) {
      return
    }
    const controller = new AbortController()
    const contentId = source.content_id
    void client.listAttachments(contentId, organizationId, attachmentPage, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setAttachments((current) => attachmentPage === 1 ? result.results : [...current, ...result.results])
        setAttachmentMore(result.has_more)
        setAttachmentError('')
      })
      .catch(() => { if (!controller.signal.aborted) setAttachmentError(translate('repository.attachmentListFailed')) })
    return () => controller.abort()
  }, [client, organizationId, source, attachmentPage, attachmentReload, canDownloadSaved])

  function open(id: string) {
    attempt(() => {
      setAttachmentPage(1); setAttachments([])
      setError(''); setMessage(''); setConflict(null); setBusy(true)
      void client.source(id, organizationId)
        .then((result) => { setSource(result); setDraft(draftFromSource(result)) })
        .catch(() => setError(translate('repository.sourceFailed')))
        .finally(() => setBusy(false))
    })
  }

  function create() {
    attempt(() => {
      setAttachmentPage(1); setAttachments([])
      setSource(null)
      setDraft({ id: crypto.randomUUID(), kind: 'document', title: '', markdown: '', path: '', metadataText: '{}' })
      setError(''); setMessage(''); setConflict(null)
    })
  }

  async function save() {
    if (!draft || busy) return
    let metadata: Record<string, unknown>
    try {
      const parsed: unknown = JSON.parse(draft.metadataText)
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error()
      metadata = parsed as Record<string, unknown>
    } catch {
      setError(translate('repository.metadataInvalid'))
      return
    }
    setBusy(true); setError(''); setMessage(''); setConflict(null)
    try {
      const saved = await client.save({
        operation: source ? (draft.path !== source.path ? 'move' : 'update') : 'create',
        content_id: draft.id,
        base_commit: source?.accepted_commit ?? listing?.accepted_commit ?? null,
        base_blob: source?.source_blob ?? null,
        kind: draft.kind,
        path: draft.path || null,
        title: source === null || draft.title !== source.title ? draft.title : undefined,
        markdown: source === null || draft.markdown !== source.markdown ? draft.markdown : undefined,
        metadata_patch: metadata,
      }, organizationId)
      setSource(saved); setDraft(draftFromSource(saved)); setReload((value) => value + 1)
      setMessage(saved.accepted_commit === saved.indexed_commit ? translate('repository.saved') : translate('repository.indexPending'))
    } catch (caught) {
      if (caught instanceof RepositoryConflictError) setConflict(caught.conflict)
      else setError(caught instanceof Error ? caught.message : translate('repository.saveFailed'))
    } finally { setBusy(false) }
  }

  async function uploadAttachment(file: File) {
    if (!source || source.kind !== 'document' || !source.accepted_commit
      || source.accepted_commit !== source.indexed_commit || busy) return
    const selectedId = source.content_id
    setBusy(true); setUploading(true); setError(''); setMessage('')
    try {
      const attachment = await client.uploadAttachment(selectedId, file, organizationId)
      if (sourceRef.current?.content_id !== selectedId) return
      const label = attachment.filename.replaceAll('\\', '\\\\').replaceAll('[', '\\[').replaceAll(']', '\\]')
      const link = `[${label}](tekdocs://attachment/${attachment.id})`
      setDraft((current) => current?.id === selectedId
        ? { ...current, markdown: `${current.markdown}${current.markdown && !current.markdown.endsWith('\n') ? '\n\n' : ''}${link}\n` }
        : current)
      setMessage(translate('repository.attachmentLinked', { filename: attachment.filename }))
      setAttachmentPage(1); setAttachmentReload((value) => value + 1)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('repository.attachmentFailed'))
    } finally { setUploading(false); setBusy(false) }
  }

  async function archiveAttachment(attachment: RepositoryAttachmentStatus) {
    if (!source || !attachment.can_archive || draft?.markdown.includes(attachment.id) || busy) return
    const contentId = source.content_id
    setBusy(true); setAttachmentError('')
    try {
      await client.archiveAttachment(contentId, attachment.id, organizationId)
      if (sourceRef.current?.content_id !== contentId) return
      setAttachments((current) => current.filter((item) => item.id !== attachment.id))
      setAttachmentPage(1); setAttachmentReload((value) => value + 1)
      setMessage(translate('repository.attachmentArchived', { filename: attachment.filename }))
    } catch {
      setAttachmentError(translate('repository.attachmentArchiveFailed'))
    } finally { setBusy(false) }
  }

  async function rebase() {
    if (!draft) return
    setBusy(true)
    try {
      if (source) {
        const latest = await client.source(draft.id, organizationId)
        setSource(latest)
      } else {
        setListing(await client.list(organizationId, query))
      }
      setConflict(null)
      setMessage(translate('repository.reviewRebase'))
    } catch { setError(translate('repository.sourceFailed')) }
    finally { setBusy(false) }
  }

  function downloadLoadedSource() {
    if (!source?.accepted_commit) return
    const name = source.path.split('/').at(-1) || `${source.content_id}.md`
    const url = URL.createObjectURL(new Blob([source.source], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = name
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  async function downloadSnapshot() {
    if (exporting) return
    setExporting(true); setError('')
    try {
      const result = await client.exportSources(organizationId)
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a')
      link.href = url
      link.download = result.name
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      setError(translate('repository.snapshotFailed'))
    } finally { setExporting(false) }
  }

  async function downloadEditableBundle() {
    if (bundleExporting) return
    setBundleExporting(true); setError('')
    try {
      const result = await client.exportEditableBundle(organizationId)
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a')
      link.href = url
      link.download = result.name
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      setError(translate('repository.bundleFailed'))
    } finally { setBundleExporting(false) }
  }

  async function downloadHtml() {
    if (htmlExporting || pdfExporting || docxExporting || busy || source?.kind !== 'document' || !source.accepted_commit
      || source.accepted_commit !== source.indexed_commit) return
    const selectedId = source.content_id
    const selectedCommit = source.accepted_commit
    setHtmlExporting(true); setError('')
    try {
      const result = await client.exportHtml(selectedId, organizationId)
      if (result.commit !== selectedCommit || sourceRef.current?.content_id !== selectedId
        || sourceRef.current.accepted_commit !== selectedCommit) {
        setError(translate('repository.htmlRevisionChanged'))
        return
      }
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a')
      link.href = url
      link.download = result.name
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      setError(translate('repository.htmlFailed'))
    } finally { setHtmlExporting(false) }
  }

  async function downloadPdf() {
    if (pdfExporting || htmlExporting || docxExporting || busy || source?.kind !== 'document' || !source.accepted_commit
      || source.accepted_commit !== source.indexed_commit) return
    const selectedId = source.content_id
    const selectedCommit = source.accepted_commit
    setPdfExporting(true); setError('')
    try {
      const result = await client.exportPdf(selectedId, organizationId)
      if (result.commit !== selectedCommit || sourceRef.current?.content_id !== selectedId
        || sourceRef.current.accepted_commit !== selectedCommit) {
        setError(translate('repository.pdfRevisionChanged'))
        return
      }
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a')
      link.href = url
      link.download = result.name
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      setError(translate('repository.pdfFailed'))
    } finally { setPdfExporting(false) }
  }

  async function downloadDocx() {
    if (docxExporting || htmlExporting || pdfExporting || busy || source?.kind !== 'document' || !source.accepted_commit
      || source.accepted_commit !== source.indexed_commit) return
    const selectedId = source.content_id
    const selectedCommit = source.accepted_commit
    setDocxExporting(true); setError('')
    try {
      const result = await client.exportDocx(selectedId, organizationId)
      if (result.commit !== selectedCommit || sourceRef.current?.content_id !== selectedId
        || sourceRef.current.accepted_commit !== selectedCommit) {
        setError(translate('repository.docxRevisionChanged'))
        return
      }
      const url = URL.createObjectURL(result.content)
      const link = document.createElement('a')
      link.href = url
      link.download = result.name
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      setError(translate('repository.docxFailed'))
    } finally { setDocxExporting(false) }
  }

  return <section className="repository-authoring">
    <header className="page-header"><div><h1 ref={headingRef} tabIndex={-1}>{translate('repository.heading')}</h1><p>{translate('repository.description')}</p></div><div className="page-actions"><button type="button" className="secondary-button" onClick={() => attempt(onClose)}>{translate('repository.return')}</button><button type="button" className="secondary-button" onClick={() => { void downloadSnapshot() }} disabled={!listing?.accepted_commit || listing.accepted_commit !== listing.indexed_commit || exporting}>{exporting ? translate('repository.snapshotPreparing') : translate('repository.snapshotDownload')}</button><button type="button" className="secondary-button" onClick={() => { void downloadEditableBundle() }} disabled={!listing?.accepted_commit || listing.accepted_commit !== listing.indexed_commit || bundleExporting}>{bundleExporting ? translate('repository.bundlePreparing') : translate('repository.bundleDownload')}</button><button type="button" className="primary-button" onClick={create} disabled={!listing || loading}>{translate('repository.new')}</button></div></header>
    <p className="form-message">{translate('repository.snapshotNotice')}</p>
    <p className="form-message">{translate('repository.bundleNotice')}</p>
    {error && <p role="alert" className="form-message error">{error}</p>}
    {message && <p role="status" className="form-message success">{message}</p>}
    {listing && listing.accepted_commit !== listing.indexed_commit && <p role="status" className="form-message">{translate('repository.indexPending')}</p>}
    <div className="repository-authoring-grid">
      <section aria-label={translate('repository.files')}>
        <label>{translate('repository.search')}<input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setLoading(true) }} /></label>
        {loading && <p role="status">{translate('repository.loading')}</p>}
        {!loading && listing?.results.length === 0 && <p className="empty-state">{translate('repository.empty')}</p>}
        {!loading && listing && <ul className="document-title-list">{listing.results.map((item) => <li key={item.id}><button type="button" aria-current={draft?.id === item.id ? 'true' : undefined} onClick={() => open(item.id)}><span><strong>{item.title}</strong><small>{item.kind === 'fragment' ? translate('repository.fragment') : translate('repository.document')} · {item.path}</small></span></button></li>)}</ul>}
        {listing?.has_more && <p>{translate('repository.moreResults')}</p>}
      </section>
      <section aria-label={translate('repository.editor')}>
        {!draft && <p className="empty-state">{translate('repository.choose')}</p>}
        {draft && <><div className="repository-editor-fields">
          {!source && <label>{translate('repository.kind')}<select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as Draft['kind'] })}><option value="document">{translate('repository.document')}</option><option value="fragment">{translate('repository.fragment')}</option></select></label>}
          <label>{translate('repository.title')}<input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
          <label>{translate('repository.path')}<input value={draft.path} placeholder={source ? undefined : translate('repository.generatedPath')} onChange={(event) => setDraft({ ...draft, path: event.target.value })} /></label>
          <label>{translate('repository.markdown')}<textarea rows={16} value={draft.markdown} onChange={(event) => setDraft({ ...draft, markdown: event.target.value })} /></label>
          {source?.kind === 'document' && <><label>{translate('repository.attachFile')}<input type="file" disabled={!canDownloadSaved || busy} onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; if (file) void uploadAttachment(file) }} /></label><p className="field-hint">{translate('repository.attachmentNotice')}</p>{uploading && <p role="status">{translate('repository.attachmentUploading')}</p>}
            {canDownloadSaved && <section aria-label={translate('repository.attachmentFiles')}><h3>{translate('repository.attachmentFiles')}</h3>{attachmentError && <p role="alert">{attachmentError}</p>}
              {attachments.length === 0 && !attachmentError && <p>{translate('repository.attachmentEmpty')}</p>}
              <ul>{attachments.map((attachment) => <li key={attachment.id}>{attachment.filename} · {attachment.size} B · {attachment.linked_current ? translate('repository.attachmentLinkedStatus') : translate('repository.attachmentRetainedStatus')}{attachment.can_archive && <button type="button" className="secondary-button" disabled={busy || !!draft?.markdown.includes(attachment.id)} onClick={() => { void archiveAttachment(attachment) }}>{translate('repository.attachmentArchive', { filename: attachment.filename })}</button>}</li>)}</ul>
              {attachmentMore && <button type="button" className="secondary-button" onClick={() => setAttachmentPage((page) => page + 1)}>{translate('repository.attachmentMore')}</button>}
            </section>}
          </>}
          <details><summary>{translate('repository.metadata')}</summary><p>{translate('repository.metadataHelp')}</p><textarea rows={6} aria-label={translate('repository.metadataPatch')} value={draft.metadataText} onChange={(event) => setDraft({ ...draft, metadataText: event.target.value })} /><p>{translate('repository.sourceNotice')}</p><pre>{source?.source ?? ''}</pre></details>
        </div>
        {conflict && <div role="alert" className="form-message error"><p>{translate('repository.conflict')}</p>{(conflict.base || conflict.current || conflict.proposed) && <details open><summary>{translate('repository.compare')}</summary><h3>{translate('repository.base')}</h3><pre>{conflict.base}</pre><h3>{translate('repository.current')}</h3><pre>{conflict.current}</pre><h3>{translate('repository.yours')}</h3><pre>{conflict.proposed}</pre></details>}<button type="button" className="secondary-button" onClick={() => { void rebase() }} disabled={busy}>{translate('repository.rebase')}</button></div>}
        {source?.accepted_commit && <p className="form-message">{translate('repository.loadedRevision', { commit: source.accepted_commit.slice(0, 12) })}</p>}
        {canDownloadSaved && <p className="form-message">{translate('repository.htmlNotice')}</p>}
        {canDownloadSaved && <p className="form-message">{translate('repository.pdfNotice')}</p>}
        {canDownloadSaved && <p className="form-message">{translate('repository.docxNotice')}</p>}
        <div className="form-actions">
          <button type="button" className="primary-button" onClick={() => { void save() }} disabled={busy || !draft.title.trim() || (source !== null && !dirty)}>{busy ? translate('repository.saving') : translate('repository.save')}</button>
          {source?.accepted_commit && <button type="button" className="secondary-button" onClick={downloadLoadedSource}>{translate('repository.downloadLoaded')}</button>}
          {canDownloadSaved && <button type="button" className="secondary-button" onClick={() => { void downloadHtml() }} disabled={busy || htmlExporting || pdfExporting || docxExporting}>{htmlExporting ? translate('repository.htmlPreparing') : translate('repository.htmlDownload')}</button>}
          {canDownloadSaved && <button type="button" className="secondary-button" onClick={() => { void downloadPdf() }} disabled={busy || htmlExporting || pdfExporting || docxExporting}>{pdfExporting ? translate('repository.pdfPreparing') : translate('repository.pdfDownload')}</button>}
          {canDownloadSaved && <button type="button" className="secondary-button" onClick={() => { void downloadDocx() }} disabled={busy || htmlExporting || pdfExporting || docxExporting}>{docxExporting ? translate('repository.docxPreparing') : translate('repository.docxDownload')}</button>}
          <button type="button" className="secondary-button" onClick={() => attempt(() => { setDraft(null); setSource(null); setConflict(null) })}>{translate('common.close')}</button>
        </div></>}
        {source?.kind === 'document' && source.accepted_commit && <RepositoryPublicationHistory key={`${organizationId ?? 'msp'}:${source.content_id}`} contentId={source.content_id} organizationId={organizationId} client={client} />}
      </section>
    </div>
  </section>
}
