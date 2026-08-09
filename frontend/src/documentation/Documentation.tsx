import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Archive, BookOpenText, ExternalLink, History, Link2, Pin, Plus, Share2, Unlink, X } from 'lucide-react'
import type { WorkspaceContext, WorkspaceClient, WorkspaceOption } from '../workspaces/api'
import { browserWorkspaceClient } from '../workspaces/api'
import { browserDocumentsClient, RevisionConflictError } from './api'
import type { BlockRevision, BlockRevisionDetail, DocumentInput, DocumentRecord, DocumentsClient } from './api'

const Editor = lazy(async () => ({ default: (await import('../editor/EditorSpike')).EditorSpike }))

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Documentation could not be loaded.'
}

export function Documentation({ workspace, client = browserDocumentsClient, workspaceClient = browserWorkspaceClient }: { workspace: WorkspaceContext | null; client?: DocumentsClient; workspaceClient?: WorkspaceClient }) {
  const scope = useMemo(() => ({ organizationId: workspace?.id }), [workspace?.id])
  const scopeKey = workspace?.id ?? 'msp'
  const [loaded, setLoaded] = useState<{ key: string; results: DocumentRecord[] } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selected, setSelected] = useState<DocumentRecord | 'new' | null>(null)
  const [title, setTitle] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [shareQuery, setShareQuery] = useState('')
  const [shareOptions, setShareOptions] = useState<WorkspaceOption[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<BlockRevision[]>([])
  const [historyPhase, setHistoryPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [viewedRevision, setViewedRevision] = useState<BlockRevisionDetail | null>(null)
  const [conflict, setConflict] = useState<RevisionConflictError | null>(null)
  const [sourceDocumentId, setSourceDocumentId] = useState('')
  const [placementMode, setPlacementMode] = useState<'live' | 'pinned'>('live')

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setLoaded({ key: scopeKey, results: result.results }); setPhase('ready'); setError(null) } })
      .catch((loadError) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError)) } })
    return () => controller.abort()
  }, [client, revision, scope, scopeKey])

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

  const results = loaded?.key === scopeKey ? loaded.results : []
  const visiblePhase = loaded?.key === scopeKey ? phase : 'loading'
  const resetRevisionUi = () => { setHistoryOpen(false); setHistory([]); setHistoryPhase('idle'); setViewedRevision(null); setConflict(null) }
  const open = (document: DocumentRecord) => { resetRevisionUi(); setSelected(document); setTitle(document.title); setMarkdown(document.markdown); setMessage(null); setError(null); setShareQuery(''); setSourceDocumentId(''); setPlacementMode('live') }
  const create = () => { resetRevisionUi(); setSelected('new'); setTitle(''); setMarkdown(''); setMessage(null); setError(null) }
  const close = () => { resetRevisionUi(); setSelected(null); setShareQuery(''); setShareOptions([]) }
  const save = async () => {
    if (!title.trim()) return
    setSaving(true); setError(null)
    const input: DocumentInput = { title: title.trim(), markdown }
    try {
      const record = selected === 'new'
        ? await client.create(scope, input)
        : await client.update(scope, selected!.id, { ...input, base_revision_id: selected!.current_revision_id })
      setSelected(record); setTitle(record.title); setMarkdown(record.markdown); setConflict(null); setMessage(`Document saved as revision ${record.revision_number}.`); setRevision((value) => value + 1)
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
  const loadHistory = async (document = selected) => {
    if (!document || document === 'new') return
    setHistoryOpen(true); setHistoryPhase('loading'); setViewedRevision(null)
    try { const result = await client.listRevisions(scope, document.id); setHistory(result.results); setHistoryPhase('ready') }
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
    setSelected(record); setMessage(status); setError(null); setRevision((value) => value + 1)
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

  return <>
    <header className="page-header"><div><h1>Documentation</h1><p>{workspace ? `Documents owned by or referenced into ${workspace.name}.` : 'MSP-owned procedures, policies, and reusable reference material.'}</p></div><button className="primary-button" type="button" onClick={create}><Plus size={16} />New document</button></header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {message && <div className="form-message success" role="status">{message}</div>}
    <section className="content-section document-index" aria-labelledby="document-index-heading">
      <div className="section-heading"><h2 id="document-index-heading">Documents</h2><span>{phase === 'ready' ? `${results.length} total` : 'Loading'}</span></div>
      {visiblePhase === 'loading' && <p className="empty-state" role="status">Loading documents…</p>}
      {visiblePhase === 'error' && <p className="empty-state">Documents are unavailable.</p>}
      {visiblePhase === 'ready' && results.length === 0 && <p className="empty-state">No documents have been added to this workspace.</p>}
      {visiblePhase === 'ready' && results.length > 0 && <ul className="document-title-list">{results.map((document) => <li key={document.id}><button type="button" onClick={() => open(document)}><BookOpenText size={17} /><span><strong>{document.title || 'Untitled document'}</strong>{document.is_reference && <small>MSP reference</small>}</span></button></li>)}</ul>}
    </section>
    {selected && <section className="document-workspace" aria-label={selected === 'new' ? 'New document' : `Edit ${selected.title}`}>
      <div className="document-edit-heading"><label>Document title<input autoFocus={selected === 'new'} maxLength={240} required value={title} onChange={(event) => setTitle(event.target.value)} /></label><button className="icon-button" type="button" aria-label="Close document" onClick={close}><X size={19} /></button></div>
      <Suspense fallback={<section className="content-section" role="status">Loading editor…</section>}><Editor key={selected === 'new' ? 'new' : selected.id} initialMarkdown={markdown} title={title || 'Untitled document'} description="Canonical Markdown · changes save to PostgreSQL" onMarkdownChange={setMarkdown} /></Suspense>
      {conflict && <div className="revision-conflict" role="alert"><strong>Newer revision detected</strong><p>Your draft remains in the editor. Review the server changes below and reconcile them into your draft.</p>{conflict.payload.diff && <pre>{conflict.payload.diff}</pre>}<button className="secondary-button" type="button" onClick={acknowledgeConflict}>I reconciled with revision {conflict.payload.current_revision.revision_number}</button></div>}
      <div className="document-actions"><button className="primary-button" type="button" disabled={saving || !title.trim() || conflict !== null} onClick={() => { void save() }}>{saving ? 'Saving…' : 'Save document'}</button>{selected !== 'new' && <button className="secondary-button" type="button" onClick={() => { if (historyOpen) setHistoryOpen(false); else void loadHistory() }}><History size={15} />{historyOpen ? 'Hide history' : 'Revision history'}</button>}{selected !== 'new' && <button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}><Archive size={15} />Archive</button>}</div>
      {selected !== 'new' && <section className="document-composition" aria-labelledby="document-composition-heading">
        <div className="section-heading"><div><h2 id="document-composition-heading">Reusable blocks</h2><p>Live blocks follow new revisions. Pinned blocks retain the selected revision.</p></div><span>{selected.placement_count} block{selected.placement_count === 1 ? '' : 's'}</span></div>
        <ol>{selected.placements.map((placement) => <li key={placement.id} style={{ paddingInlineStart: `${placement.depth * 18}px` }}><div><Link2 size={15} /><span><strong>{placement.is_primary ? title || selected.title : placement.block_name.replace(/ — content$/, '')}</strong><small>{placement.is_primary ? 'Primary block' : `${placement.resolution_mode === 'live' ? 'Live' : 'Pinned'} · revision ${placement.resolved_revision_number} · ${placement.resolved_checksum.slice(0, 12)}`}</small></span></div>{!placement.is_primary && <div className="composition-actions">{placement.resolution_mode === 'live' ? <button className="secondary-button" type="button" disabled={saving} onClick={() => { void changePlacementMode(placement.id, 'pinned', placement.resolved_revision_id) }}><Pin size={14} />Pin revision</button> : <button className="secondary-button" type="button" disabled={saving} onClick={() => { void changePlacementMode(placement.id, 'live', placement.resolved_revision_id) }}><Link2 size={14} />Follow latest</button>}<button className="icon-button" type="button" disabled={saving} aria-label={`Remove ${placement.block_name.replace(/ — content$/, '')}`} onClick={() => { void removePlacement(placement.id) }}><Unlink size={15} /></button></div>}</li>)}</ol>
        <div className="composition-add"><label>Document block<select value={sourceDocumentId} onChange={(event) => setSourceDocumentId(event.target.value)}><option value="">Choose a visible document</option>{results.filter((item) => item.id !== selected.id).map((item) => <option key={item.id} value={item.id}>{item.title}{item.is_reference ? ' — MSP reference' : ''}</option>)}</select></label><label>Resolution<select value={placementMode} onChange={(event) => setPlacementMode(event.target.value as 'live' | 'pinned')}><option value="live">Live</option><option value="pinned">Pinned at current revision</option></select></label><button className="secondary-button" type="button" disabled={saving || !sourceDocumentId} onClick={() => { void addPlacement() }}><Plus size={15} />Add block</button></div>
        {selected.placement_count > 1 && <details className="resolved-markdown"><summary>View assembled Markdown</summary><pre>{selected.resolved_markdown}</pre></details>}
      </section>}
      {historyOpen && selected !== 'new' && <section className="revision-history" aria-labelledby="revision-history-heading"><div className="section-heading"><h2 id="revision-history-heading">Revision history</h2><span>Latest first</span></div>{historyPhase === 'loading' && <p role="status">Loading revision history…</p>}{historyPhase === 'error' && <p>Revision history is unavailable.</p>}{historyPhase === 'ready' && history.length === 0 && <p>No revisions are available.</p>}{historyPhase === 'ready' && history.length > 0 && <div className="revision-history-body"><ol>{history.map((item) => <li key={item.id}><button type="button" onClick={() => { void inspectRevision(item) }} aria-current={viewedRevision?.id === item.id ? 'true' : undefined}><strong>Revision {item.revision_number}</strong>{item.is_current && <span>Current</span>}<small>{item.created_by ?? 'System'} · {new Date(item.created_at).toLocaleString()}</small><code>{item.checksum.slice(0, 12)}</code></button></li>)}</ol><div className="revision-diff">{viewedRevision ? <><h3>Revision {viewedRevision.revision_number} changes</h3><pre>{viewedRevision.diff_from_parent || 'No line changes.'}</pre></> : <p>Select a revision to inspect its diff.</p>}</div></div>}</section>}
      {!workspace && selected !== 'new' && <div className="document-share"><div><Share2 size={16} /><span><strong>List in a client workspace</strong><small>The MSP remains the owner; no document is copied.</small></span></div><label><span className="sr-only">Find client organization</span><input type="search" placeholder="Find a client" value={shareQuery} onChange={(event) => setShareQuery(event.target.value)} /></label>{shareOptions.length > 0 && <ul>{shareOptions.map((organization) => <li key={organization.id}><button type="button" disabled={saving} onClick={() => { void share(organization) }}>{organization.name}<ExternalLink size={14} /></button></li>)}</ul>}</div>}
    </section>}
  </>
}
