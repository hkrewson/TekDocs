import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Archive, BookOpenText, Code2, Copy, Download, ExternalLink, FileCheck2, FileUp, Heading, History, Link2, Paperclip, Pencil, Pin, Plus, Search, Share2, ShieldCheck, Trash2, Type, Unlink, X } from 'lucide-react'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import type { WorkspaceContext, WorkspaceClient, WorkspaceOption } from '../workspaces/api'
import { browserWorkspaceClient } from '../workspaces/api'
import { browserDocumentsClient, RevisionConflictError } from './api'
import type { BlockKind, BlockRevision, BlockRevisionDetail, DocumentCategory, DocumentInput, DocumentPlacement, DocumentPublication, DocumentPublicationDetail, DocumentRecord, DocumentsClient, EntityMentionOption, PublicationAudience, PublicationRetention, ReuseImpact } from './api'

const Editor = lazy(async () => ({ default: (await import('../editor/EditorSpike')).EditorSpike }))
const categories: { value: DocumentCategory; label: string }[] = [
  { value: 'general', label: 'General' }, { value: 'policy', label: 'Policy' },
  { value: 'procedure', label: 'Procedure' }, { value: 'guide', label: 'Guide' },
  { value: 'reference', label: 'Reference' },
]
const blockKinds: { value: BlockKind; label: string; description: string }[] = [
  { value: 'rich_text', label: 'Text', description: 'Paragraphs, lists, tables, and callouts' },
  { value: 'heading', label: 'Section heading', description: 'A named section boundary' },
  { value: 'code', label: 'Code', description: 'Commands, configuration, or source' },
  { value: 'url', label: 'URL', description: 'A described external reference' },
  { value: 'document_link', label: 'Document link', description: 'A stable link to another document' },
  { value: 'entity_reference', label: 'TekDocs record', description: 'A person, asset, site, network, or other record' },
  { value: 'file_reference', label: 'File', description: 'A managed attachment reference' },
]

function BlockKindIcon({ kind }: { kind: BlockKind }) {
  if (kind === 'heading') return <Heading size={15} />
  if (kind === 'code') return <Code2 size={15} />
  if (kind === 'rich_text') return <Type size={15} />
  return <Link2 size={15} />
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Documentation could not be loaded.'
}

