import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, KeyRound, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { CollectionPagination } from '../CollectionPagination'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { translate } from '../i18n/localization'
import { useUnsavedChanges } from '../navigation/navigationGuard'
import type { WorkspaceContext } from '../workspaces/api'
import type { CredentialReference, CredentialReferenceDraft, CredentialReferencesClient } from './api'

const EMPTY_DRAFT: CredentialReferenceDraft = { title: '', provider: 'onepassword', reference_url: '' }
const PAGE_SIZES = [25, 50, 100] as const

function positiveInteger(value: string | null) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

function pageSizeFrom(value: string | null): typeof PAGE_SIZES[number] {
  const parsed = Number(value)
  return PAGE_SIZES.includes(parsed as typeof PAGE_SIZES[number]) ? parsed as typeof PAGE_SIZES[number] : 25
}

function draftFor(reference: CredentialReference | null): CredentialReferenceDraft {
  return reference ? { title: reference.title, provider: 'onepassword', reference_url: '' } : { ...EMPTY_DRAFT }
}

export function CredentialReferences({ workspace, client }: { workspace: WorkspaceContext | null; client: CredentialReferencesClient }) {
  const [parameters, setParameters] = useSearchParams()
  const query = parameters.get('q') ?? ''
  const page = positiveInteger(parameters.get('page'))
  const pageSize = pageSizeFrom(parameters.get('page_size'))
  const selectedId = parameters.get('credential')
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [references, setReferences] = useState<CredentialReference[]>([])
  const [canManage, setCanManage] = useState(false)
  const [pageState, setPageState] = useState({ count: 0, hasMore: false })
  const [loadedDetail, setLoadedDetail] = useState<{ id: string; record: CredentialReference } | null>(null)
  const [detailFailure, setDetailFailure] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<CredentialReferenceDraft>({ ...EMPTY_DRAFT })
  const [initialDraft, setInitialDraft] = useState<CredentialReferenceDraft>({ ...EMPTY_DRAFT })
  const [archiving, setArchiving] = useState(false)
  const [saving, setSaving] = useState(false)
  const [closingAfterSave, setClosingAfterSave] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const formOpen = selectedId === 'new' || editing
  const dirty = formOpen && JSON.stringify(draft) !== JSON.stringify(initialDraft)

  const updateParameters = useCallback((changes: Record<string, string | number | null>, replace = false) => {
    const next = new URLSearchParams(parameters)
    for (const [name, value] of Object.entries(changes)) {
      if (value === null || value === '' || name === 'page' && value === 1 || name === 'page_size' && value === 25) next.delete(name)
      else next.set(name, String(value))
    }
    setParameters(next, { replace })
  }, [parameters, setParameters])

  const discard = useCallback(() => {
    setEditing(false)
    setArchiving(false)
    setError(null)
  }, [])
  const attempt = useUnsavedChanges(dirty && !closingAfterSave, saving && !closingAfterSave, discard, Boolean(selectedId && formOpen && !closingAfterSave))

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setPhase('loading')
      void client.list(workspace, query, page, pageSize, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return
          setReferences(result.results)
          setCanManage(result.can_manage)
          setPageState({ count: result.count, hasMore: result.has_more })
          setPhase('ready')
        })
        .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, page, pageSize, query, revision, workspace])

  const listedRecord = selectedId && selectedId !== 'new' ? references.find((reference) => reference.id === selectedId) ?? null : null
  const drawerRecord = loadedDetail?.id === selectedId ? loadedDetail.record : listedRecord
  const detailPhase = selectedId === 'new' || drawerRecord ? 'ready' : detailFailure === selectedId ? 'error' : 'loading'

  useEffect(() => {
    if (!selectedId || selectedId === 'new' || listedRecord) return
    const controller = new AbortController()
    void client.retrieve(workspace, selectedId, controller.signal)
      .then((reference) => {
        if (!controller.signal.aborted) { setLoadedDetail({ id: selectedId, record: reference }); setDetailFailure(null) }
      })
      .catch(() => { if (!controller.signal.aborted) setDetailFailure(selectedId) })
    return () => controller.abort()
  }, [client, listedRecord, revision, selectedId, workspace])

  function changeCollection(changes: Record<string, string | number | null>, replace = false) {
    setError(null)
    updateParameters({ ...changes, page: changes.page ?? null }, replace)
  }

  function openReference(reference: CredentialReference) {
    setLoadedDetail({ id: reference.id, record: reference })
    setDetailFailure(null)
    setEditing(false)
    setArchiving(false)
    setError(null)
    updateParameters({ credential: reference.id })
  }

  function openNew() {
    const next = draftFor(null)
    setDraft(next)
    setInitialDraft(next)
    setEditing(false)
    setArchiving(false)
    setError(null)
    updateParameters({ credential: 'new' })
  }

  function startEdit() {
    const next = draftFor(drawerRecord)
    setDraft(next)
    setInitialDraft(next)
    setEditing(true)
    setArchiving(false)
    setError(null)
  }

  function closeDrawer() {
    attempt(() => window.setTimeout(() => updateParameters({ credential: null }), 0))
  }

  async function save() {
    if (!selectedId || selectedId !== 'new' && !drawerRecord) return
    setSaving(true)
    setError(null)
    try {
      const saved = selectedId === 'new'
        ? await client.create(workspace, draft)
        : await client.update(workspace, selectedId, { title: draft.title, ...(draft.reference_url ? { reference_url: draft.reference_url } : {}) })
      setLoadedDetail({ id: saved.id, record: saved })
      setDraft(draftFor(saved))
      setInitialDraft(draftFor(saved))
      setEditing(false)
      setClosingAfterSave(true)
      window.setTimeout(() => {
        updateParameters({ credential: saved.id }, true)
        setClosingAfterSave(false)
      }, 50)
      setRevision((value) => value + 1)
    } catch (caught) {
      setClosingAfterSave(false)
      setError(caught instanceof Error ? caught.message : translate('credentials.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  async function archive() {
    if (!drawerRecord) return
    setSaving(true)
    setError(null)
    try {
      await client.archive(workspace, drawerRecord.id)
      setArchiving(false)
      updateParameters({ credential: null }, true)
      setRevision((value) => value + 1)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate('credentials.archiveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const returnHref = useMemo(() => {
    const next = new URLSearchParams(parameters)
    next.delete('credential')
    return `?${next.toString()}`
  }, [parameters])
  const drawerTitle = selectedId === 'new' ? translate('credentials.newHeading') : drawerRecord?.title ?? translate('credentials.record')

  return <>
    <header className="page-header"><div><h1>{translate('credentials.heading')}</h1><p>{translate('credentials.intro')}</p></div>{canManage && <button className="primary-button" type="button" onClick={openNew}><Plus size={16} aria-hidden="true" />{translate('credentials.new')}</button>}</header>
    <section className="content-section credential-reference-section" aria-busy={phase === 'loading'}>
      <div className="credential-reference-boundary"><KeyRound size={18} aria-hidden="true" /><div><strong>{translate('credentials.staysInOnePassword')}</strong><p>{translate('credentials.boundaryHelp')}</p></div></div>
      <div className="credential-reference-toolbar">
        <label className="credential-reference-search"><span>{translate('credentials.search')}</span><div><Search size={16} aria-hidden="true" /><input type="search" value={query} onChange={(event) => changeCollection({ q: event.target.value }, true)} placeholder={translate('credentials.searchPlaceholder')} /></div></label>
        <label className="collection-page-size">{translate('collections.pageSize')}<select value={pageSize} onChange={(event) => changeCollection({ page_size: Number(event.target.value) })}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
      </div>
      {query && <div className="collection-active-filters"><button type="button" className="row-action" onClick={() => changeCollection({ q: null })}>{translate('credentials.searchSummary', { query })} ×</button></div>}
      {phase === 'loading' && <p className="empty-state" role="status">{translate('credentials.loading')}</p>}
      {phase === 'error' && <div className="empty-state" role="alert"><p>{translate('credentials.unavailable')}</p><button className="secondary-button" type="button" onClick={() => setRevision((value) => value + 1)}>{translate('common.retry')}</button></div>}
      {phase === 'ready' && references.length === 0 && <p className="empty-state">{query ? translate('credentials.noMatches') : translate('credentials.empty')}</p>}
      {phase === 'ready' && references.length > 0 && <>
        <div className="section-heading credential-reference-list-heading"><h2>{translate('credentials.list')}</h2><span>{translate('credentials.count', { count: pageState.count })}</span></div>
        <ul className="credential-reference-list">{references.map((reference) => <li key={reference.id}><button id={`credential-row-${reference.id}`} className="collection-name" type="button" onClick={() => openReference(reference)}><strong>{reference.title}</strong><span>{reference.provider_label} · {translate('credentials.updated', { date: new Date(reference.updated_at).toLocaleDateString() })}</span></button></li>)}</ul>
        <CollectionPagination label={translate('credentials.heading')} page={page} pageSize={pageSize} count={pageState.count} hasMore={pageState.hasMore} onPageChange={(next) => changeCollection({ page: next })} />
      </>}
    </section>
    {selectedId && <QuickDrawer title={drawerTitle} returnFocusId={selectedId === 'new' ? undefined : `credential-row-${selectedId}`} returnHref={returnHref} returnLabel={translate('credentials.back')} onClose={closeDrawer}>
      {selectedId === 'new' && !canManage && phase === 'ready' && <p className="form-message error" role="alert">{translate('credentials.createDenied')}</p>}
      {detailPhase === 'loading' && <p className="empty-state" role="status">{translate('credentials.recordLoading')}</p>}
      {detailPhase === 'error' && <div className="empty-state" role="alert"><p>{translate('credentials.recordUnavailable')}</p><button type="button" className="secondary-button" onClick={() => { setDetailFailure(null); setRevision((value) => value + 1) }}>{translate('common.retry')}</button></div>}
      {detailPhase === 'ready' && selectedId === 'new' && canManage && <CredentialForm draft={draft} creating saving={saving} error={error} onChange={setDraft} onSave={save} onCancel={closeDrawer} />}
      {detailPhase === 'ready' && selectedId !== 'new' && drawerRecord && (editing
        ? <CredentialForm draft={draft} creating={false} saving={saving} error={error} onChange={setDraft} onSave={save} onCancel={() => attempt(discard)} />
        : <div className="credential-reference-record"><p>{translate('credentials.recordHelp')}</p><dl className="record-facts"><div><dt>{translate('credentials.provider')}</dt><dd>{drawerRecord.provider_label}</dd></div><div><dt>{translate('credentials.lastUpdated')}</dt><dd>{new Date(drawerRecord.updated_at).toLocaleString()}</dd></div></dl><div className="form-actions">{drawerRecord.can_open && <a className="primary-button" href={client.openUrl(workspace, drawerRecord.id)} target="_blank" rel="noopener noreferrer">{translate('credentials.open')}<ExternalLink size={14} aria-hidden="true" /></a>}{drawerRecord.can_manage && <><button className="secondary-button" type="button" onClick={startEdit}><Pencil size={15} aria-hidden="true" />{translate('common.edit')}</button><button className="row-action danger" type="button" onClick={() => { setArchiving(true); setError(null) }}><Trash2 size={15} aria-hidden="true" />{translate('common.archive')}</button></>}</div>{error && <div className="form-message error" role="alert">{error}</div>}{archiving && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-credential-reference-heading"><div><strong id="archive-credential-reference-heading">{translate('credentials.archiveHeading', { title: drawerRecord.title })}</strong><p>{translate('credentials.archiveHelp')}</p></div><div className="form-actions"><button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}>{saving ? translate('credentials.archiving') : translate('common.archive')}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setArchiving(false)}>{translate('common.cancel')}</button></div></div>}</div>)}
    </QuickDrawer>}
  </>
}

function CredentialForm({ draft, creating, saving, error, onChange, onSave, onCancel }: { draft: CredentialReferenceDraft; creating: boolean; saving: boolean; error: string | null; onChange: (draft: CredentialReferenceDraft) => void; onSave: () => Promise<void>; onCancel: () => void }) {
  return <form className="credential-reference-form" onSubmit={(event) => { event.preventDefault(); void onSave() }}>
    <p>{translate('credentials.formHelp')}</p>
    {error && <div className="form-message error" role="alert">{error}</div>}
    <div className="form-grid"><label><span>{translate('credentials.title')}</span><input autoFocus required value={draft.title} maxLength={240} onChange={(event) => onChange({ ...draft, title: event.target.value })} /></label><label className="wide-field"><span>{creating ? translate('credentials.privateLink') : translate('credentials.replacementLink')}</span><input required={creating} type="url" autoComplete="off" spellCheck={false} value={draft.reference_url} placeholder="https://start.1password.com/open/i?…" onChange={(event) => onChange({ ...draft, reference_url: event.target.value })} /><small>{translate('credentials.copyHelp')}</small></label></div>
    <div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? translate('common.saving') : translate('credentials.save')}</button><button className="secondary-button" type="button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
  </form>
}
