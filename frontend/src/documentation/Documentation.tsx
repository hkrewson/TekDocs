import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Archive, BookOpenText, ExternalLink, Plus, Share2, X } from 'lucide-react'
import type { WorkspaceContext, WorkspaceClient, WorkspaceOption } from '../workspaces/api'
import { browserWorkspaceClient } from '../workspaces/api'
import { browserDocumentsClient } from './api'
import type { DocumentInput, DocumentRecord, DocumentsClient } from './api'

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
  const open = (document: DocumentRecord) => { setSelected(document); setTitle(document.title); setMarkdown(document.markdown); setMessage(null); setError(null); setShareQuery('') }
  const create = () => { setSelected('new'); setTitle(''); setMarkdown(''); setMessage(null); setError(null) }
  const close = () => { setSelected(null); setShareQuery(''); setShareOptions([]) }
  const save = async () => {
    if (!title.trim()) return
    setSaving(true); setError(null)
    const input: DocumentInput = { title: title.trim(), markdown }
    try {
      const record = selected === 'new' ? await client.create(scope, input) : await client.update(scope, selected!.id, input)
      setSelected(record); setTitle(record.title); setMarkdown(record.markdown); setMessage('Document saved.'); setRevision((value) => value + 1)
    } catch (saveError) { setError(errorMessage(saveError)) } finally { setSaving(false) }
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
      <div className="document-actions"><button className="primary-button" type="button" disabled={saving || !title.trim()} onClick={() => { void save() }}>{saving ? 'Saving…' : 'Save document'}</button>{selected !== 'new' && <button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}><Archive size={15} />Archive</button>}</div>
      {!workspace && selected !== 'new' && <div className="document-share"><div><Share2 size={16} /><span><strong>List in a client workspace</strong><small>The MSP remains the owner; no document is copied.</small></span></div><label><span className="sr-only">Find client organization</span><input type="search" placeholder="Find a client" value={shareQuery} onChange={(event) => setShareQuery(event.target.value)} /></label>{shareOptions.length > 0 && <ul>{shareOptions.map((organization) => <li key={organization.id}><button type="button" disabled={saving} onClick={() => { void share(organization) }}>{organization.name}<ExternalLink size={14} /></button></li>)}</ul>}</div>}
    </section>}
  </>
}