export function Documentation({ workspace, client = browserDocumentsClient, workspaceClient = browserWorkspaceClient }: { workspace: WorkspaceContext | null; client?: DocumentsClient; workspaceClient?: WorkspaceClient }) {
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const scopeKey = workspace?.id ?? 'msp'
  const [loaded, setLoaded] = useState<{ key: string; results: DocumentRecord[] } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selected, setSelected] = useState<DocumentRecord | 'new' | null>(null)
  const [title, setTitle] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [category, setCategory] = useState<DocumentCategory>('general')
  const [isTemplate, setIsTemplate] = useState(false)
  const [documentQuery, setDocumentQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<DocumentCategory | ''>('')
  const [templateFilter, setTemplateFilter] = useState<'all' | 'documents' | 'templates'>('all')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [shareQuery, setShareQuery] = useState('')
  const [shareOptions, setShareOptions] = useState<WorkspaceOption[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<BlockRevision[]>([])
  const [historyPage, setHistoryPage] = useState(1)
  const [historyCount, setHistoryCount] = useState(0)
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyPhase, setHistoryPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [viewedRevision, setViewedRevision] = useState<BlockRevisionDetail | null>(null)
  const [conflict, setConflict] = useState<RevisionConflictError | null>(null)
  const [sourceDocumentId, setSourceDocumentId] = useState('')
  const [placementMode, setPlacementMode] = useState<'live' | 'pinned'>('live')
  const [newBlockOpen, setNewBlockOpen] = useState(false)
  const [newBlockKind, setNewBlockKind] = useState<BlockKind>('rich_text')
  const [newBlockName, setNewBlockName] = useState('')
  const [newBlockMarkdown, setNewBlockMarkdown] = useState('')
  const [newBlockPosition, setNewBlockPosition] = useState<number | null>(null)
  const [editingBlock, setEditingBlock] = useState<{ placement: DocumentPlacement; draft: string } | null>(null)
  const [reuseReview, setReuseReview] = useState<{ placementId: string; impact: ReuseImpact; draft: string } | null>(null)
  const [approvedRevisionId, setApprovedRevisionId] = useState<string | null>(null)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionOptions, setMentionOptions] = useState<EntityMentionOption[]>([])
  const [editorGeneration, setEditorGeneration] = useState(0)
  const [publicationView, setPublicationView] = useState<{ sourceId: string; phase: 'loading' | 'ready' | 'error'; record?: DocumentPublicationDetail } | null>(null)
  const [publicationForm, setPublicationForm] = useState<{ source: DocumentRecord; reason: string; audience: PublicationAudience; retention: PublicationRetention; reviewOn: string; supersedesId: string | null } | null>(null)
  const [publicationControl, setPublicationControl] = useState<{ action: 'approve' | 'withdraw'; reason: string } | null>(null)
  const importInput = useRef<HTMLInputElement>(null)
  const attachmentInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, controller.signal, { q: documentQuery, category: categoryFilter, template: templateFilter })
      .then((result) => { if (!controller.signal.aborted) { setLoaded({ key: scopeKey, results: result.results }); setPhase('ready'); setError(null) } })
      .catch((loadError) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError)) } })
    return () => controller.abort()
  }, [categoryFilter, client, documentQuery, revision, scope, scopeKey, templateFilter])

  useEffect(() => {
    if (workspace || !shareQuery.trim() || selected === null || selected === 'new') return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      workspaceClient.searchOrganizations(shareQuery, 1, controller.signal, 'client')
        .then((result) => { if (!controller.signal.aborted) setShareOptions(result.results) })
        .catch(() => { if (!controller.signal.aborted) setShareOptions([]) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [selected, shareQuery, workspace, workspaceClient])

  useEffect(() => {
    if (!mentionQuery.trim() || !selected) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.searchMentionEntities(scope, mentionQuery, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setMentionOptions(result.results) })
        .catch(() => { if (!controller.signal.aborted) setMentionOptions([]) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, mentionQuery, scope, selected])

  const results = loaded?.key === scopeKey ? loaded.results : []
  const visiblePhase = loaded?.key === scopeKey ? phase : 'loading'
  const resetRevisionUi = () => { setHistoryOpen(false); setHistory([]); setHistoryPhase('idle'); setViewedRevision(null); setConflict(null); setReuseReview(null); setApprovedRevisionId(null); setMentionQuery(''); setMentionOptions([]); setEditingBlock(null); setNewBlockOpen(false); setNewBlockMarkdown(''); setNewBlockName(''); setNewBlockPosition(null) }
  const open = (document: DocumentRecord) => { resetRevisionUi(); setPublicationView(null); setPublicationForm(null); setPublicationControl(null); setSelected(document); setTitle(document.title); setMarkdown(document.markdown); setCategory(document.category); setIsTemplate(document.is_template); setMessage(null); setError(null); setShareQuery(''); setSourceDocumentId(''); setPlacementMode('live') }
  const create = () => { resetRevisionUi(); setPublicationView(null); setPublicationForm(null); setPublicationControl(null); setSelected('new'); setTitle(''); setMarkdown(''); setCategory('general'); setIsTemplate(false); setMessage(null); setError(null) }
  const close = () => { resetRevisionUi(); setSelected(null); setPublicationView(null); setPublicationForm(null); setPublicationControl(null); setShareQuery(''); setShareOptions([]) }
  const openPublication = async (document: DocumentRecord, publication: DocumentPublication) => {
    resetRevisionUi(); setSelected(null); setPublicationForm(null); setPublicationControl(null); setPublicationView({ sourceId: document.id, phase: 'loading' }); setError(null); setMessage(null)
    try { setPublicationView({ sourceId: document.id, phase: 'ready', record: await client.getPublication(scope, document.id, publication.id) }) }
    catch (publicationError) { setPublicationView({ sourceId: document.id, phase: 'error' }); setError(errorMessage(publicationError)) }
  }
  const save = async (skipImpactReview = false) => {
    if (!selected || !title.trim()) return
    setSaving(true); setError(null)
    const input: DocumentInput = { title: title.trim(), markdown, category, is_template: isTemplate }
    try {
      if (selected !== 'new' && markdown !== selected.markdown && !skipImpactReview && approvedRevisionId !== selected.current_revision_id) {
        const primary = selected.placements.find((placement) => placement.is_primary)
        if (primary) {
          const impact = await client.getReuseImpact(scope, selected.id, primary.id)
          if (impact.live_audience_count > 1) {
            setReuseReview({ placementId: primary.id, impact, draft: markdown })
            setMessage('Review the audiences below before saving this shared revision.')
            return
          }
        }
      }
      const record = selected === 'new'
        ? await client.create(scope, input)
        : await client.update(scope, selected.id, { ...input, base_revision_id: selected.current_revision_id })
      setSelected(record); setTitle(record.title); setMarkdown(record.markdown); setCategory(record.category); setIsTemplate(record.is_template); setConflict(null); setMessage(`Document saved as revision ${record.revision_number}.`); setRevision((value) => value + 1)
      if (historyOpen) void loadHistory(record)
    } catch (saveError) {
      if (saveError instanceof RevisionConflictError) setConflict(saveError)
      else setError(errorMessage(saveError))
    } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!selected || selected === 'new') return
    if (!window.confirm(`Archive “${selected.title}”?`)) return
    setSaving(true); setError(null)
    try { await client.archive(scope, selected.id); close(); setMessage('Document archived.'); setRevision((value) => value + 1) }
    catch (archiveError) { setError(errorMessage(archiveError)) } finally { setSaving(false) }
  }
  const share = async (organization: WorkspaceOption) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { await client.addReference(selected.id, organization.id); setMessage(`Reference added to ${organization.name}.`); setShareQuery(''); setShareOptions([]) }
    catch (shareError) { setError(errorMessage(shareError)) } finally { setSaving(false) }
  }
  const loadHistory = async (document = selected, page = 1) => {
    if (!document || document === 'new') return
    setHistoryOpen(true); setHistoryPhase('loading'); setViewedRevision(null)
    try {
      const result = await client.listRevisions(scope, document.id, page)
      setHistory(result.results); setHistoryPage(result.page); setHistoryCount(result.count); setHistoryHasMore(result.has_more); setHistoryPhase('ready')
    }
    catch (historyError) { setHistoryPhase('error'); setError(errorMessage(historyError)) }
  }
  const inspectRevision = async (revisionRecord: BlockRevision) => {
    if (!selected || selected === 'new') return
    try { setViewedRevision(await client.getRevision(scope, selected.id, revisionRecord.id)) }
    catch (historyError) { setError(errorMessage(historyError)) }
  }
  const acknowledgeConflict = () => {
    if (!conflict || !selected || selected === 'new') return
    const current = conflict.payload.current_revision
    setSelected({ ...selected, current_revision_id: current.id, revision_number: current.revision_number, checksum: current.checksum })
    setConflict(null)
    setMessage('Conflict acknowledged. Reconcile the draft with the shown server changes before saving.')
  }
  const applyCompositionRecord = (record: DocumentRecord, status: string) => {
    setSelected(record); setMarkdown(record.markdown); setMessage(status); setError(null); setRevision((value) => value + 1)
  }
  const createLocalBlock = async () => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const record = await client.addPlacement(scope, selected.id, {
        operation: 'create_block',
        block_kind: newBlockKind,
        block_name: newBlockName.trim(),
        markdown: newBlockMarkdown,
        position: newBlockPosition,
      })
      applyCompositionRecord(record, `${blockKinds.find((item) => item.value === newBlockKind)?.label ?? 'Block'} added.`)
      setNewBlockOpen(false); setNewBlockKind('rich_text'); setNewBlockName(''); setNewBlockMarkdown(''); setNewBlockPosition(null)
    } catch (blockError) { setError(errorMessage(blockError)) } finally { setSaving(false) }
  }
  const beginBlockEdit = (placement: DocumentPlacement) => {
    setEditingBlock({ placement, draft: placement.resolved_markdown })
    setReuseReview(null); setError(null); setMessage(null)
  }
  const saveBlockEdit = async () => {
    if (!selected || selected === 'new' || !editingBlock) return
    setSaving(true); setError(null)
    try {
      const impact = await client.getReuseImpact(scope, selected.id, editingBlock.placement.id)
      if (impact.live_audience_count > 1) {
        setReuseReview({ placementId: editingBlock.placement.id, impact, draft: editingBlock.draft })
        setEditingBlock(null)
        setMessage('Review the affected audiences before saving this shared block.')
        return
      }
      const record = await client.updateSharedBlock(
        scope,
        selected.id,
        editingBlock.placement.id,
        editingBlock.draft,
        editingBlock.placement.resolved_revision_id,
      )
      applyCompositionRecord(record, 'Block revision saved.')
      setEditingBlock(null)
    } catch (blockError) {
      if (blockError instanceof RevisionConflictError) setConflict(blockError)
      else setError(errorMessage(blockError))
    } finally { setSaving(false) }
  }
  const addPlacement = async () => {
    if (!selected || selected === 'new' || !sourceDocumentId) return
    const source = results.find((item) => item.id === sourceDocumentId)
    if (!source) return
    setSaving(true); setError(null)
    try {
      const record = await client.addPlacement(scope, selected.id, {
        source_document_id: source.id,
        resolution_mode: placementMode,
        pinned_revision_id: placementMode === 'pinned' ? source.current_revision_id : null,
      })
      applyCompositionRecord(record, `${source.title} added as a ${placementMode} block.`); setSourceDocumentId('')
    } catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const changePlacementMode = async (placementId: string, mode: 'live' | 'pinned', revisionId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const record = await client.updatePlacement(scope, selected.id, placementId, { resolution_mode: mode, pinned_revision_id: mode === 'pinned' ? revisionId : null })
      applyCompositionRecord(record, mode === 'live' ? 'Block now follows the latest revision.' : 'Block pinned to its current revision.')
    } catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const removePlacement = async (placementId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { applyCompositionRecord(await client.removePlacement(scope, selected.id, placementId), 'Reusable block removed.') }
    catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const reviewPlacement = async (placementId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const impact = await client.getReuseImpact(scope, selected.id, placementId)
      setReuseReview({ placementId, impact, draft: impact.markdown })
    } catch (reviewError) { setError(errorMessage(reviewError)) } finally { setSaving(false) }
  }
  const saveSharedBlock = async () => {
    if (!selected || selected === 'new' || !reuseReview) return
    setSaving(true); setError(null)
    try {
      const record = await client.updateSharedBlock(scope, selected.id, reuseReview.placementId, reuseReview.draft, reuseReview.impact.revision_id)
      applyCompositionRecord(record, `Shared block updated across ${reuseReview.impact.live_audience_count} live audience${reuseReview.impact.live_audience_count === 1 ? '' : 's'}.`)
      if (record.block_id === reuseReview.impact.block_id) { setMarkdown(record.markdown); setEditorGeneration((value) => value + 1) }
      setReuseReview(null)
    } catch (reviewError) {
      if (reviewError instanceof RevisionConflictError) setConflict(reviewError)
      else setError(errorMessage(reviewError))
    } finally { setSaving(false) }
  }
  const detachPlacement = async () => {
    if (!selected || selected === 'new' || !reuseReview) return
    setSaving(true); setError(null)
    try {
      applyCompositionRecord(await client.detachPlacement(scope, selected.id, reuseReview.placementId), 'Block detached as an independent copy in this workspace.')
      setReuseReview(null)
    } catch (detachError) { setError(errorMessage(detachError)) } finally { setSaving(false) }
  }
  const insertMention = (entity: EntityMentionOption) => {
    const label = entity.display_name.replace(/[\\[\]]/g, '\\$&')
    const append = (current: string) => `${current}${current && !current.endsWith('\n') ? '\n\n' : ''}[${label}](tekdocs://entity/${entity.id})`
    if (editingBlock) setEditingBlock({ ...editingBlock, draft: append(editingBlock.draft) })
    else if (newBlockOpen) setNewBlockMarkdown(append(newBlockMarkdown))
    else setMarkdown(append)
    setMentionQuery(''); setMentionOptions([]); setEditorGeneration((value) => value + 1)
  }
  const importMarkdown = async (file: File) => {
    setSaving(true); setError(null)
    try {
      const imported = await client.importMarkdown(scope, file, file.name.replace(/\.md$/i, '') || 'Imported document', 'general', false)
      open(imported); setMessage('Markdown imported as a new document.'); setRevision((value) => value + 1)
    } catch (importError) { setError(errorMessage(importError)) } finally { setSaving(false); if (importInput.current) importInput.current.value = '' }
  }
  const instantiateSelectedTemplate = async () => {
    if (!selected || selected === 'new' || !selected.is_template) return
    setSaving(true); setError(null)
    try {
      const created = await client.instantiateTemplate(scope, selected.id, `New from ${selected.title}`, selected.category)
      open(created); setMessage('Independent document created from the template.'); setRevision((value) => value + 1)
    } catch (templateError) { setError(errorMessage(templateError)) } finally { setSaving(false) }
  }
  const uploadAttachment = async (file: File) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const attachment = await client.uploadAttachment(scope, selected.id, file)
      setSelected({ ...selected, attachments: [...selected.attachments, attachment], attachment_count: selected.attachment_count + 1 })
      setMessage(`${attachment.filename} attached.`)
    } catch (attachmentError) { setError(errorMessage(attachmentError)) } finally { setSaving(false); if (attachmentInput.current) attachmentInput.current.value = '' }
  }
  const removeAttachment = async (attachmentId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      await client.archiveAttachment(scope, selected.id, attachmentId)
      setSelected({ ...selected, attachments: selected.attachments.filter((item) => item.id !== attachmentId), attachment_count: selected.attachment_count - 1 })
      setMessage('Attachment removed from the document.')
    } catch (attachmentError) { setError(errorMessage(attachmentError)) } finally { setSaving(false) }
  }
  const insertAttachment = (attachmentId: string, filename: string) => {
    const label = filename.replaceAll('[', '\\[').replaceAll(']', '\\]')
    const append = (current: string) => `${current}${current && !current.endsWith('\n') ? '\n\n' : ''}[${label}](tekdocs://attachment/${attachmentId})`
    if (editingBlock) setEditingBlock({ ...editingBlock, draft: append(editingBlock.draft) })
    else if (newBlockOpen) setNewBlockMarkdown(append(newBlockMarkdown))
    else setMarkdown(append)
    setEditorGeneration((value) => value + 1)
  }
  const beginPublication = (source: DocumentRecord, supersedes: DocumentPublication | null = null) => {
    setPublicationControl(null)
    setPublicationForm({ source, reason: '', audience: supersedes?.audience ?? 'msp_internal', retention: 'permanent', reviewOn: '', supersedesId: supersedes?.id ?? null })
  }
  const publishStatic = async () => {
    if (!publicationForm || !publicationForm.reason.trim()) return
    if (!window.confirm(`Publish an immutable STATIC version of “${publicationForm.source.title}”? Its retained artifacts and lifecycle record cannot be edited or deleted.`)) return
    setSaving(true); setError(null)
    try {
      const publication = await client.publish(scope, publicationForm.source.id, {
        reason: publicationForm.reason.trim(), audience: publicationForm.audience, retention: publicationForm.retention,
        retention_review_on: publicationForm.retention === 'review_on' ? publicationForm.reviewOn : null,
        supersedes_id: publicationForm.supersedesId,
      })
      const sourceId = publicationForm.source.id
      setLoaded((current) => current ? { ...current, results: current.results.map((document) => document.id === sourceId ? { ...document, publications: [publication, ...document.publications], publication_count: document.publication_count + 1 } : document) } : current)
      setSelected(null); setPublicationForm(null)
      setPublicationView({ sourceId, phase: 'ready', record: publication })
      setMessage(publication.lifecycle_state === 'pending_approval' ? 'STATIC snapshot submitted. A different authorized user must approve client portal availability.' : publication.supersedes_id ? 'Corrected STATIC publication created; the prior version remains retained.' : 'Immutable STATIC publication and retained artifacts created.')
    } catch (publicationError) { setError(errorMessage(publicationError)) } finally { setSaving(false) }
  }
  const applyPublicationControl = async () => {
    if (!publicationView?.record || !publicationControl?.reason.trim()) return
    const verb = publicationControl.action === 'approve' ? 'Approve' : 'Withdraw'
    if (!window.confirm(`${verb} “${publicationView.record.title}”? This decision is retained in its append-only publication history.`)) return
    setSaving(true); setError(null)
    try {
      const record = publicationControl.action === 'approve'
        ? await client.approvePublication(scope, publicationView.sourceId, publicationView.record.id, publicationControl.reason.trim())
        : await client.withdrawPublication(scope, publicationView.sourceId, publicationView.record.id, publicationControl.reason.trim())
      setPublicationView({ sourceId: publicationView.sourceId, phase: 'ready', record })
      setPublicationControl(null)
      setRevision((value) => value + 1)
      setMessage(publicationControl.action === 'approve' ? 'Publication approved for its intended audience.' : 'Publication withdrawn from audience availability; retained evidence remains accessible to authorized MSP staff.')
    } catch (controlError) { setError(errorMessage(controlError)) } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>Documentation</h1><p>{workspace ? `Documents owned by or referenced into ${workspace.name}.` : 'MSP-owned procedures, policies, and reusable reference material.'}</p></div><div className="page-actions"><input ref={importInput} aria-label="Markdown file to import" className="sr-only" type="file" accept=".md,text/markdown" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importMarkdown(file) }} /><button className="secondary-button" type="button" disabled={saving} onClick={() => importInput.current?.click()}><FileUp size={16} />Import Markdown</button><button className="primary-button" type="button" onClick={create}><Plus size={16} />New document</button></div></header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {message && <div className="form-message success" role="status">{message}</div>}
    <section className="content-section document-index" aria-labelledby="document-index-heading">
      <div className="section-heading"><h2 id="document-index-heading">Documents</h2><span>{phase === 'ready' ? `${results.length} total` : 'Loading'}</span></div>
      <div className="document-filters"><label><span>Search</span><input type="search" value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} /></label><label><span>Category</span><select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value as DocumentCategory | '')}><option value="">All categories</option>{categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label><span>Type</span><select value={templateFilter} onChange={(event) => setTemplateFilter(event.target.value as typeof templateFilter)}><option value="all">Documents and templates</option><option value="documents">Documents</option><option value="templates">Templates</option></select></label></div>
      {visiblePhase === 'loading' && <p className="empty-state" role="status">Loading documents…</p>}
      {visiblePhase === 'error' && <p className="empty-state">Documents are unavailable.</p>}
      {visiblePhase === 'ready' && results.length === 0 && <p className="empty-state">No documents have been added to this workspace.</p>}
      {visiblePhase === 'ready' && results.length > 0 && <ul className="document-title-list">{results.map((document) => <li key={document.id}><button type="button" onClick={() => open(document)}><BookOpenText size={17} /><span><strong>{document.title || 'Untitled document'}</strong><small>{categories.find((item) => item.value === document.category)?.label}{document.is_template ? ' · Template' : ''}{document.is_reference ? ' · MSP reference' : ''}{document.publication_count ? ` · ${document.publication_count} STATIC` : ''}</small></span></button>{document.publications.length > 0 && <ul className="static-publication-list">{document.publications.map((publication) => <li key={publication.id}><button type="button" onClick={() => { void openPublication(document, publication) }}><FileCheck2 size={15} /><span><strong>{publication.title}</strong><small>STATIC · {publication.lifecycle_state.replace('_', ' ')} · {publication.audience.replace('_', ' ')} · {new Date(publication.published_at).toLocaleString()}</small></span></button></li>)}</ul>}</li>)}</ul>}
    </section>
    {publicationView && <section className="document-workspace static-publication" aria-label="STATIC publication">
      <div className="document-edit-heading"><div><h2>{publicationView.record?.title ?? 'STATIC publication'}</h2><p>Immutable retained version</p></div><button className="icon-button" type="button" aria-label="Close publication" onClick={close}><X size={19} /></button></div>
      {publicationView.phase === 'loading' && <p className="empty-state" role="status">Loading STATIC publication…</p>}
      {publicationView.phase === 'error' && <p className="empty-state">This STATIC publication is unavailable.</p>}
      {publicationView.phase === 'ready' && publicationView.record && <>
        <dl className="publication-lifecycle">
          <div><dt>Status</dt><dd>{publicationView.record.lifecycle_state.replace('_', ' ')}</dd></div>
          <div><dt>Audience</dt><dd>{publicationView.record.audience.replace('_', ' ')}</dd></div>
          <div><dt>Reason</dt><dd>{publicationView.record.reason}</dd></div>
          <div><dt>Retention</dt><dd>{publicationView.record.retention === 'permanent' ? 'Permanent' : `Review on ${publicationView.record.retention_review_on}`}</dd></div>
        </dl>
        <section className="publication-audiences" aria-labelledby="publication-audiences-heading"><h3 id="publication-audiences-heading">Audience availability</h3><dl>{publicationView.record.audience_projections.map((projection) => <div key={projection.audience}><dt>{projection.audience === 'msp_staff' ? 'MSP staff' : 'Client portal'}</dt><dd>{projection.available ? 'Available' : projection.state.replaceAll('_', ' ')}</dd></div>)}</dl></section>
        <div className="publication-integrity"><ShieldCheck size={18} /><div><strong>{publicationView.record.verification.valid ? 'Signature verified' : 'Verification failed'}</strong><span>{publicationView.record.signature_algorithm} · snapshot created {new Date(publicationView.record.published_at).toLocaleString()} by {publicationView.record.published_by ?? 'System'}</span><code>SHA-256 {publicationView.record.content_digest}</code><code>Key {publicationView.record.key_fingerprint}</code></div></div>
        <SanitizedMarkdown html={publicationView.record.sanitized_html} />
        <div className="document-actions">
          {publicationView.record.artifacts.filter((artifact) => artifact.kind === 'pdf').map((artifact) => <a key={artifact.id} className="secondary-button" href={client.publicationArtifactUrl(scope, publicationView.sourceId, publicationView.record!.id, artifact.id)}><Download size={15} />Download PDF</a>)}
          <a className="secondary-button" href={client.publicationMarkdownUrl(scope, publicationView.sourceId, publicationView.record.id)}><Download size={15} />Download Markdown</a>
          <a className="secondary-button" href={client.publicationManifestUrl(scope, publicationView.sourceId, publicationView.record.id)}><Download size={15} />Download manifest</a>
          {['published', 'review_due', 'withdrawn'].includes(publicationView.record.lifecycle_state) && !publicationView.record.superseded_by_id && results.find((document) => document.id === publicationView.sourceId) && <button className="secondary-button" type="button" onClick={() => beginPublication(results.find((document) => document.id === publicationView.sourceId)!, publicationView.record)}><FileCheck2 size={15} />Publish correction</button>}
          {publicationView.record.lifecycle_state === 'pending_approval' && <button className="secondary-button" type="button" onClick={() => setPublicationControl({ action: 'approve', reason: '' })}>Approve publication</button>}
          {['pending_approval', 'published', 'review_due'].includes(publicationView.record.lifecycle_state) && <button className="danger-button" type="button" onClick={() => setPublicationControl({ action: 'withdraw', reason: '' })}>Withdraw publication</button>}
        </div>
        {publicationControl && <section className="publication-control" aria-labelledby="publication-control-heading"><h3 id="publication-control-heading">{publicationControl.action === 'approve' ? 'Approval decision' : 'Withdrawal decision'}</h3><p>{publicationControl.action === 'approve' ? 'Client-visible approval must come from a different authorized user than the snapshot publisher.' : 'Withdrawal removes audience availability without deleting the signed snapshot or retained artifacts.'}</p><label>Decision reason<textarea required maxLength={500} value={publicationControl.reason} onChange={(event) => setPublicationControl({ ...publicationControl, reason: event.target.value })} /></label><div className="document-actions"><button className={publicationControl.action === 'approve' ? 'primary-button' : 'danger-button'} type="button" disabled={saving || !publicationControl.reason.trim()} onClick={() => { void applyPublicationControl() }}>{saving ? 'Saving decision…' : publicationControl.action === 'approve' ? 'Record approval' : 'Record withdrawal'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPublicationControl(null)}>Cancel</button></div></section>}
        <section className="publication-history" aria-labelledby="publication-history-heading"><h3 id="publication-history-heading">Publication history</h3><ol>{publicationView.record.control_events.map((event) => <li key={event.id}><strong>{event.action.replace('_', ' ')}</strong><span>{event.reason}</span><small>{event.actor ?? 'System'} · {new Date(event.occurred_at).toLocaleString()}</small></li>)}</ol></section>
        {publicationView.record.artifacts.some((artifact) => artifact.kind === 'attachment') && <section className="publication-artifacts" aria-labelledby="retained-artifacts-heading"><h3 id="retained-artifacts-heading">Retained attachments</h3><ul>{publicationView.record.artifacts.filter((artifact) => artifact.kind === 'attachment').map((artifact) => <li key={artifact.id}><a href={client.publicationArtifactUrl(scope, publicationView.sourceId, publicationView.record!.id, artifact.id)}><strong>{artifact.filename}</strong><small>{artifact.media_type} · {artifact.size.toLocaleString()} bytes · {artifact.checksum.slice(0, 12)}</small></a></li>)}</ul></section>}
      </>}
    </section>}
    {publicationForm && <section className="publication-form" aria-labelledby="publication-form-heading">
      <div className="section-heading"><div><h2 id="publication-form-heading">{publicationForm.supersedesId ? 'Publish correction' : 'Publish STATIC'}</h2><p>{publicationForm.source.title}</p></div><button className="icon-button" type="button" aria-label="Cancel publication" onClick={() => setPublicationForm(null)}><X size={18} /></button></div>
      <label>Publication reason<textarea required maxLength={500} value={publicationForm.reason} onChange={(event) => setPublicationForm({ ...publicationForm, reason: event.target.value })} /></label>
      <div className="publication-form-fields"><label>Audience<select disabled={publicationForm.supersedesId !== null} value={publicationForm.audience} onChange={(event) => setPublicationForm({ ...publicationForm, audience: event.target.value as PublicationAudience })}><option value="msp_internal">MSP internal</option>{workspace && <option value="client_visible">Client visible</option>}</select></label><label>Retention<select value={publicationForm.retention} onChange={(event) => setPublicationForm({ ...publicationForm, retention: event.target.value as PublicationRetention, reviewOn: event.target.value === 'permanent' ? '' : publicationForm.reviewOn })}><option value="permanent">Permanent</option><option value="review_on">Review on date</option></select></label>{publicationForm.retention === 'review_on' && <label>Review date<input type="date" required value={publicationForm.reviewOn} onChange={(event) => setPublicationForm({ ...publicationForm, reviewOn: event.target.value })} /></label>}</div>
      <p>Publishing retains signed Markdown, HTML, PDF, manifest, and referenced attachment bytes. Client-visible snapshots remain pending until a different authorized user approves them.</p>
      <div className="document-actions"><button className="primary-button" type="button" disabled={saving || !publicationForm.reason.trim() || (publicationForm.retention === 'review_on' && !publicationForm.reviewOn)} onClick={() => { void publishStatic() }}>{saving ? 'Publishing…' : publicationForm.supersedesId ? 'Publish correction' : 'Publish immutable version'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPublicationForm(null)}>Cancel</button></div>
    </section>}
    {selected && <section className="document-workspace" aria-label={selected === 'new' ? 'New document' : `Edit ${selected.title}`}>
      <div className="document-edit-heading"><label>Document title<input autoFocus={selected === 'new'} maxLength={240} required value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Category<select value={category} onChange={(event) => setCategory(event.target.value as DocumentCategory)}>{categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label className="checkbox-field"><input type="checkbox" checked={isTemplate} onChange={(event) => setIsTemplate(event.target.checked)} />Reusable template</label><button className="icon-button" type="button" aria-label="Close document" onClick={close}><X size={19} /></button></div>
      {selected === 'new' ? <Suspense fallback={<section className="content-section" role="status">Loading editor…</section>}><Editor key={`new-${editorGeneration}`} initialMarkdown={markdown} title={title || 'Untitled document'} description="The first Markdown block" organizationId={workspace?.id} onMarkdownChange={setMarkdown} /></Suspense> : <section className="document-block-canvas" aria-labelledby="document-block-canvas-heading">
        <div className="section-heading"><div><h2 id="document-block-canvas-heading">Document blocks</h2><p>Select a block to edit it. Each block keeps its own identity and revision history.</p></div><button className="secondary-button" type="button" disabled={saving} onClick={() => { setNewBlockPosition(null); setNewBlockOpen(true) }}><Plus size={15} />New block</button></div>
        <ol>{selected.placements.map((placement) => <li className={editingBlock?.placement.id === placement.id ? 'editing' : ''} key={placement.id} style={{ marginInlineStart: `${placement.depth * 18}px` }}>
          <header><span className="block-kind"><BlockKindIcon kind={placement.block_kind} />{blockKinds.find((item) => item.value === placement.block_kind)?.label ?? placement.block_kind}</span><span>{placement.resolution_mode === 'pinned' ? `Pinned at revision ${placement.resolved_revision_number}` : `Revision ${placement.resolved_revision_number}`}</span></header>
          {editingBlock?.placement.id === placement.id ? <div className="block-editor"><Suspense fallback={<p role="status">Loading block editor…</p>}><Editor key={`${placement.id}-${placement.resolved_revision_id}-${editorGeneration}`} initialMarkdown={editingBlock.draft} title={placement.block_name} description="Canonical Markdown block" organizationId={workspace?.id} documentId={selected.id} onMarkdownChange={(draft) => setEditingBlock({ placement, draft })} /></Suspense><div className="document-actions"><button className="primary-button" type="button" disabled={saving || editingBlock.draft === placement.resolved_markdown} onClick={() => { void saveBlockEdit() }}>{saving ? 'Saving…' : 'Save block'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setEditingBlock(null)}>Cancel</button></div></div> : <button className="block-preview" type="button" onClick={() => beginBlockEdit(placement)}><span>{placement.block_name.replace(/ — content$/, '')}</span><pre>{placement.resolved_markdown || 'Empty block'}</pre><span className="block-edit-label"><Pencil size={14} />Edit block</span></button>}
          <footer><button className="secondary-button" type="button" disabled={saving} onClick={() => { void reviewPlacement(placement.id) }}><Share2 size={14} />Reuse impact</button>{!placement.is_primary && <>{placement.resolution_mode === 'live' ? <button className="secondary-button" type="button" disabled={saving} onClick={() => { void changePlacementMode(placement.id, 'pinned', placement.resolved_revision_id) }}><Pin size={14} />Pin</button> : <button className="secondary-button" type="button" disabled={saving} onClick={() => { void changePlacementMode(placement.id, 'live', placement.resolved_revision_id) }}><Link2 size={14} />Follow latest</button>}<button className="icon-button" type="button" disabled={saving} aria-label={`Remove ${placement.block_name.replace(/ — content$/, '')}`} onClick={() => { void removePlacement(placement.id) }}><Unlink size={15} /></button></>}</footer>
        </li>)}</ol>
      </section>}
      <div className="entity-mention-picker"><label><Search size={15} /><span>Reference an entity</span><input type="search" placeholder="Search people, sites, organizations…" value={mentionQuery} onChange={(event) => { setMentionQuery(event.target.value); if (!event.target.value.trim()) setMentionOptions([]) }} /></label>{mentionQuery.trim() && mentionOptions.length > 0 && <ul>{mentionOptions.map((entity) => <li key={entity.id}><button type="button" onClick={() => insertMention(entity)}><strong>{entity.display_name}</strong><small>{entity.entity_type.replaceAll('_', ' ')} · {entity.workspace_label}</small></button></li>)}</ul>}</div>
      {conflict && <div className="revision-conflict" role="alert"><strong>Newer revision detected</strong><p>Your draft remains in the editor. Review the server changes below and reconcile them into your draft.</p>{conflict.payload.diff && <pre>{conflict.payload.diff}</pre>}<button className="secondary-button" type="button" onClick={acknowledgeConflict}>I reconciled with revision {conflict.payload.current_revision.revision_number}</button></div>}
      <div className="document-actions"><button className="primary-button" type="button" disabled={saving || !title.trim() || conflict !== null} onClick={() => { void save() }}>{saving ? 'Saving…' : 'Save document'}</button>{selected !== 'new' && <button className="secondary-button" type="button" disabled={saving} onClick={() => beginPublication(selected)}><FileCheck2 size={15} />Publish STATIC</button>}{selected !== 'new' && selected.is_template && <button className="secondary-button" type="button" disabled={saving} onClick={() => { void instantiateSelectedTemplate() }}><Copy size={15} />Use template</button>}{selected !== 'new' && <a className="secondary-button" href={client.exportUrl(scope, selected.id)}><Download size={15} />Export Markdown</a>}{selected !== 'new' && <button className="secondary-button" type="button" onClick={() => { if (historyOpen) setHistoryOpen(false); else void loadHistory() }}><History size={15} />{historyOpen ? 'Hide history' : 'Revision history'}</button>}{selected !== 'new' && <button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}><Archive size={15} />Archive</button>}</div>
      {selected !== 'new' && <section className="document-attachments" aria-labelledby="document-attachments-heading"><div className="section-heading"><div><h2 id="document-attachments-heading">Attachments</h2><p>Private managed files referenced by stable Markdown links.</p></div><div><input ref={attachmentInput} aria-label="Attachment file" className="sr-only" type="file" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadAttachment(file) }} /><button className="secondary-button" type="button" disabled={saving} onClick={() => attachmentInput.current?.click()}><Paperclip size={15} />Add attachment</button></div></div>{selected.attachments.length === 0 ? <p className="empty-state">No files attached.</p> : <ul>{selected.attachments.map((attachment) => <li key={attachment.id}><a href={client.attachmentDownloadUrl(scope, selected.id, attachment.id)}><strong>{attachment.filename}</strong><small>{attachment.media_type} · {attachment.size.toLocaleString()} bytes · scanned</small></a><div><button className="secondary-button" type="button" onClick={() => insertAttachment(attachment.id, attachment.filename)}>Insert link</button><button className="icon-button" type="button" aria-label={`Remove ${attachment.filename}`} disabled={saving} onClick={() => { void removeAttachment(attachment.id) }}><Trash2 size={15} /></button></div></li>)}</ul>}</section>}
      {selected !== 'new' && <section className="document-composition" aria-labelledby="document-composition-heading">
        <div className="section-heading"><div><h2 id="document-composition-heading">Block sources</h2><p>Create a local block or reuse content from a visible document.</p></div><span>{selected.placement_count} block{selected.placement_count === 1 ? '' : 's'}</span></div>
        {reuseReview && <section className="reuse-impact" aria-labelledby="reuse-impact-heading"><div className="section-heading"><div><h3 id="reuse-impact-heading">Reuse impact</h3><p>{reuseReview.impact.live_audience_count} live audience{reuseReview.impact.live_audience_count === 1 ? '' : 's'} will update; {reuseReview.impact.pinned_audience_count} pinned audience{reuseReview.impact.pinned_audience_count === 1 ? '' : 's'} will stay unchanged.</p></div><button className="icon-button" type="button" aria-label="Close reuse impact" onClick={() => setReuseReview(null)}><X size={16} /></button></div><ul>{reuseReview.impact.audiences.map((audience, index) => <li key={`${audience.relationship}-${audience.document_id}-${audience.workspace_id}-${index}`}><span><strong>{audience.document_title}</strong><small>{audience.workspace_name} · {audience.relationship.replace('_', ' ')}</small></span><span className={audience.will_update ? 'impact-live' : 'impact-pinned'}>{audience.will_update ? 'Will update' : 'Unchanged'}</span></li>)}</ul>{reuseReview.impact.truncated && <p>Additional authorized audiences are not shown.</p>}{reuseReview.impact.can_edit_shared && <><label>Shared block Markdown<textarea value={reuseReview.draft} onChange={(event) => setReuseReview({ ...reuseReview, draft: event.target.value })} /></label><button className="primary-button" type="button" disabled={saving} onClick={() => { void saveSharedBlock() }}>Save shared revision</button></>}{reuseReview.impact.can_detach && <button className="secondary-button" type="button" disabled={saving} onClick={() => { void detachPlacement() }}><Copy size={14} />Detach into this workspace</button>}{!reuseReview.impact.can_edit_shared && !reuseReview.impact.can_detach && <p>You can view this block but cannot edit or detach it.</p>}</section>}
        {newBlockOpen && <section className="new-document-block" aria-labelledby="new-document-block-heading"><div className="section-heading"><div><h3 id="new-document-block-heading">New local block</h3><p>This block begins with its own stable identity and revision.</p></div><button className="icon-button" type="button" aria-label="Cancel new block" onClick={() => setNewBlockOpen(false)}><X size={16} /></button></div><div className="new-block-fields"><label>Block type<select value={newBlockKind} onChange={(event) => setNewBlockKind(event.target.value as BlockKind)}>{blockKinds.map((kind) => <option key={kind.value} value={kind.value}>{kind.label} — {kind.description}</option>)}</select></label><label>Block name <span>optional</span><input maxLength={240} value={newBlockName} onChange={(event) => setNewBlockName(event.target.value)} /></label><label>Insert after<select value={newBlockPosition ?? ''} onChange={(event) => setNewBlockPosition(event.target.value ? Number(event.target.value) : null)}><option value="">End of document</option>{selected.placements.filter((placement) => placement.depth === 0).map((placement) => <option key={placement.id} value={placement.position + 1}>{placement.block_name.replace(/ — content$/, '')}</option>)}</select></label></div><Suspense fallback={<p role="status">Loading block editor…</p>}><Editor key={`new-block-${newBlockKind}-${editorGeneration}`} initialMarkdown={newBlockMarkdown} title={newBlockName || blockKinds.find((item) => item.value === newBlockKind)?.label || 'New block'} description="Canonical Markdown block" organizationId={workspace?.id} documentId={selected.id} onMarkdownChange={setNewBlockMarkdown} /></Suspense><div className="document-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void createLocalBlock() }}>{saving ? 'Adding…' : 'Add block'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setNewBlockOpen(false)}>Cancel</button></div></section>}
        <div className="composition-add"><label>Document block<select value={sourceDocumentId} onChange={(event) => setSourceDocumentId(event.target.value)}><option value="">Choose a visible document</option>{results.filter((item) => item.id !== selected.id).map((item) => <option key={item.id} value={item.id}>{item.title}{item.is_reference ? ' — MSP reference' : ''}</option>)}</select></label><label>Resolution<select value={placementMode} onChange={(event) => setPlacementMode(event.target.value as 'live' | 'pinned')}><option value="live">Live</option><option value="pinned">Pinned at current revision</option></select></label><button className="secondary-button" type="button" disabled={saving || !sourceDocumentId} onClick={() => { void addPlacement() }}><Plus size={15} />Reuse document block</button></div>
        {selected.placement_count > 1 && <details className="resolved-markdown"><summary>View assembled Markdown</summary><pre>{selected.resolved_markdown}</pre></details>}
      </section>}
      {historyOpen && selected !== 'new' && <section className="revision-history" aria-labelledby="revision-history-heading">
        <div className="section-heading"><div><h2 id="revision-history-heading">Revision history</h2><p>{historyCount} retained revision{historyCount === 1 ? '' : 's'} · latest first</p></div><span>Page {historyPage}</span></div>
        {historyPhase === 'loading' && <p role="status">Loading revision history…</p>}
        {historyPhase === 'error' && <p role="alert">Revision history is unavailable.</p>}
        {historyPhase === 'ready' && history.length === 0 && <p>No revisions are available.</p>}
        {historyPhase === 'ready' && history.length > 0 && <>
          <div className="revision-history-body"><ol>{history.map((item) => <li key={item.id}><button type="button" onClick={() => { void inspectRevision(item) }} aria-current={viewedRevision?.id === item.id ? 'true' : undefined}><strong>Revision {item.revision_number}</strong>{item.is_current && <span>Current</span>}<small>{item.created_by ?? 'System'} · {new Date(item.created_at).toLocaleString()}</small><code>{item.checksum.slice(0, 12)}</code></button></li>)}</ol><div className="revision-diff" aria-live="polite">{viewedRevision ? <><h3>Revision {viewedRevision.revision_number} changes</h3><pre tabIndex={0}>{viewedRevision.diff_from_parent || 'No line changes.'}</pre></> : <p>Select a revision to inspect its diff.</p>}</div></div>
          <nav className="history-pagination" aria-label="Revision history pages"><button className="secondary-button" type="button" disabled={historyPage === 1} onClick={() => { void loadHistory(selected, historyPage - 1) }}>Newer revisions</button><span>Showing {((historyPage - 1) * 50) + 1}–{Math.min(historyPage * 50, historyCount)} of {historyCount}</span><button className="secondary-button" type="button" disabled={!historyHasMore} onClick={() => { void loadHistory(selected, historyPage + 1) }}>Older revisions</button></nav>
        </>}
      </section>}
      {!workspace && selected !== 'new' && <div className="document-share"><div><Share2 size={16} /><span><strong>List in a client workspace</strong><small>The MSP remains the owner; no document is copied.</small></span></div><label><span className="sr-only">Find client organization</span><input type="search" placeholder="Find a client" value={shareQuery} onChange={(event) => setShareQuery(event.target.value)} /></label>{shareOptions.length > 0 && <ul>{shareOptions.map((organization) => <li key={organization.id}><button type="button" disabled={saving} onClick={() => { void share(organization) }}>{organization.name}<ExternalLink size={14} /></button></li>)}</ul>}</div>}
    </section>}
  </>
}
